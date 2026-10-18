# pylint: disable=import-error, wrong-import-position, protected-access
"""Testes de robustez do Servidor MCP Oracle (Tools/oracle/mcp_server.py).

Cada teste prova um defeito apontado na revisão: argumento não textual derrubava
o loop STDIO; o ping de reuso e as ferramentas não tinham prazo por chamada; a
mensagem de timeout prometia um limite total que o call_timeout não garante; e
ORACLE_MCP_TIMEOUT=0 desligava o prazo. Nenhum teste conecta ao Oracle.
"""

import functools
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import oracledb
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _ROOT / "Tools" / "oracle"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import mcp_server  # noqa: E402
from mcp_server import (  # noqa: E402
    DEFAULT_ARRAYSIZE,
    DEFAULT_TIMEOUT,
    McpServer,
    OracleConfig,
    OracleConnectionManager,
    OracleMcpTools,
    load_config,
)

pytestmark = pytest.mark.unitario

PRAZO_CONFIG = 10.0


def _config() -> OracleConfig:
    return OracleConfig(
        user="usuario_teste",
        password=os.environ.get("ORACLE_TEST_PASSWORD", "placeholder-de-teste"),
        dsn="dbprd",
        client_lib="oracle_client",
        tns_admin="oracle_client/Network/Admin",
        timeout=PRAZO_CONFIG,
        arraysize=1000,
    )


def _conexao_com_registro_de_prazo(registros: list[Any]) -> MagicMock:
    """Conexão dublê que anota `call_timeout` no momento de cada execute."""
    conn = MagicMock(name="conexao")
    cursor = MagicMock(name="cursor")
    cursor.description = [("X",)]
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = ("SGTPRD", "DBPRD", "HOST01")
    cursor.execute.side_effect = lambda *_a, **_k: registros.append(conn.call_timeout)
    conn.cursor.return_value = cursor
    return conn


@pytest.mark.parametrize(
    "ferramenta",
    ["list_tables", "describe_table", "get_query_plan", "check_connection"],
)
def test_ferramenta_aplica_prazo_por_chamada(ferramenta: str) -> None:
    registros: list[Any] = []
    conn = _conexao_com_registro_de_prazo(registros)
    mgr = MagicMock()
    mgr.get_connection.return_value = conn
    tools = OracleMcpTools(mgr, _config())
    chamadas = {
        "list_tables": (tools.list_tables, ()),
        "describe_table": (tools.describe_table, ("cad_x",)),
        "get_query_plan": (tools.get_query_plan, ("SELECT 1 FROM DUAL",)),
        "check_connection": (tools.check_connection, ()),
    }
    funcao, argumentos = chamadas[ferramenta]
    funcao(*argumentos)

    assert registros, "a ferramenta deveria ter executado SQL"
    assert all(valor == PRAZO_CONFIG * 1000 for valor in registros), registros


def test_ping_de_reuso_tem_prazo(monkeypatch: pytest.MonkeyPatch) -> None:
    registros: list[Any] = []
    conn = MagicMock(name="conexao")
    conn.ping.side_effect = lambda: registros.append(conn.call_timeout)
    # A sondagem do modo não pode abrir conexão real neste teste de ping.
    monkeypatch.setattr(
        mcp_server, "connect_adaptive", MagicMock(return_value=MagicMock())
    )
    mgr = OracleConnectionManager(_config())
    mgr._conn = conn  # pylint: disable=protected-access

    assert mgr.get_connection() is conn
    assert registros == [15000]


def test_timeout_de_execucao_diz_que_o_prazo_e_por_chamada() -> None:
    cursor = MagicMock(name="cursor")
    cursor.description = [("X",)]
    cursor.execute.side_effect = oracledb.DatabaseError(
        "DPY-4024: call timeout of 10000 ms exceeded"
    )
    conn = MagicMock(name="conexao")
    conn.cursor.return_value = cursor
    mgr = MagicMock()
    mgr.get_connection.return_value = conn
    resultado = OracleMcpTools(mgr, _config()).execute_sql("SELECT 1 FROM DUAL")

    assert resultado["error"] is True
    assert "uma chamada ao banco excedeu o limite de 10s" in resultado["message"]
    # Sessão cancelada no meio de um round-trip não volta ao pool.
    mgr.discard_connection.assert_called_once_with(conn)


