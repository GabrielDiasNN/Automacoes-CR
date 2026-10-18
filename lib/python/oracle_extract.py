"""Núcleo compartilhado de extração Oracle: credenciais, fetch, serialização e idempotência.

Extrai o padrão repetido nos 6 scripts de extração de domínio (Receitas
Emitidas, OBs Paradas Fase, Montagem de Terceirizados, Receitas Bloqueadas,
OBs Fluxo Sem Tingimento, OBs Restrição Branco): resolver credenciais do
ambiente, conectar via Thick Mode, buscar linhas em lotes e normalizar valores
(datetime -> isoformat, strings -> strip).

`compute_hash`/`read_last_hash`/`write_state_tmp` cobrem apenas o padrão de
idempotência por HASH DE LOTE, usado por Receitas Emitidas e OBs Paradas Fase.
Receitas Bloqueadas usa `compute_hash` mas grava o state por outro caminho
(não usa `write_state_tmp` — ver comentário em
`Receitas Bloqueadas/processar_receitas.py`). Montagem de Terceirizados não
usa nenhuma das três: sua idempotência é por canal, via
`lib/Lib-Idempotency.psm1` (PowerShell) — ver `docs/architecture-standard.md`
§ Idempotência de Entrega e Bootstrap Python das Automações. OFST-06 e ORB-07
têm idempotência por OB individual (schema de state mais rico, com reservas
de estoque) e implementam essa parte em `validators.py`/`extract_*.py` — ver
CONTEXT.md de cada uma para o porquê.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import oracledb
from oracle_client import (
    DRIVER_MODE_THICK,
    aplicar_metadados_oci,
    connect_adaptive,
    get_driver_mode,
    init_oracle_thick_mode,
)

LogFn = Callable[..., None]


@dataclass(frozen=True)
class OracleCredentials:
    user: str
    password: str
    dsn: str
    client_lib: str
    tns_admin: str | None


def instrument_oracle_session(
    connection: Any,
    automacao: str,
    exec_id: str,
    action: str = "FETCH",
    log_fn: LogFn | None = None,
) -> None:
    """Instrumenta a sessão ativa com metadados nativos OCI na V$SESSION do Oracle 19c.

    Falha ao instrumentar não bloqueia a extração: é só registrada em DEBUG.
    """
    clean_auto = (automacao or "Extracao").strip()
    clean_exec = (exec_id or "UNKNOWN").strip()
    sanitized_op = "".join(c if c.isalnum() else "_" for c in clean_auto).upper()
    erro = aplicar_metadados_oci(
        connection,
        modulo=f"HubAutomacoes.{clean_auto}",
        acao=f"{action}:{clean_exec[:8]}",
        identificador=f"AUTO:{clean_auto[:20]}:{clean_exec[:8]}",
        db_op=f"OP_{sanitized_op}",
    )
    if erro and log_fn:
        log_fn(f"Aviso não-bloqueante ao instrumentar sessão OCI: {erro}", "DEBUG")


def _probe_sem_rota(host: str, port: int, amostras: int, erro: str) -> dict[str, Any]:
    """Resultado do probe quando nem a resolução do nome funcionou."""
    return {
        "host": host,
        "port": port,
        "reachable": False,
        "rtt_ms": None,
        "min_rtt_ms": None,
        "max_rtt_ms": None,
        "packet_loss_pct": 100.0,
        "samples_ok": 0,
        "samples_total": amostras,
        "error": erro,
    }


def probe_wan_health(
    host: str, port: int = 1521, samples: int = 3, timeout: float = 1.0
) -> dict[str, Any]:
    """Testa a saúde da rota WAN via TCP ping de abertura de socket.

    Mede latência média (RTT), desvio e taxa de sucesso em milissegundos.
    Execução rápida (< 50 ms no link normal). Não levanta exceção: cada amostra tem
    prazo de `timeout` s, e a resolução do nome não tem prazo próprio (DNS lento pode
    atrasar a chamada). O chamador decide o que fazer com o resultado.
    """
    total_samples = max(1, samples)
    rtts: list[float] = []
    failures = 0
    last_error: str | None = None

    # Resolve o nome uma vez, fora do laço: getaddrinfo não respeita settimeout, e
    # com DNS lento cada amostra esperaria o resolver inteiro.
    try:
        destino = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0]
    except OSError as exc:
        return _probe_sem_rota(
            host, port, total_samples, f"resolução de nome falhou: {exc}"
        )

    for _ in range(total_samples):
        sock = socket.socket(destino[0], socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.perf_counter()
        try:
            sock.connect(destino[4])
            rtts.append((time.perf_counter() - start) * 1000.0)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            failures += 1
            last_error = str(exc)
        finally:
            with contextlib.suppress(Exception):
                sock.close()

    success_count = len(rtts)
    loss_pct = (failures / total_samples) * 100.0
    avg_rtt = (sum(rtts) / success_count) if rtts else None

    return {
        "host": host,
        "port": port,
        "reachable": success_count > 0,
        "rtt_ms": round(avg_rtt, 2) if avg_rtt is not None else None,
        "min_rtt_ms": round(min(rtts), 2) if rtts else None,
        "max_rtt_ms": round(max(rtts), 2) if rtts else None,
        "packet_loss_pct": round(loss_pct, 1),
        "samples_ok": success_count,
        "samples_total": total_samples,
        "error": last_error,
    }


def _extrair_host_porta_dsn(
    dsn: str, default_host: str = "", default_port: int = 1521
) -> tuple[str, int]:
    """Extrai host e porta de uma string DSN (Easy Connect, Easy Connect Plus ou TNS).

    Sem host no DSN nem em ORACLE_HOST devolve `default_host` (vazio por padrão):
    não há IP fixo de fallback, e quem chama não sonda nada sem host.
    """
    # A query string sai primeiro: um parâmetro como `wallet_location=file://...`
    # não pode ser confundido com o protocolo do endereço.
    clean = dsn.strip().split("?")[0]
    # Easy Connect Plus aceita protocolo (`tcps://`) e `//` antes do host; IPv6 vem
    # entre colchetes. Sem tirar o prefixo, "tcps://h:2484/x" virava host "tcps".
    if "://" in clean:
        clean = clean.split("://", 1)[1]
    clean = clean.lstrip("/")
    if ":" in clean:
        endereco = clean.split("/")[0]
        if endereco.startswith("["):
            host, _, resto = endereco[1:].partition("]")
            porta_txt = resto.lstrip(":")
        else:
            host, _, porta_txt = endereco.partition(":")
        try:
            port = int(porta_txt.strip()) if porta_txt.strip() else default_port
        except ValueError:
            port = default_port
        return host.strip() or default_host, port

    env_host = os.environ.get("ORACLE_HOST")
    if env_host:
        return env_host.strip(), default_port
    return default_host, default_port


def connect_from_creds(
    creds: OracleCredentials, log_fn: LogFn | None = None
) -> oracledb.Connection:
    """`connect_adaptive` com os campos de `OracleCredentials` (fonte única da chamada)."""
    return connect_adaptive(
        user=creds.user,
        password=creds.password,
        dsn=creds.dsn,
        client_lib=creds.client_lib,
        tns_admin=creds.tns_admin,
        log_fn=log_fn or (lambda *_a, **_k: None),
    )


def resolve_oracle_credentials(
    log: LogFn,
    exec_id: str,
    *,
    default_dsn: str = "dbprd",
    require_tns_admin: bool = False,
    force_dsn: str | None = None,
) -> OracleCredentials | None:
    """Le e valida as credenciais Oracle do ambiente. Retorna None (e loga o motivo) se invalidas.

    `force_dsn` ignora ORACLE_CONNECT_STRING e usa sempre o valor informado
    (contrato de scripts que resolvem DSN via TNS alias fixo, ex.: Montagem
    de Terceirizados usa sempre "dbprd" independente do .env).

    Formatos de DSN suportados integralmente:
    - Alias TNS simples (ex.: "dbprd")
    - Easy Connect tradicional (ex.: "host:1521/service_name")
    - Easy Connect Plus nativo Oracle 19c com parâmetros de resiliência WAN
      (ex.: "host:1521/dbprd?transport_connect_timeout=5&retry_count=3&retry_delay=2&sdu=65535")
    """
    user = os.environ.get("ORACLE_READONLY_USER")
    password = os.environ.get("ORACLE_READONLY_PASSWORD")
    raw_dsn = (
        force_dsn
        if force_dsn is not None
        else os.environ.get("ORACLE_CONNECT_STRING", default_dsn)
    )
    dsn = (raw_dsn or "").strip()
    client_lib = os.environ.get("ORACLE_CLIENT_LIB_DIR") or os.environ.get(
        "ORACLE_CLIENT_PATH"
    )
    tns_admin = os.environ.get("TNS_ADMIN")

    if not user or not password:
        log("Credenciais Oracle ausentes no ambiente.", "ERROR", exec_id)
        return None
    if not dsn:
        # DSN vazio (ORACLE_CONNECT_STRING= ou force_dsn="") é configuração errada:
        # cair em silêncio no padrão apontaria para produção sem ninguém pedir.
        log("DSN Oracle vazio (ORACLE_CONNECT_STRING ou force_dsn).", "ERROR", exec_id)
        return None
    # Só o Thick Mode explícito exige o Client já no bootstrap. No modo auto (Thin) a
    # biblioteca só é usada no fallback do verificador legado, que valida o caminho
    # ao ativar o Thick e falha com orientação (oracle_client.init_oracle_thick_mode).
    if get_driver_mode() == DRIVER_MODE_THICK and (
        not client_lib or not os.path.exists(client_lib)
    ):
        log(
            "ORACLE_CLIENT_LIB_DIR invalido (obrigatorio com ORACLE_DRIVER_MODE=thick).",
            "ERROR",
            exec_id,
        )
        return None
    if client_lib and not os.path.exists(client_lib):
        log(
            "ORACLE_CLIENT_LIB_DIR inexistente: Thin segue; o fallback Thick falhara se for preciso.",
            "WARN",
            exec_id,
        )
    if require_tns_admin and not tns_admin:
        log("TNS_ADMIN ausente no ambiente.", "ERROR", exec_id)
        return None

    return OracleCredentials(
        user=user,
        password=password,
        dsn=dsn,
        client_lib=client_lib or "",
        tns_admin=tns_admin,
    )


def init_thick_mode(creds: OracleCredentials, log: LogFn, exec_id: str) -> None:
    """Ativa o Thick Mode só com `ORACLE_DRIVER_MODE=thick`.

    No padrão `auto` nada é ativado aqui: cada conexão tenta Thin Mode e recorre
    ao Thick Mode só se o servidor exigir o verificador legado (ver
    `oracle_client.connect_adaptive`). A função continua existindo porque os
    extratores a chamam no bootstrap.
    """
    if get_driver_mode() != DRIVER_MODE_THICK:
        log(
            "Modo Oracle: auto (Thin Mode; Thick só se o servidor exigir verificador legado).",
            "INFO",
            exec_id,
        )
        return
    init_oracle_thick_mode(
        creds.client_lib,
        creds.tns_admin,
        lambda msg, lvl="INFO": log(msg, lvl, exec_id),
    )


def _nome_da_automacao(automacao: str | None) -> str:
    """Nome para a V$SESSION: argumento, depois o ambiente, depois um padrão."""
    return (
        automacao
        or os.environ.get("HUB_AUTOMATION")
        or os.environ.get("AUTOMATION_NAME")
        or "Extracao"
    )


def _registrar_saude_wan(dsn: str, tamanho: int, log: LogFn, exec_id: str) -> None:
    """Pré-voo de WAN: só registra a saúde da rota. Nunca bloqueia nem muda o lote.

    O lote pedido é mantido de propósito: em link lento, lote menor multiplica os
    round-trips de fetch e alonga a consulta, que é o oposto do desejado numa rede
    que derruba sessões em poucos segundos. Uma amostra só, para não somar conexões
    TCP extras no listener a cada extração.
    """
    if ":" not in dsn and not os.environ.get("ORACLE_HOST"):
        # Alias TNS sem host conhecido: medir o IP padrão não diria nada da rota real.
        return
    try:
        probe_host, probe_port = _extrair_host_porta_dsn(dsn)
        if not probe_host:
            return
        probe = probe_wan_health(probe_host, probe_port, samples=1, timeout=0.5)
        if not (probe.get("reachable") and probe.get("rtt_ms") is not None):
            return
        rtt = probe["rtt_ms"]
        loss = probe.get("packet_loss_pct", 0.0)
        if rtt > 80.0:
            log(
                f"WAN degradada: {probe_host}:{probe_port} RTT {rtt:.1f}ms (lote mantido em {tamanho}).",
                "WARN",
                exec_id,
            )
            return
        log(
            f"Telemetria WAN saudável: {probe_host}:{probe_port} RTT {rtt:.1f}ms (perda: {loss:.0f}%).",
            "DEBUG",
            exec_id,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log(f"Aviso não-bloqueante no pre-flight WAN: {exc}", "DEBUG", exec_id)


def fetch_all(  # pylint: disable=too-many-arguments
    creds: OracleCredentials,
    sql: str,
    exec_id: str,
    log: LogFn,
    *,
    batch_size: int = 5000,
    cursor_arraysize: int | None = None,
    params: dict[str, Any] | None = None,
    automacao: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Conecta, executa a query e retorna (colunas, linhas) buscadas em lotes.

    Sem decorator de retry proprio: cada script decora a chamada com o
    make_oracle_retry() configurado para o seu proprio perfil de resiliencia.

    `params` sao bind variables passadas ao cursor. Valores SEMPRE via bind —
    nunca interpolados na string SQL.

    `batch_size` tambem define o `arraysize` implicito do cursor quando
    `cursor_arraysize` nao e passado explicitamente (sincroniza o tamanho do
    lote de `fetchmany()` com o arraysize do driver, evitando round-trips
    extras). Valores muito grandes de `batch_size` podem, por isso, inflar o
    consumo de memoria por round-trip em queries com colunas largas
    (CLOB/BLOB/LONG) — hoje nao e um problema pratico, pois os chamadores
    usam `batch_size` entre 1000 e 5000 e nenhuma query envolvida traz essas
    colunas.

    `automacao` define o nome da automação para observabilidade OCI (V$SESSION).
    Se omitido, recupera de HUB_AUTOMATION ou AUTOMATION_NAME do ambiente.
    """
    # O pré-voo de WAN roda antes de conectar: a rede derruba sessões ociosas em
    # poucos segundos, então a sessão não pode esperar pelo probe.
    tamanho_pedido = cursor_arraysize if cursor_arraysize is not None else batch_size
    _registrar_saude_wan(creds.dsn, tamanho_pedido, log, exec_id)
    effective_size = tamanho_pedido

    log(f"Conectando ao Oracle (DSN: {creds.dsn})...", "INFO", exec_id)
    connection: oracledb.Connection = connect_adaptive(
        user=creds.user,
        password=creds.password,
        dsn=creds.dsn,
        client_lib=creds.client_lib,
        tns_admin=creds.tns_admin,
        log_fn=lambda msg, lvl="INFO": log(msg, lvl, exec_id),
    )

    instrument_oracle_session(
        connection,
        _nome_da_automacao(automacao),
        exec_id,
        "FETCH",
        lambda msg, lvl="DEBUG": log(msg, lvl, exec_id),
    )

    with connection:
        cursor = connection.cursor()

        # Sincroniza arraysize e prefetchrows com o batch_size efetivo:
        # - prefetchrows traz o 1º lote inteiro já junto com a resposta do execute() (0 round-trips de fetch)
        # - arraysize garante que lotes subsequentes venham em blocos únicos de 64KB (SDU)
        cursor.arraysize = effective_size
        cursor.prefetchrows = effective_size
        cursor.execute(sql, params or {})
        if not cursor.description:
            return [], []
        columns = [col[0] for col in cursor.description]
        rows: list[Any] = []
        while True:
            batch = cursor.fetchmany(effective_size)
            if not batch:
                break
            rows.extend(batch)
        log(
            f"Query executada com sucesso. Linhas retornadas: {len(rows)}",
            "INFO",
            exec_id,
        )
        return columns, rows


