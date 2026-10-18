"""Servidor Model Context Protocol (MCP) para Oracle Database (ERP SGT).

Implementa a especificação JSON-RPC 2.0 (protocolo 2024-11-05) sobre STDIO para
fornecer ferramentas de inspeção e consulta seguras ao Oracle do ERP SGT.

Arquitetura e Contrato Operacional:
1. Data Center Unifique:
   - Conecta ao Oracle do Data Center Unifique pelo DSN configurado (ORACLE_CONNECT_STRING, padrão dbprd)
     preferencialmente via alias TNS 'dbprd' com SDU = 65535 e ENABLE = BROKEN.
2. Driver adaptativo (lib/python/oracle_client.py):
   - Thin Mode por padrão. Se o servidor oferecer só o verificador de senha legado
     (0x939, DPY-3015), ativa o Thick Mode com o Oracle Client de ORACLE_CLIENT_LIB_DIR
     e reconecta. Sem redeploy, quando a senha for regenerada, volta para Thin Mode puro.
   - ORACLE_DRIVER_MODE=thick força o Thick Mode antes da primeira conexão (rollback).
3. Otimização WAN:
   - Arraysize e prefetchrows iguais a ORACLE_MCP_ARRAYSIZE (padrão 1000) em todos os
     cursores, para reduzir round-trips na rede WAN (~4 ms de RTT). execute_sql limita o
     tamanho de busca ao max_rows pedido.
4. Resiliência e Watchdog:
   - Prazo por chamada via `connection.call_timeout` nativo (Thin ou Oracle Client 18.1+);
     em Client abaixo de 18.1, emulado por thread e connection.cancel() (oracle_session.py).
     Protege contra travamentos e desconexões silenciosas (ORA-00028, ORA-03113, ORA-03135,
     DPY-1001).
5. Segurança Estrita (Somente Leitura):
   - Todas as queries passam pelo Guardião SQL (Tools/oracle/guard_sql.py).
   - Bloqueio determinístico de DML, DDL, PL/SQL, transações e múltiplas instruções.
"""

from __future__ import annotations

import atexit
import contextlib
import functools
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Força codificação UTF-8 nos streams
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Carrega variáveis do .env da raiz do repositório
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import oracledb  # noqa: E402

# Módulos compartilhados do repositório (lib/python, já no sys.path acima).
from oracle_client import (  # noqa: E402
    CONNECT_PARAMS,
    DRIVER_MODE_THICK,
    LEGACY_VERIFIER_MARKER,
    aplicar_metadados_oci,
    connect_adaptive,
    describe_driver_mode,
    get_driver_mode,
    init_oracle_thick_mode,
)
from oracle_session import (  # noqa: E402
    call_deadline,
    connect_within,
    is_session_drop,
    supports_native_call_timeout,
)

# Guardião SQL do acervo. Se não carregar, validate_read_only bloqueia tudo (fail-closed).
_guard_sql: Any = None
_erro_import_guard: str | None = None
try:
    import guard_sql

    _guard_sql = guard_sql
except Exception as exc:  # pylint: disable=broad-exception-caught
    _erro_import_guard = f"{type(exc).__name__}: {exc}"

SERVER_NAME = "oracledb"
SERVER_VERSION = "2.0.0"
PROTOCOL_VERSION = "2024-11-05"

# Sem caminho padrão do Oracle Client: a máquina pode ter o 12.2 legado ou o Instant
# Client 19c (Tools/oracle/Install-InstantClient19c.ps1, destino escolhido na instalação),
# e adivinhar um deles carregaria o cliente errado em silêncio. Em Thick Mode,
# ORACLE_CLIENT_LIB_DIR (ou ORACLE_CLIENT_PATH) e TNS_ADMIN vêm do ambiente/.env.
DEFAULT_LIB_DIR = ""
DEFAULT_TNS_ADMIN = ""
DEFAULT_DSN = "dbprd"
DEFAULT_TIMEOUT = 60.0
DEFAULT_ARRAYSIZE = 1000
# Teto do ping ao reutilizar a sessão: sessão morta não pode travar o servidor inteiro.
PRAZO_PING_SEGUNDOS = 15.0
# Depois de falhar ao criar o SessionPool, espera esta janela antes de tentar de novo.
JANELA_NOVA_TENTATIVA_POOL_SEGUNDOS = 300.0
# Teto do rollback que desfaz o EXPLAIN PLAN: socket travado não pode prender o loop STDIO.
PRAZO_ROLLBACK_SEGUNDOS = 15.0
# Depois de falha de conexão avulsa, novas tentativas são recusadas por esta janela,
# para que cada chamada não espere o prazo de conexão inteiro durante uma queda de rede.
JANELA_FALHA_CONEXAO_SEGUNDOS = 30.0
# Teto de caracteres lidos de um CLOB por célula; acima disso o texto é truncado.
LIMITE_CLOB_CARACTERES = 4000
FORMATOS_EXECUCAO = ("table", "json")
# Cache do canônico do guard: (módulo carregado, canônico já com patch). Recarregado
# apenas quando o módulo muda, o que exige reinício do servidor após editar o canônico.
_cache_canonico: dict[str, tuple[Any, Any]] = {}


def log_stderr(message: str) -> None:
    """Registra mensagens operacionais em STDERR sem poluir o STDOUT do JSON-RPC."""
    sys.stderr.write(f"[{SERVER_NAME}] {message}\n")
    sys.stderr.flush()


@dataclass(frozen=True)
class OracleConfig:
    user: str
    password: str
    dsn: str
    client_lib: str
    tns_admin: str
    timeout: float
    arraysize: int