def test_run_sobrevive_a_argumentos_nao_textuais(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    linhas = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "execute_sql",
                "arguments": {"sql": "SELECT 1 FROM DUAL", "max_rows": "dez"},
            },
        },
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": "nao-e-objeto"},
        {"jsonrpc": "2.0", "id": 4, "method": "ping"},
    ]
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO("\n".join(json.dumps(linha) for linha in linhas) + "\n"),
    )

    McpServer().run()

    saida = [json.loads(linha) for linha in capsys.readouterr().out.splitlines()]
    assert [r["id"] for r in saida] == [1, 3, 4]
    # Argumento de tipo errado é erro do cliente (-32602), não falha do servidor.
    assert saida[0]["error"]["code"] == -32602
    assert saida[1]["error"]["code"] == -32602
    assert saida[2] == {"jsonrpc": "2.0", "id": 4, "result": {}}


@pytest.mark.parametrize("variavel", ["ORACLE_MCP_TIMEOUT", "ORACLE_MCP_ARRAYSIZE"])
@pytest.mark.parametrize("valor", ["0", "-5"])
def test_load_config_valor_nao_positivo_usa_padrao(
    monkeypatch: pytest.MonkeyPatch, variavel: str, valor: str
) -> None:
    monkeypatch.setenv(variavel, valor)
    config = load_config()
    if variavel == "ORACLE_MCP_TIMEOUT":
        assert config.timeout == DEFAULT_TIMEOUT
    else:
        assert config.arraysize == DEFAULT_ARRAYSIZE


def test_guarda_indisponivel_bloqueia_por_padrao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_guard_sql", None)
    permitido, motivo = mcp_server.validate_read_only("SELECT 1 FROM DUAL")
    assert permitido is False
    assert "fail-closed" in motivo


def test_guarda_que_falha_bloqueia(monkeypatch: pytest.MonkeyPatch) -> None:
    class _GuardaQuebrada:
        @staticmethod
        def load_canonical() -> None:
            raise RuntimeError("canonico corrompido")

        @staticmethod
        def patch_canonical(canon: Any) -> Any:
            return canon

    monkeypatch.setattr(mcp_server, "_guard_sql", _GuardaQuebrada)
    permitido, motivo = mcp_server.validate_read_only("SELECT 1 FROM DUAL")
    assert permitido is False
    assert "canonico corrompido" in motivo


def test_guarda_bloqueia_funcao_com_efeito_colateral() -> None:
    permitido, _ = mcp_server.validate_read_only(
        "SELECT meu_pkg.grava_log('x') FROM dual"
    )
    assert permitido is False


def test_get_query_plan_nao_persiste_com_commit() -> None:
    cursor = MagicMock(name="cursor")
    cursor.fetchall.return_value = [("PLAN",)]
    conn = MagicMock(name="conexao")
    conn.cursor.return_value = cursor
    mgr = MagicMock()
    mgr.get_connection.return_value = conn

    OracleMcpTools(mgr, _config()).get_query_plan("SELECT 1 FROM DUAL")

    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()
    sqls = [chamada.args[0] for chamada in cursor.execute.call_args_list]
    assert any(sql.upper().startswith("EXPLAIN PLAN") for sql in sqls)


def test_get_query_plan_queda_de_sessao_fecha_conexao() -> None:
    cursor = MagicMock(name="cursor")
    cursor.execute.side_effect = Exception(
        "ORA-03113: end-of-file on communication channel"
    )
    conn = MagicMock(name="conexao")
    conn.cursor.return_value = cursor
    mgr = MagicMock()
    mgr.get_connection.return_value = conn

    resultado = OracleMcpTools(mgr, _config()).get_query_plan("SELECT 1 FROM DUAL")

    assert resultado["message"].startswith("Falha ao obter plano de execução: ")
    # Regressão: queda de uma sessão não derruba o pool inteiro. A conexão do pool que
    # caiu é descartada (não devolvida); o `None` do decorador só toca a dedicada.
    mgr.discard_connection.assert_any_call(conn)
    mgr.release_connection.assert_not_called()
    mgr.close.assert_not_called()