def serialize_rows(
    columns: list[str],
    rows: list[Any],
    *,
    sort_key: Callable[[dict[str, Any]], Any] | None = None,
) -> list[dict[str, Any]]:
    """Converte linhas Oracle em dicts, normalizando datetime (isoformat) e strings (strip).

    Nomes de coluna repetidos levantam ValueError: num dict, a segunda coluna
    sobrescreveria a primeira sem aviso. Use alias único na consulta.
    """
    if len(set(columns)) != len(columns):
        repetidas = sorted({nome for nome in columns if columns.count(nome) > 1})
        raise ValueError(
            f"Colunas com nome repetido na consulta: {', '.join(repetidas)}. "
            "Use alias único para cada coluna."
        )
    data: list[dict[str, Any]] = []
    for row in rows:
        # `strict=True`: colunas e valores vêm do mesmo cursor e devem ter o
        # mesmo tamanho. Divergência indica cursor corrompido — melhor falhar
        # alto que gerar registros silenciosamente truncados.
        record: dict[str, Any] = dict(zip(columns, row, strict=True))
        for key, value in record.items():
            if isinstance(value, datetime):
                record[key] = value.isoformat()
            elif isinstance(value, str) and value:
                record[key] = value.strip()
        data.append(record)
    if sort_key is not None:
        data.sort(key=sort_key)
    return data


def compute_hash(data: Any) -> str:
    """Calcula o sha256 hex de `data` serializado como JSON deterministico (sort_keys)."""
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_last_hash(state_path: str) -> str:
    """Le o last_hash do state.json.

    Retorna "" se o arquivo não existe, não pode ser lido ou tem JSON corrompido (o
    extrator trata como primeira execução). Levanta ValueError quando o JSON é válido
    mas a raiz não é um objeto, e UnicodeDecodeError quando o arquivo não é UTF-8:
    esses casos indicam arquivo alterado à mão ou erro de programação, e não devem
    virar primeira execução em silêncio.
    """
    if not os.path.exists(state_path):
        return ""
    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        raise ValueError(f"state.json em {state_path} deve ser um objeto JSON.")
    return str(data.get("last_hash", ""))


def write_state_tmp(state_path: str, current_hash: str) -> None:
    """Escreve state.json.tmp com o hash atual. O commit final e responsabilidade do run.ps1."""
    state_tmp_path = state_path + ".tmp"
    with open(state_tmp_path, "w", encoding="utf-8") as f:
        json.dump(
            {"last_hash": current_hash, "updated_at": datetime.now().isoformat()},
            f,
            ensure_ascii=False,
        )