def load_config() -> OracleConfig:
    """Lê configuração do ambiente respeitando as variáveis canônicas do Hub."""
    user = (
        os.environ.get("ORACLE_READONLY_USER")
        or os.environ.get("ORACLE_USERNAME")
        or os.environ.get("ORACLE_USER")
        or ""
    )
    password = (
        os.environ.get("ORACLE_READONLY_PASSWORD")
        or os.environ.get("ORACLE_PASSWORD")
        or ""
    )
    dsn = os.environ.get("ORACLE_CONNECT_STRING") or os.environ.get(
        "ORACLE_CONNECTION_STRING", DEFAULT_DSN
    )
    client_lib = (
        os.environ.get("ORACLE_CLIENT_LIB_DIR")
        or os.environ.get("ORACLE_CLIENT_PATH")
        or DEFAULT_LIB_DIR
    )
    tns_admin = os.environ.get("TNS_ADMIN") or DEFAULT_TNS_ADMIN
    if get_driver_mode() == DRIVER_MODE_THICK and not client_lib:
        log_stderr(
            "ORACLE_DRIVER_MODE=thick sem ORACLE_CLIENT_LIB_DIR: defina no .env o "
            "diretório do Oracle Client (12.2 ou Instant Client 19c)."
        )

    try:
        timeout = float(os.environ.get("ORACLE_MCP_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        timeout = DEFAULT_TIMEOUT
    if (
        timeout <= 0
    ):  # zero desligaria o prazo no Thin e cancelaria tudo em 50 ms no Client 12.2
        timeout = DEFAULT_TIMEOUT

    try:
        arraysize = int(os.environ.get("ORACLE_MCP_ARRAYSIZE", DEFAULT_ARRAYSIZE))
    except ValueError:
        arraysize = DEFAULT_ARRAYSIZE
    if arraysize <= 0:
        arraysize = DEFAULT_ARRAYSIZE

    return OracleConfig(
        user=user,
        password=password,
        dsn=dsn,
        client_lib=client_lib,
        tns_admin=tns_admin,
        timeout=timeout,
        arraysize=arraysize,
    )


def log_driver(message: str, level: str = "INFO") -> None:
    """Adaptador de log do connect_adaptive para o STDERR do servidor."""
    log_stderr(f"[{level}] {message}")


CABECALHO_COLUNAS = ["#", "COLUNA", "TIPO", "ANULÁVEL", "COMENTÁRIO"]


def _canonico_do_guard() -> Any:
    """Canônico do guard com patch aplicado, carregado uma vez por processo.

    `_guard_sql` é fixado no import, então o canônico só muda após reiniciar o MCP.
    Uma falha ao carregar não grava nada no cache, então a chamada seguinte repete a
    validação e continua fail-closed.
    """
    guard = _guard_sql
    entrada = _cache_canonico.get("entrada")
    if entrada is not None and entrada[0] is guard:
        return entrada[1]
    canon = guard.patch_canonical(guard.load_canonical())
    _cache_canonico["entrada"] = (guard, canon)
    return canon


def _validar_pelo_guard(sql: str) -> tuple[bool, str]:
    """Autoridade única de leitura: o guard_sql do acervo. Sem ele, nada passa (fail-closed)."""
    if _guard_sql is None:
        motivo_import = f" Causa: {_erro_import_guard}." if _erro_import_guard else ""
        return (
            False,
            "Guard SQL indisponível: consulta bloqueada por segurança (fail-closed)."
            + motivo_import,
        )
    try:
        canon = _canonico_do_guard()
        classificacao = canon.classificar(sql, exigir_limite=False)
        if (
            not classificacao.get("permitido", False)
            or classificacao.get("classe") != "leitura"
        ):
            motivos = (
                ", ".join(classificacao.get("motivos", []))
                or "Classificada como mutação/DDL"
            )
            return False, f"Bloqueado pelo guard_sql: {motivos}"
        return True, ""
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return False, f"Guard SQL falhou ao validar (fail-closed): {exc}"


def validate_read_only(sql: str) -> tuple[bool, str]:
    """Valida se a instrução SQL é estritamente Somente Leitura (Read-Only).

    Fail-closed: só o guard_sql do acervo aprova. Se ele não estiver disponível ou
    falhar, a consulta é bloqueada. O antigo fallback por regex foi removido porque
    deixava passar funções com efeito colateral, como `SELECT pkg.func() FROM dual`.
    """
    return _validar_pelo_guard(sql)


def _normalizar_lob(lob: Any, tipo: Any) -> str:
    """Converte um LOB sem carregá-lo inteiro: BLOB vira marcador, CLOB é lido com teto."""
    if tipo == oracledb.DB_TYPE_BLOB:
        tamanho = getattr(lob, "size", None)
        return f"<blob {tamanho} bytes>" if isinstance(tamanho, int) else "<blob>"
    bruto = lob.read(1, LIMITE_CLOB_CARACTERES + 1)
    if isinstance(bruto, (bytes, bytearray)):  # tipo desconhecido e conteúdo binário
        return "<blob>"
    texto: str = bruto
    if len(texto) > LIMITE_CLOB_CARACTERES:
        return (
            texto[:LIMITE_CLOB_CARACTERES]
            + f"... [CLOB truncado em {LIMITE_CLOB_CARACTERES} caracteres]"
        )
    return texto


def _normalizar_valor(val: Any, tipo: Any = None) -> Any:
    """Converte um valor do cursor em algo serializável (ordem de decisão preservada)."""
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, (bytes, bytearray)):
        return f"<blob {len(val)} bytes>"
    if hasattr(val, "read"):  # LOB locator
        return _normalizar_lob(val, tipo)
    if isinstance(val, str):
        return val.strip()
    return val


def _linhas_colunas(rows: list[Any]) -> list[list[Any]]:
    """Converte as linhas de ALL_TAB_COLS nas linhas da tabela de descrição."""
    return [
        [
            col_id,
            col_name,
            type_str,
            "SIM" if nullable == "Y" else "NÃO",
            (comments or "").strip(),
        ]
        for col_id, col_name, _, type_str, nullable, comments in rows
    ]


def _descricao_timeout() -> str:
    """Como o prazo por chamada é aplicado: nativo no driver ou emulado por thread."""
    if supports_native_call_timeout():
        return "nativo (`call_timeout`)"
    return "emulado (thread + cancel; Oracle Client abaixo de 18.1)"


def _erro_rpc(req_id: Any, codigo: int, mensagem: str) -> dict[str, Any]:
    """Resposta de erro JSON-RPC 2.0."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": codigo, "message": mensagem},
    }


def _motivo_argumentos_invalidos(ferramenta: str, args: dict[str, Any]) -> str | None:
    """Motivo da rejeição (-32602) quando os tipos dos argumentos não batem com o schema."""
    if ferramenta in ("execute_sql", "get_query_plan") and not isinstance(
        args.get("sql", ""), str
    ):
        return "'sql' deve ser texto."
    if ferramenta == "execute_sql":
        max_rows = args.get("max_rows", 100)
        if isinstance(max_rows, bool) or not isinstance(max_rows, int):
            return "'max_rows' deve ser um inteiro."
        if args.get("format", "table") not in FORMATOS_EXECUCAO:
            return "'format' deve ser 'table' ou 'json'."
    return None


class OracleConnectionManager:
    """Gerenciador de conexão Oracle com SessionPool, fallback dedicado e watchdog."""

    def __init__(self, config: OracleConfig) -> None:
        self.config = config
        self._pool: Any | None = None
        self._conn: Any | None = None
        self._lock = threading.Lock()
        self._pool_failed = False
        self._pool_failed_em: float | None = None
        self._falha_conexao: tuple[float, str] | None = None
        atexit.register(self.close)

    def _init_pool_if_needed(self) -> None:
        """Inicializa o SessionPool com Thick/Thin adaptativo de forma idempotente."""
        if self._pool is not None:
            return
        if self._pool_failed:
            # Falha do pool não é permanente: após a janela, tenta de novo (a rede
            # do Data Center derruba e volta). Sem instante registrado, não expira.
            if (
                self._pool_failed_em is None
                or time.monotonic() - self._pool_failed_em
                < JANELA_NOVA_TENTATIVA_POOL_SEGUNDOS
            ):
                return
            self._pool_failed = False
            self._pool_failed_em = None

        if not self.config.user or not self.config.password:
            return

        extra_pool: dict[str, Any] = {}
        if self.config.tns_admin and oracledb.is_thin_mode():
            extra_pool["config_dir"] = self.config.tns_admin

        pool_params: dict[str, Any] = {
            "user": self.config.user,
            "password": self.config.password,
            "dsn": self.config.dsn,
            "min": 1,
            "max": 4,
            "increment": 1,
            "getmode": oracledb.POOL_GETMODE_WAIT,
            "timeout": 300,
            "homogeneous": True,
            # Mesmos prazos de rede das conexões avulsas (fonte única em oracle_client).
            **CONNECT_PARAMS,
            **extra_pool,
        }

        # Inicializa Thick Mode antecipadamente se configurado explicitamente
        if get_driver_mode() == DRIVER_MODE_THICK:
            init_oracle_thick_mode(
                self.config.client_lib, self.config.tns_admin, log_driver
            )

        log_stderr(
            f"Criando SessionPool Oracle Unifique (min=1, max=4, DSN: {self.config.dsn})..."
        )
        try:
            self._pool = oracledb.create_pool(**pool_params)
            log_stderr("SessionPool Oracle inicializado com sucesso (min=1, max=4).")
        except oracledb.NotSupportedError as exc:
            if LEGACY_VERIFIER_MARKER in str(exc) and oracledb.is_thin_mode():
                log_stderr(
                    "Servidor ofereceu verificador de senha legado (DPY-3015) para o pool. "
                    "Ativando Thick Mode e recriando SessionPool..."
                )
                pool_params.pop("config_dir", None)
                try:
                    # Dentro do try: falha no init (Instant Client ausente) também
                    # precisa marcar _pool_failed e cair nas conexões dedicadas.
                    init_oracle_thick_mode(
                        self.config.client_lib, self.config.tns_admin, log_driver
                    )
                    self._pool = oracledb.create_pool(**pool_params)
                    log_stderr(
                        "SessionPool Oracle inicializado com sucesso em Thick Mode."
                    )
                    return
                except Exception as inner_exc:  # pylint: disable=broad-exception-caught
                    log_stderr(
                        f"Falha ao recriar pool em Thick Mode ({inner_exc}). Fallback para conexões dedicadas."
                    )
                    self._marcar_pool_falho()
            else:
                log_stderr(
                    f"Aviso: Não foi possível criar SessionPool ({exc}). Fallback para conexões dedicadas."
                )
                self._marcar_pool_falho()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log_stderr(
                f"Aviso: Não foi possível criar SessionPool ({exc}). Fallback para conexões dedicadas."
            )
            self._marcar_pool_falho()

    def _marcar_pool_falho(self) -> None:
        self._pool_failed = True
        self._pool_failed_em = time.monotonic()

    @property
    def pool(self) -> Any | None:
        """Acesso direto ao SessionPool gerenciado (ou None se inativo)."""
        with self._lock:
            self._init_pool_if_needed()
            return self._pool

    def acquire_connection(self) -> Any:
        """Adquire uma conexão viva do SessionPool ou da conexão dedicada (fallback)."""
        with self._lock:
            if not self.config.user or not self.config.password:
                raise ValueError(
                    "Credenciais Oracle ausentes no ambiente (.env). "
                    "Configure ORACLE_READONLY_USER e ORACLE_READONLY_PASSWORD."
                )

            self._init_pool_if_needed()

            # 1. Tenta adquirir do SessionPool
            if self._pool is not None:
                try:
                    return self._pool.acquire()
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    log_stderr(
                        f"Falha ao adquirir do SessionPool ({exc}); tentando fallback dedicado..."
                    )

            # 2. Fallback para conexão dedicada avulsa com ping watchdog
            if self._conn is not None:
                try:
                    with call_deadline(
                        self._conn, PRAZO_PING_SEGUNDOS, threading.Event()
                    ):
                        self._conn.ping()
                    return self._conn
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    log_stderr(f"Sessão dedicada inválida ({exc}); reconectando...")
                    with contextlib.suppress(Exception):
                        self._conn.close()
                    self._conn = None

            # Após uma falha recente, recusa sem tentar: cada tentativa custaria o prazo
            # de conexão inteiro, e durante uma queda isso travaria cada chamada.
            if self._falha_conexao is not None:
                instante, motivo = self._falha_conexao
                if time.monotonic() - instante < JANELA_FALHA_CONEXAO_SEGUNDOS:
                    raise ConnectionError(
                        "Conexão Oracle recusada por "
                        f"{JANELA_FALHA_CONEXAO_SEGUNDOS:g} s após falha anterior: {motivo}"
                    )
                self._falha_conexao = None

            log_stderr(
                f"Conectando ao Oracle Unifique via conexão avulsa (DSN: {self.config.dsn})..."
            )

            def _do_connect() -> Any:
                return connect_adaptive(
                    user=self.config.user,
                    password=self.config.password,
                    dsn=self.config.dsn,
                    client_lib=self.config.client_lib,
                    tns_admin=self.config.tns_admin,
                    log_fn=log_driver,
                )

            try:
                self._conn = connect_within(_do_connect, seconds=15.0)
            except Exception as exc:
                self._falha_conexao = (time.monotonic(), str(exc))
                raise
            self._falha_conexao = None
            log_stderr("Conexão avulsa estabelecida com sucesso.")
            return self._conn

    def release_connection(self, conn: Any) -> None:
        """Devolve a conexão ao SessionPool ou preserva conexão dedicada."""
        if conn is None:
            return
        with self._lock:
            if self._pool is not None:
                with contextlib.suppress(Exception):
                    self._pool.release(conn)

    def get_connection(self) -> Any:
        """Método de compatibilidade para clientes que solicitam conexão."""
        return self.acquire_connection()

    def get_pool_status(self) -> dict[str, Any]:
        """Retorna o status operacional do SessionPool para relatórios e telemetria."""
        with self._lock:
            if self._pool is not None:
                try:
                    return {
                        "active": True,
                        "open": getattr(self._pool, "opened", 0),
                        "busy": getattr(self._pool, "busy", 0),
                        "max": getattr(self._pool, "max", 4),
                        "min": getattr(self._pool, "min", 1),
                        "timeout": getattr(self._pool, "timeout", 300),
                    }
                except Exception:  # pylint: disable=broad-exception-caught
                    # Telemetria do pool nunca derruba o relatório de diagnóstico.
                    return {"active": True, "open": 0, "busy": 0, "max": 4}
            return {
                "active": False,
                "open": 1 if self._conn is not None else 0,
                "busy": 0,
                "max": 1,
            }

    def discard_connection(self, conn: Any | None) -> None:
        """Descarta só a conexão afetada por uma falha, sem derrubar o pool.

        Conexão do pool sai com `pool.drop` (o pool repõe sob demanda); a dedicada é
        fechada. `None` descarta a dedicada, quando quem falhou não tem a conexão.
        """
        with self._lock:
            alvo: Any = self._conn if conn is None else conn
            if alvo is None:
                return
            if alvo is self._conn:
                self._conn = None
            elif self._pool is not None:
                try:
                    self._pool.drop(alvo)
                    return
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    log_stderr(f"pool.drop falhou ({exc}); fechando a conexão.")
            with contextlib.suppress(Exception):
                alvo.close()

    def close(self) -> None:
        """Encerra o SessionPool e a conexão avulsa (no encerramento do servidor)."""
        with self._lock:
            if self._pool is not None:
                try:
                    # force=True: conexões ocupadas não podem impedir o fechamento.
                    self._pool.close(force=True)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    log_stderr(f"Falha ao fechar o SessionPool: {exc}")
                self._pool = None
            if self._conn is not None:
                with contextlib.suppress(Exception):
                    self._conn.close()
                self._conn = None


def _fronteira_de_ferramenta(
    prefixo: str, *, fecha_em_queda: bool = False
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Fronteira de erro das ferramentas: qualquer falha vira resposta de erro com `prefixo`.

    `fecha_em_queda` fecha a conexão compartilhada quando a falha é queda de sessão,
    para a próxima chamada reconectar.
    """

    def decorador(
        funcao: Callable[..., dict[str, Any]],
    ) -> Callable[..., dict[str, Any]]:
        @functools.wraps(funcao)
        def envolvida(
            self: OracleMcpTools, *args: Any, **kwargs: Any
        ) -> dict[str, Any]:
            try:
                return funcao(self, *args, **kwargs)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if fecha_em_queda and is_session_drop(exc):
                    self.conn_mgr.discard_connection(None)
                return {"error": True, "message": f"{prefixo}{exc}"}

        return envolvida

    return decorador


class OracleMcpTools:
    """Implementação das ferramentas expostas pelo servidor MCP."""

    def __init__(self, conn_mgr: OracleConnectionManager, config: OracleConfig) -> None:
        self.conn_mgr = conn_mgr
        self.config = config

    def _instrumentar_sessao(self, conn: Any, tool_name: str) -> None:
        """Identifica a sessão em V$SESSION do Oracle 19c para o monitoramento do acervo.

        - module: HubAutomacoes.MCP
        - action: TOOL:<nome_da_ferramenta>
        - client_identifier: MCP:<tool>:<session_id[:8]>
        """
        session_id = (
            os.environ.get("MCP_SESSION_ID")
            or os.environ.get("CONVERSATION_ID")
            or f"{os.getpid():x}"
        )
        erro = aplicar_metadados_oci(
            conn,
            modulo="HubAutomacoes.MCP",
            acao=f"TOOL:{tool_name}",
            identificador=f"MCP:{tool_name}:{session_id[:8]}",
            db_op=f"TOOL_{tool_name.upper()}",
        )
        if erro:
            log_stderr(f"Aviso não-bloqueante ao instrumentar sessão OCI MCP: {erro}")

    def _liberar_conexao(self, conn: Any | None) -> None:
        """Devolve a conexão ao SessionPool após a execução da ferramenta."""
        if conn is not None and hasattr(self.conn_mgr, "release_connection"):
            with contextlib.suppress(Exception):
                self.conn_mgr.release_connection(conn)

    def _abrir_cursor(self, conn: Any) -> Any:
        """`conn.cursor()` que devolve a conexão ao pool se falhar.

        Sem isto, um cursor() que lança (sessão já derrubada) deixaria a conexão
        presa: o pool tem max=4 com GETMODE_WAIT e travaria as chamadas seguintes.
        """
        try:
            return conn.cursor()
        except Exception:
            self._liberar_conexao(conn)
            raise

    def _configurar_cursor(self, cursor: Any) -> None:
        """Tamanho de busca igual em arraysize e prefetchrows (ORACLE_MCP_ARRAYSIZE)."""
        cursor.arraysize = cursor.prefetchrows = self.config.arraysize

    def _conexao(
        self, prefixo: str, tool_name: str | None = None
    ) -> tuple[Any, dict[str, Any] | None]:
        """Conexão viva, ou a resposta de erro pronta quando não há conexão."""
        try:
            conn = self.conn_mgr.get_connection()
            if tool_name:
                self._instrumentar_sessao(conn, tool_name)
            return conn, None
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return None, {"error": True, "message": f"{prefixo}{exc}"}

    def execute_sql(
        self,
        sql: str,
        max_rows: int = 100,
        output_format: str = "table",
    ) -> dict[str, Any]:
        """Executa consulta SELECT com prazo por chamada e cursores otimizados."""
        is_safe, reason = validate_read_only(sql)
        if not is_safe:
            return {
                "error": True,
                "message": f"Segurança MCP (Read-Only Violation): {reason}",
            }

        max_rows = max(1, min(max_rows, 5000))
        start_time = time.perf_counter()

        conn, erro = self._conexao(
            "Erro de conexão com o banco Oracle: ", tool_name="execute_sql"
        )
        if erro is not None:
            return erro

        cursor = self._abrir_cursor(conn)
        cursor.arraysize = cursor.prefetchrows = min(self.config.arraysize, max_rows)

        fired = threading.Event()
        try:
            with call_deadline(conn, self.config.timeout, fired):
                cursor.execute(sql)
                if not cursor.description:
                    return {"columns": [], "rows": [], "row_count": 0, "duration_ms": 0}

                columns, linhas, truncado = self._buscar_linhas(cursor, max_rows)

            return self._resposta_execucao(
                columns,
                linhas,
                output_format,
                round((time.perf_counter() - start_time) * 1000, 2),
                truncado,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return self._falha_execucao(exc, fired, conn)
        finally:
            with contextlib.suppress(Exception):
                cursor.close()
            self._liberar_conexao(conn)

    @staticmethod
    def _buscar_linhas(
        cursor: Any, max_rows: int
    ) -> tuple[list[str], list[list[Any]], bool]:
        """Colunas, linhas normalizadas e a marca de truncamento de uma consulta com resultado.

        Busca `max_rows + 1`: uma linha além do pedido prova que há mais dados. A
        normalização fica dentro do prazo, porque a leitura de LOB também faz round-trips.
        """
        columns = [col[0] for col in cursor.description]
        tipos = [col[1] if len(col) > 1 else None for col in cursor.description]
        brutas = cursor.fetchmany(max_rows + 1)
        linhas = [
            [_normalizar_valor(v, tipo) for v, tipo in zip(linha, tipos, strict=True)]
            for linha in brutas[:max_rows]
        ]
        return columns, linhas, len(brutas) > max_rows

    @staticmethod
    def _resposta_execucao(
        columns: list[str],
        cleaned_rows: list[list[Any]],
        output_format: str,
        elapsed_ms: float,
        truncated: bool,
    ) -> dict[str, Any]:
        """Monta a resposta de sucesso no formato pedido (tabela Markdown ou JSON)."""
        if output_format == "json":
            return {
                "data": [dict(zip(columns, r, strict=True)) for r in cleaned_rows],
                "row_count": len(cleaned_rows),
                "columns": columns,
                "duration_ms": elapsed_ms,
                "truncated": truncated,
            }

        table_md = OracleMcpTools._render_markdown_table(columns, cleaned_rows)
        meta = f"\n\n*Retornadas {len(cleaned_rows)} linha(s) em {elapsed_ms} ms"
        if truncated:
            meta += f" (limite de {len(cleaned_rows)} linhas atingido)*"
        else:
            meta += "*"
        return {"text": table_md + meta}

    def _falha_execucao(
        self, exc: BaseException, fired: threading.Event, conn: Any | None = None
    ) -> dict[str, Any]:
        """Classifica a falha da execução: timeout, queda de sessão ou erro do banco."""
        if fired.is_set():
            # Depois de cancelar no meio de um round-trip, a sessão pode ficar
            # inutilizável (DPI-1067/ORA-03156 no Thick): descarta em vez de devolver ao pool.
            self.conn_mgr.discard_connection(conn)
            return {
                "error": True,
                "message": (
                    f"Timeout da consulta: uma chamada ao banco excedeu o limite de {self.config.timeout:g}s "
                    "e foi cancelada pelo watchdog para preservar a integridade do processo."
                ),
            }
        if is_session_drop(exc):
            self.conn_mgr.discard_connection(conn)
            return {
                "error": True,
                "message": (
                    f"Sessão Oracle desconectada pela rede/servidor ({exc}). "
                    "A conexão com o Data Center da Unifique será restabelecida na próxima chamada."
                ),
            }
        return {
            "error": True,
            "message": f"Erro Oracle durante a execução: {exc}",
        }

    @_fronteira_de_ferramenta("Falha ao obter plano de execução: ", fecha_em_queda=True)
    def get_query_plan(self, sql: str) -> dict[str, Any]:
        """Gera o plano de execução via EXPLAIN PLAN / DBMS_XPLAN sem rodar a query.

        O EXPLAIN PLAN grava em PLAN_TABLE dentro da transação da sessão. O rollback
        final desfaz essa escrita: a ferramenta não persiste nada no banco (sem COMMIT).
        """
        is_safe, reason = validate_read_only(sql)
        if not is_safe:
            return {"error": True, "message": f"Segurança MCP: {reason}"}

        stmt_id = f"mcp_plan_{int(time.time())}"
        conn, erro = self._conexao(
            "Erro de conexão Oracle: ", tool_name="get_query_plan"
        )
        if erro is not None:
            return erro

        cursor = self._abrir_cursor(conn)
        self._configurar_cursor(cursor)

        try:
            with call_deadline(conn, self.config.timeout, threading.Event()):
                # 1. EXPLAIN PLAN: as linhas ficam pendentes na transação da sessão.
                cursor.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{stmt_id}' FOR {sql}")
                # 2. Plano formatado pelo DBMS_XPLAN, na mesma sessão.
                cursor.execute(
                    "SELECT PLAN_TABLE_OUTPUT FROM TABLE("
                    "DBMS_XPLAN.DISPLAY('PLAN_TABLE', :stmt_id, 'TYPICAL')"
                    ")",
                    {"stmt_id": stmt_id},
                )
                lines = [row[0] for row in cursor.fetchall()]
            return {"text": "\n".join(lines)}
        finally:
            self._desfazer_plano(conn, cursor)

    def _desfazer_plano(self, conn: Any, cursor: Any) -> None:
        """Rollback, nunca COMMIT: descarta as linhas do EXPLAIN PLAN.

        Tem prazo próprio. Falha ou estouro aqui descarta a conexão (limpeza best effort).
        """
        descartar = False
        try:
            with call_deadline(conn, PRAZO_ROLLBACK_SEGUNDOS, threading.Event()):
                conn.rollback()
        except Exception:  # pylint: disable=broad-exception-caught
            descartar = True
        with contextlib.suppress(Exception):
            cursor.close()
        if descartar:
            self.conn_mgr.discard_connection(conn)
        else:
            self._liberar_conexao(conn)

    @_fronteira_de_ferramenta("Erro ao listar tabelas: ")
    def list_tables(
        self,
        pattern: str | None = None,
        owner: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Lista tabelas e views acessíveis com paginação e busca por padrão."""
        limit = max(1, min(limit, 500))
        target_owner = (
            owner or os.environ.get("ORACLE_DEFAULT_SCHEMA", "SGTPRD")
        ).upper()

        sql = (
            "SELECT OWNER, TABLE_NAME, 'TABLE' AS OBJECT_TYPE, NUM_ROWS, TABLESPACE_NAME "
            "FROM ALL_TABLES WHERE OWNER = :owner "
        )
        params: dict[str, Any] = {"owner": target_owner}

        if pattern:
            sql += "AND TABLE_NAME LIKE :pattern "
            params["pattern"] = pattern.upper()

        sql += (
            "UNION ALL "
            "SELECT OWNER, VIEW_NAME AS TABLE_NAME, 'VIEW' AS OBJECT_TYPE, NULL AS NUM_ROWS, NULL AS TABLESPACE_NAME "
            "FROM ALL_VIEWS WHERE OWNER = :owner "
        )
        if pattern:
            sql += "AND VIEW_NAME LIKE :pattern "

        sql += f"ORDER BY TABLE_NAME FETCH FIRST {limit} ROWS ONLY"

        conn, erro = self._conexao("Erro de conexão: ", tool_name="list_tables")
        if erro is not None:
            return erro

        cursor = self._abrir_cursor(conn)
        self._configurar_cursor(cursor)

        try:
            with call_deadline(conn, self.config.timeout, threading.Event()):
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            cols = ["OWNER", "TABLE_NAME", "TYPE", "NUM_ROWS", "TABLESPACE"]
            return {"text": self._render_markdown_table(cols, rows)}
        finally:
            with contextlib.suppress(Exception):
                cursor.close()
            self._liberar_conexao(conn)

    @_fronteira_de_ferramenta("Erro ao descrever tabela: ")
    def describe_table(
        self, table_name: str, owner: str | None = None
    ) -> dict[str, Any]:
        """Descreve a estrutura detalhada de colunas e comentários da tabela/view."""
        clean_name = table_name.strip().upper()
        target_owner = (
            owner or os.environ.get("ORACLE_DEFAULT_SCHEMA", "SGTPRD")
        ).upper()

        sql = (
            "SELECT c.COLUMN_ID, c.COLUMN_NAME, c.DATA_TYPE, "
            "       CASE "
            "         WHEN c.DATA_TYPE IN ('VARCHAR2', 'CHAR') THEN c.DATA_TYPE || '(' || c.DATA_LENGTH || ')' "
            "         WHEN c.DATA_TYPE = 'NUMBER' AND c.DATA_PRECISION IS NOT NULL "
            "              THEN 'NUMBER(' || c.DATA_PRECISION || ',' || NVL(c.DATA_SCALE, 0) || ')' "
            "         ELSE c.DATA_TYPE "
            "       END AS FORMATTED_TYPE, "
            "       c.NULLABLE, "
            "       comm.COMMENTS "
            "FROM ALL_TAB_COLUMNS c "
            "LEFT JOIN ALL_COL_COMMENTS comm "
            "       ON comm.OWNER = c.OWNER AND comm.TABLE_NAME = c.TABLE_NAME AND comm.COLUMN_NAME = c.COLUMN_NAME "
            "WHERE c.OWNER = :owner AND c.TABLE_NAME = :tbl "
            "ORDER BY c.COLUMN_ID"
        )

        conn, erro = self._conexao("Erro de conexão: ", tool_name="describe_table")
        if erro is not None:
            return erro

        cursor = self._abrir_cursor(conn)
        self._configurar_cursor(cursor)

        try:
            with call_deadline(conn, self.config.timeout, threading.Event()):
                cursor.execute(sql, {"owner": target_owner, "tbl": clean_name})
                rows = cursor.fetchall()
            if not rows:
                return {
                    "error": True,
                    "message": f"Objeto '{clean_name}' não encontrado no schema '{target_owner}'.",
                }

            return {
                "text": f"### Tabela: {target_owner}.{clean_name}\n\n"
                + self._render_markdown_table(CABECALHO_COLUNAS, _linhas_colunas(rows))
            }
        finally:
            with contextlib.suppress(Exception):
                cursor.close()
            self._liberar_conexao(conn)

    @_fronteira_de_ferramenta("Falha na verificação de conectividade com a Unifique: ")
    def check_connection(self) -> dict[str, Any]:
        """Testa conectividade e saúde com o Data Center da Unifique.

        Informa o modo ativo do driver (Thin, ou Thick com a versão do Oracle Client),
        o RTT medido só na consulta de teste (sem contar o tempo de conexão) e os
        parâmetros de WAN. `conn.version` vem do driver e não exige V$VERSION.
        """
        connect_start = time.perf_counter()
        conn, erro = self._conexao(
            "Erro de diagnóstico: ", tool_name="check_connection"
        )
        if erro is not None:
            return erro
        connect_ms = round((time.perf_counter() - connect_start) * 1000, 2)

        cursor = self._abrir_cursor(conn)
        query_start = time.perf_counter()
        try:
            with call_deadline(conn, self.config.timeout, threading.Event()):
                cursor.execute(
                    "SELECT SYS_CONTEXT('USERENV', 'CURRENT_USER'), "
                    "       SYS_CONTEXT('USERENV', 'DB_NAME'), "
                    "       SYS_CONTEXT('USERENV', 'SERVER_HOST') "
                    "FROM DUAL"
                )
                user, db_name, host = cursor.fetchone()
            rtt_ms = round((time.perf_counter() - query_start) * 1000, 2)
        finally:
            with contextlib.suppress(Exception):
                cursor.close()
            self._liberar_conexao(conn)

        driver = describe_driver_mode()
        report = [
            "### Status da Conexão Oracle (Data Center Unifique)",
            "- **Status:** Conectado com sucesso",
            f"- **Modo de Operação:** {driver.label}",
            f"- **SessionPool:** {self._descricao_pool()}",
            f"- **Versão Oracle (servidor):** {getattr(conn, 'version', 'N/D')}",
            f"- **Tempo de aquisição de sessão:** {connect_ms} ms",
            f"- **Latência (RTT, consulta de teste):** {rtt_ms} ms",
            f"- **Timeout por chamada:** {_descricao_timeout()}",
            f"- **Usuário:** `{user}`",
            f"- **Banco / Service:** `{db_name}`",
            f"- **Host Remoto:** `{host}`",
            f"- **DSN Resolvido:** `{self.config.dsn}`",
            f"- **TNS_ADMIN:** `{self.config.tns_admin}`",
        ]
        if driver.mode == "thick":
            report.append(f"- **Client Lib:** `{self.config.client_lib}`")
        report.append(
            "- **Configuração de WAN:** "
            f"arraysize={self.config.arraysize}, prefetchrows={self.config.arraysize}"
        )
        return {"text": "\n".join(report)}

    def _descricao_pool(self) -> str:
        """Estado do SessionPool para o relatório de check_connection."""
        status = (
            self.conn_mgr.get_pool_status()
            if hasattr(self.conn_mgr, "get_pool_status")
            else {"active": False}
        )
        if not status.get("active"):
            return "Inativo (Conexões avulsas dedicadas)"
        return (
            f"Ativo (Abertas: {status.get('open')}, "
            f"Ocupadas: {status.get('busy')}, Máximo: {status.get('max')})"
        )

    @staticmethod
    def _render_markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
        """Renderiza uma tabela Markdown formatada e alinhada."""
        if not headers:
            return "*(sem colunas)*"
        if not rows:
            header_line = "| " + " | ".join(str(h) for h in headers) + " |"
            sep_line = "| " + " | ".join("---" for _ in headers) + " |"
            return f"{header_line}\n{sep_line}\n*(0 linhas retornadas)*"

        str_rows = [[str(cell if cell is not None else "") for cell in r] for r in rows]
        widths = [len(str(h)) for h in headers]
        for r in str_rows:
            for i, cell in enumerate(r):
                if i < len(widths):
                    widths[i] = max(widths[i], len(cell))

        header_line = (
            "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
        )
        sep_line = (
            "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
        )
        data_lines = [
            "| "
            + " | ".join(
                r[i].ljust(widths[i]) if i < len(r) else "".ljust(widths[i])
                for i in range(len(headers))
            )
            + " |"
            for r in str_rows
        ]
        return "\n".join([header_line, sep_line] + data_lines)


class McpServer:
    """Servidor MCP JSON-RPC 2.0 sobre STDIO."""

    def __init__(self) -> None:
        self.config = load_config()
        self.conn_mgr = OracleConnectionManager(self.config)
        self.tools = OracleMcpTools(self.conn_mgr, self.config)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "execute_sql",
                "description": (
                    "Executa uma consulta SQL (SELECT ou WITH) no banco Oracle do ERP SGT "
                    "(Data Center Unifique) em modo estritamente Somente Leitura (Read-Only). "
                    "Cursores com arraysize/prefetchrows configurável (ORACLE_MCP_ARRAYSIZE, padrão 1000) e watchdog contra quedas."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "A consulta SQL (SELECT / WITH) a ser executada.",
                        },
                        "max_rows": {
                            "type": "integer",
                            "description": "Número máximo de linhas a retornar (default: 100, max: 5000).",
                            "default": 100,
                        },
                        "format": {
                            "type": "string",
                            "description": "Formato de saída: 'table' (Markdown) ou 'json'.",
                            "enum": ["table", "json"],
                            "default": "table",
                        },
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "get_query_plan",
                "description": (
                    "Gera o plano de execução (EXPLAIN PLAN / DBMS_XPLAN) para uma consulta SQL "
                    "sem executá-la no banco de dados."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "A consulta SQL cujo plano de execução será gerado.",
                        }
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "list_tables",
                "description": (
                    "Lista tabelas e views do banco Oracle com paginação e filtro opcional por nome ou schema."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Filtro de busca LIKE (ex: 'CAD_%', 'OB_%').",
                        },
                        "owner": {
                            "type": "string",
                            "description": "Schema proprietário (padrão: SGTPRD / usuário da conexão).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Máximo de objetos a retornar (default: 100, max: 500).",
                            "default": 100,
                        },
                    },
                },
            },
            {
                "name": "describe_table",
                "description": (
                    "Retorna a estrutura completa de colunas, tipos de dados, precisão, "
                    "nulidade e comentários de uma tabela ou view do Oracle."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Nome da tabela ou view (ex: 'CAD_PRODUTO').",
                        },
                        "owner": {
                            "type": "string",
                            "description": "Schema proprietário (opcional).",
                        },
                    },
                    "required": ["table_name"],
                },
            },
            {
                "name": "check_connection",
                "description": (
                    "Diagnóstico completo de conectividade e saúde com o Data Center da Unifique: "
                    "testa RTT/latência, modo do driver (Thin ou Thick), resolução TNS e versão do Oracle."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        # Mensagem sem "id" é notificação (JSON-RPC 2.0 §4.1): nunca recebe resposta,
        # nem de erro. Vem antes de tools/call: uma chamada de ferramenta sem id não
        # é executada (não há a quem devolver o resultado).
        if "id" not in req:
            return None

        if method == "tools/call":
            return self._responder_tools_call(req_id, params)

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.get_tool_definitions()},
            }

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            }

        return _erro_rpc(req_id, -32601, f"Método não suportado: '{method}'")

    def _despachos_ferramentas(
        self,
    ) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        """Ferramenta -> função que lê os argumentos do cliente e chama o OracleMcpTools."""
        return {
            "execute_sql": lambda a: self.tools.execute_sql(
                a.get("sql", ""), a.get("max_rows", 100), a.get("format", "table")
            ),
            "get_query_plan": lambda a: self.tools.get_query_plan(a.get("sql", "")),
            "list_tables": lambda a: self.tools.list_tables(
                a.get("pattern"), a.get("owner"), a.get("limit", 100)
            ),
            "describe_table": lambda a: self.tools.describe_table(
                a.get("table_name", ""), a.get("owner")
            ),
            "check_connection": lambda _a: self.tools.check_connection(),
        }

    def _responder_tools_call(self, req_id: Any, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            return _erro_rpc(
                req_id,
                -32602,
                "Parâmetros inválidos: 'params' deve ser um objeto JSON.",
            )
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _erro_rpc(
                req_id,
                -32602,
                "Parâmetros inválidos: 'arguments' deve ser um objeto JSON.",
            )
        # Nome não textual nunca chega ao dicionário (não é chave válida nem ferramenta).
        nome = tool_name if isinstance(tool_name, str) else ""
        despacho = self._despachos_ferramentas().get(nome) if nome else None
        if despacho is None:
            return _erro_rpc(req_id, -32601, f"Ferramenta desconhecida: '{tool_name}'")

        motivo = _motivo_argumentos_invalidos(nome, args)
        if motivo is not None:
            return _erro_rpc(
                req_id, -32602, f"Argumentos inválidos para '{nome}': {motivo}"
            )

        res = despacho(args)
        is_error = res.get("error", False)
        if is_error:
            text_out = f"[ERRO] {res.get('message', 'Erro desconhecido')}"
        else:
            text_out = (
                res["text"]
                if "text" in res
                else json.dumps(res, indent=2, ensure_ascii=False)
            )

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": text_out}],
                "isError": is_error,
            },
        }

    def _responder_seguro(self, req: Any) -> dict[str, Any] | None:
        """Nunca deixa uma requisição derrubar o loop STDIO: falha vira erro JSON-RPC -32603."""
        if not isinstance(req, dict):
            return _erro_rpc(
                None, -32600, "Requisição inválida: esperado um objeto JSON."
            )
        try:
            return self.handle_request(req)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log_stderr(f"Falha interna ao atender requisição: {exc}")
            return _erro_rpc(req.get("id"), -32603, f"Erro interno do servidor: {exc}")

    def run(self) -> None:
        """Loop principal do servidor MCP escutando JSON-RPC em STDIO."""
        log_stderr(
            f"Iniciando {SERVER_NAME} v{SERVER_VERSION} sobre STDIO (MCP 2024-11-05)..."
        )
        log_stderr(f"Alvo Oracle: DSN '{self.config.dsn}'.")
        if _erro_import_guard:
            log_stderr(
                f"Guard SQL não carregado ({_erro_import_guard}); consultas serão bloqueadas."
            )

        try:
            for line in sys.stdin:
                line_str = line.strip()
                if not line_str:
                    continue

                try:
                    req = json.loads(line_str)
                except json.JSONDecodeError as exc:
                    log_stderr(f"JSON inválido recebido: {exc}")
                    err_resp = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": "Parse error: JSON inválido",
                        },
                    }
                    sys.stdout.write(json.dumps(err_resp) + "\n")
                    sys.stdout.flush()
                    continue

                resp = self._responder_seguro(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                    sys.stdout.flush()

        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self.conn_mgr.close()
            log_stderr("Servidor MCP finalizado.")


def main() -> None:
    server = McpServer()
    server.run()


if __name__ == "__main__":
    main()