class _Lob:  # pylint: disable=too-few-public-methods
    """LOB falso: read(offset, amount) em caracteres, como o locator do driver."""

    def __init__(self, texto: str) -> None:
        self._texto = texto
        self.size = len(texto)

    def read(self, offset: int = 1, amount: int | None = None) -> str:
        inicio = offset - 1
        if amount is None:
            return self._texto[inicio:]
        return self._texto[inicio : inicio + amount]


class _BlobNaoLe:  # pylint: disable=too-few-public-methods
    """BLOB falso: qualquer leitura do conteúdo falha, para provar que não é lido."""

    size = 123

    def read(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("BLOB não deve ser lido")


def _cursor_com_coluna(tipo: Any, valor: Any) -> MagicMock:
    cursor = MagicMock(name="cursor")
    cursor.description = [("C", tipo)]
    cursor.fetchmany.return_value = [(valor,)]
    return cursor


def test_clob_grande_e_lido_com_teto_por_celula() -> None:
    cursor = _cursor_com_coluna(oracledb.DB_TYPE_CLOB, _Lob("x" * 9000))
    conn = MagicMock(name="conexao")
    conn.cursor.return_value = cursor
    mgr = MagicMock()
    mgr.get_connection.return_value = conn

    resultado = OracleMcpTools(mgr, _config()).execute_sql(
        "SELECT 1 FROM DUAL", output_format="json"
    )

    valor = resultado["data"][0]["C"]
    limite = mcp_server.LIMITE_CLOB_CARACTERES
    assert valor.startswith("x" * limite)
    assert "CLOB truncado" in valor
    assert len(valor) < 9000


def test_blob_vira_marcador_sem_ler_o_conteudo() -> None:
    cursor = _cursor_com_coluna(oracledb.DB_TYPE_BLOB, _BlobNaoLe())
    conn = MagicMock(name="conexao")
    conn.cursor.return_value = cursor
    mgr = MagicMock()
    mgr.get_connection.return_value = conn

    resultado = OracleMcpTools(mgr, _config()).execute_sql(
        "SELECT 1 FROM DUAL", output_format="json"
    )

    assert resultado["data"][0]["C"] == "<blob 123 bytes>"


def test_rollback_roda_com_prazo_por_chamada() -> None:
    registros: list[Any] = []
    conn = MagicMock(name="conexao")
    conn.cursor.return_value.fetchall.return_value = [("PLAN",)]
    conn.rollback.side_effect = lambda: registros.append(conn.call_timeout)
    mgr = MagicMock()
    mgr.get_connection.return_value = conn

    OracleMcpTools(mgr, _config()).get_query_plan("SELECT 1 FROM DUAL")

    assert registros == [mcp_server.PRAZO_ROLLBACK_SEGUNDOS * 1000]


def test_rollback_que_falha_descarta_a_conexao() -> None:
    conn = MagicMock(name="conexao")
    conn.cursor.return_value.fetchall.return_value = [("PLAN",)]
    conn.rollback.side_effect = RuntimeError("socket travado")
    mgr = MagicMock()
    mgr.get_connection.return_value = conn

    resultado = OracleMcpTools(mgr, _config()).get_query_plan("SELECT 1 FROM DUAL")

    assert resultado == {"text": "PLAN"}
    mgr.discard_connection.assert_called_once_with(conn)
    mgr.close.assert_not_called()
    mgr.release_connection.assert_not_called()


def test_falha_de_conexao_avulsa_recusa_novas_tentativas_na_janela(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[int] = []

    def _conexao_fora_do_ar(_funcao: Any, seconds: float) -> None:
        chamadas.append(1)
        raise TimeoutError(f"sem resposta em {seconds} s")

    monkeypatch.setattr(mcp_server, "connect_within", _conexao_fora_do_ar)
    mgr = OracleConnectionManager(_config())
    mgr._pool_failed = True  # pylint: disable=protected-access

    with pytest.raises(TimeoutError):
        mgr.get_connection()
    with pytest.raises(ConnectionError, match="recusada por 30 s"):
        mgr.get_connection()

    assert len(chamadas) == 1, "a segunda chamada não deveria tentar conectar"


def test_falha_de_conexao_avulsa_volta_a_tentar_apos_a_janela(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[int] = []

    def _conexao_fora_do_ar(_funcao: Any, seconds: float) -> None:
        chamadas.append(1)
        raise TimeoutError(f"sem resposta em {seconds} s")

    monkeypatch.setattr(mcp_server, "connect_within", _conexao_fora_do_ar)
    monkeypatch.setattr(mcp_server, "JANELA_FALHA_CONEXAO_SEGUNDOS", 0.0)
    mgr = OracleConnectionManager(_config())
    mgr._pool_failed = True  # pylint: disable=protected-access

    for _ in range(2):
        with pytest.raises(TimeoutError):
            mgr.get_connection()

    assert len(chamadas) == 2


class _GuardaContavel:  # pylint: disable=too-few-public-methods
    """Guard falso que conta quantas vezes o canônico é carregado."""

    def __init__(self) -> None:
        self.cargas = 0

    def load_canonical(self) -> object:
        self.cargas += 1
        return object()

    def patch_canonical(self, _canon: Any) -> Any:
        class _Canon:  # pylint: disable=too-few-public-methods
            @staticmethod
            def classificar(_sql: str, **_kwargs: Any) -> dict[str, Any]:
                return {"permitido": True, "classe": "leitura", "motivos": []}

        return _Canon()


def test_canonico_do_guard_e_carregado_uma_vez_por_modulo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guarda = _GuardaContavel()
    monkeypatch.setattr(mcp_server, "_guard_sql", guarda)
    mcp_server._cache_canonico.clear()  # pylint: disable=protected-access

    assert mcp_server.validate_read_only("SELECT 1 FROM DUAL") == (True, "")
    assert mcp_server.validate_read_only("SELECT 2 FROM DUAL") == (True, "")

    assert guarda.cargas == 1


def test_causa_do_import_do_guard_aparece_na_mensagem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_guard_sql", None)
    monkeypatch.setattr(
        mcp_server,
        "_erro_import_guard",
        "ModuleNotFoundError: No module named 'guard_sql'",
    )

    permitido, motivo = mcp_server.validate_read_only("SELECT 1 FROM DUAL")

    assert permitido is False
    assert "fail-closed" in motivo
    assert "No module named 'guard_sql'" in motivo


def test_argumento_de_tipo_errado_vira_32602() -> None:
    servidor = McpServer()

    bool_no_max_rows = servidor._responder_tools_call(
        7,
        {
            "name": "execute_sql",
            "arguments": {"sql": "SELECT 1 FROM DUAL", "max_rows": True},
        },
    )
    formato_fora_do_enum = servidor._responder_tools_call(
        8,
        {
            "name": "execute_sql",
            "arguments": {"sql": "SELECT 1 FROM DUAL", "format": "csv"},
        },
    )
    params_nulos = servidor._responder_tools_call(9, None)

    assert bool_no_max_rows["error"]["code"] == -32602
    assert formato_fora_do_enum["error"]["code"] == -32602
    assert params_nulos["error"]["code"] == -32602


def test_requisicao_nao_objeto_vira_32600() -> None:
    resposta = McpServer()._responder_seguro(
        [1, 2, 3]
    )  # pylint: disable=protected-access

    assert resposta is not None
    assert resposta["error"]["code"] == -32600
    assert resposta["id"] is None


# ------------------------------------------ função sem parênteses no guard (achado 1)

SQL_COM_FUNCAO = "SELECT SGTPRD.PKG.FN FROM DUAL"


def _mgr_com_conexao(conn: Any) -> MagicMock:
    mgr = MagicMock()
    mgr.get_connection.return_value = conn
    return mgr


def _conexao_com_cursor(cursor: MagicMock) -> MagicMock:
    conn = MagicMock(name="conexao")
    conn.cursor.return_value = cursor
    return conn


def _sqls_executados(cursor: MagicMock) -> list[str]:
    return [str(chamada.args[0]) for chamada in cursor.execute.call_args_list]


def test_funcao_sem_parenteses_bloqueada_sem_executar_o_sql() -> None:
    """Regressão (achado 1): `SELECT PKG.FN FROM DUAL` passava no guard e executava a função.

    A consulta de verificação de catálogo acusa a função, e o SQL do usuário não roda.
    """
    cursor = MagicMock(name="cursor")
    cursor.description = [("X", None)]
    cursor.fetchall.return_value = [("SGTPRD", "FN", "FUNCTION")]
    conn = _conexao_com_cursor(cursor)
    mgr = _mgr_com_conexao(conn)

    resultado = OracleMcpTools(mgr, _config()).execute_sql(SQL_COM_FUNCAO)

    assert resultado["error"] is True
    assert resultado["message"].startswith(
        "Segurança MCP (Read-Only Violation): a consulta referencia função"
    )
    assert "SGTPRD.FN (FUNCTION)" in resultado["message"]
    executados = _sqls_executados(cursor)
    assert len(executados) == 1
    assert "ALL_OBJECTS" in executados[0].upper()
    # Sessão saudável: a conexão volta ao pool.
    mgr.release_connection.assert_called_once_with(conn)
    mgr.discard_connection.assert_not_called()


def test_verificacao_sem_linhas_executa_a_consulta() -> None:
    cursor = MagicMock(name="cursor")
    cursor.description = [("X", None)]
    cursor.fetchall.return_value = []
    cursor.fetchmany.return_value = [(1,)]
    mgr = _mgr_com_conexao(_conexao_com_cursor(cursor))

    resultado = OracleMcpTools(mgr, _config()).execute_sql(SQL_COM_FUNCAO)

    assert "text" in resultado
    assert _sqls_executados(cursor)[-1] == SQL_COM_FUNCAO


def test_falha_da_verificacao_bloqueia_a_consulta_fail_closed() -> None:
    cursor = MagicMock(name="cursor")
    cursor.execute.side_effect = Exception("ORA-00942: tabela ou view nao existe")
    mgr = _mgr_com_conexao(_conexao_com_cursor(cursor))

    resultado = OracleMcpTools(mgr, _config()).execute_sql(SQL_COM_FUNCAO)

    assert resultado["error"] is True
    assert "ORA-00942" in resultado["message"]
    assert SQL_COM_FUNCAO not in _sqls_executados(cursor)


def test_mais_de_quinhentos_nomes_bloqueia_sem_conectar() -> None:
    """Acima do limite da verificação não há como provar a ausência de função."""
    colunas = ", ".join(f"C{i}" for i in range(mcp_server.LIMITE_NOMES_VERIFICADOS + 1))
    mgr = MagicMock()

    resultado = OracleMcpTools(mgr, _config()).execute_sql(
        f"SELECT {colunas} FROM DUAL"  # nosec B608 - colunas sintéticas C0..C500; nada vai ao banco
    )

    assert resultado["error"] is True
    assert "fail-closed" in resultado["message"]
    mgr.get_connection.assert_not_called()


# ------------------------------------------------------ stdin UTF-8 (achado 2)


def test_stdin_do_processo_aceita_utf8_com_acento() -> None:
    """Regressão (achado 2): o stdin em pipe no Windows ficava em cp1252 e corrompia acentos.

    Roda o servidor como processo, sem PYTHONUTF8/PYTHONIOENCODING, para medir o
    comportamento real do stdin. Nenhum teste conecta ao Oracle.
    """
    requisicao = {"jsonrpc": "2.0", "id": 1, "method": "método_ção"}
    entrada = json.dumps(requisicao, ensure_ascii=False).encode("utf-8") + b"\n"
    ambiente = {
        chave: valor
        for chave, valor in os.environ.items()
        if chave not in ("PYTHONUTF8", "PYTHONIOENCODING")
    }

    processo = subprocess.run(
        [sys.executable, str(_TOOLS / "mcp_server.py")],
        input=entrada,
        capture_output=True,
        timeout=120,
        check=False,
        env=ambiente,
    )

    assert processo.returncode == 0
    linhas = processo.stdout.decode("utf-8").splitlines()
    resposta = json.loads(next(linha for linha in linhas if linha.startswith("{")))
    assert resposta["error"]["message"] == "Método não suportado: 'método_ção'"


# -------------------------------------------- queda e pool (achado 7)


@pytest.mark.parametrize(
    "ferramenta", ["list_tables", "describe_table", "check_connection"]
)
def test_queda_na_ferramenta_descarta_a_conexao_do_pool(ferramenta: str) -> None:
    """Regressão (achado 7): a conexão que caiu sai do pool; não volta a ele."""
    cursor = MagicMock(name="cursor")
    cursor.execute.side_effect = Exception(
        "ORA-03113: end-of-file on communication channel"
    )
    conn = _conexao_com_cursor(cursor)
    mgr = _mgr_com_conexao(conn)
    tools = OracleMcpTools(mgr, _config())
    chamadas: dict[str, Callable[[], dict[str, Any]]] = {
        "list_tables": tools.list_tables,
        "describe_table": functools.partial(tools.describe_table, "cad_x"),
        "check_connection": tools.check_connection,
    }

    resultado = chamadas[ferramenta]()

    assert resultado["error"] is True
    mgr.discard_connection.assert_called_once_with(conn)
    mgr.release_connection.assert_not_called()


def test_cursor_que_falha_por_queda_descarta_a_conexao() -> None:
    conn = MagicMock(name="conexao")
    conn.cursor.side_effect = Exception("DPY-1001: not connected")
    mgr = _mgr_com_conexao(conn)

    resultado = OracleMcpTools(mgr, _config()).list_tables()

    assert resultado["error"] is True
    mgr.discard_connection.assert_called_once_with(conn)
    mgr.release_connection.assert_not_called()


def test_describe_table_sem_falha_devolve_a_conexao_ao_pool() -> None:
    cursor = MagicMock(name="cursor")
    cursor.fetchall.return_value = []
    conn = _conexao_com_cursor(cursor)
    mgr = _mgr_com_conexao(conn)

    OracleMcpTools(mgr, _config()).describe_table("cad_x")

    mgr.release_connection.assert_called_once_with(conn)
    mgr.discard_connection.assert_not_called()


# ------------------------------------------------- `;` final e cursor (achados 12 e 14)


def test_ponto_e_virgula_final_nao_chega_ao_oracle() -> None:
    """Regressão (achado 12): o guard aceita `;` final, mas o Oracle rejeita (ORA-00933)."""
    cursor = MagicMock(name="cursor")
    cursor.description = [("X", None)]
    cursor.fetchmany.return_value = [(1,)]
    mgr = _mgr_com_conexao(_conexao_com_cursor(cursor))

    OracleMcpTools(mgr, _config()).execute_sql("SELECT 1 FROM DUAL;  ;")

    assert _sqls_executados(cursor)[-1] == "SELECT 1 FROM DUAL"


def test_get_query_plan_tira_ponto_e_virgula_antes_do_explain() -> None:
    cursor = MagicMock(name="cursor")
    cursor.fetchall.return_value = [("PLAN",)]
    mgr = _mgr_com_conexao(_conexao_com_cursor(cursor))

    OracleMcpTools(mgr, _config()).get_query_plan("SELECT 1 FROM DUAL;")

    assert _sqls_executados(cursor)[0].endswith("FOR SELECT 1 FROM DUAL")


def test_arraysize_acompanha_max_rows_mais_uma() -> None:
    """Regressão (achado 14): buscar max_rows + 1 não pode pedir lote maior que isso."""
    cursor = MagicMock(name="cursor")
    cursor.description = [("X", None)]
    cursor.fetchmany.return_value = [(1,)]
    mgr = _mgr_com_conexao(_conexao_com_cursor(cursor))

    OracleMcpTools(mgr, _config()).execute_sql("SELECT 1 FROM DUAL", max_rows=2)

    assert cursor.arraysize == 3
    assert cursor.prefetchrows == 3
