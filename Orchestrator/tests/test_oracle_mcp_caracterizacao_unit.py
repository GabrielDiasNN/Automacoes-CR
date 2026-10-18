# pylint: disable=import-error, wrong-import-position, protected-access
"""Testes de caracterização do Servidor MCP Oracle (Tools/oracle/mcp_server.py).

Fixam o comportamento observável atual (formatos de saída, mensagens de erro,
códigos JSON-RPC, limites e o loop STDIO) antes de qualquer refatoração. Se um
destes testes falhar depois de uma mudança, a mudança alterou algo visível para
quem usa o MCP: isso é regressão, não ajuste de teste.

Nenhum teste conecta ao Oracle: conexões e cursores são dublês.
"""

import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _ROOT / "Tools" / "oracle"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from mcp_server import (  # noqa: E402
    DEFAULT_TIMEOUT,
    DEFAULT_TNS_ADMIN,
    McpServer,
    OracleConfig,
    OracleConnectionManager,
    OracleMcpTools,
    load_config,
    validate_read_only,
)

pytestmark = pytest.mark.unitario


def _config(**overrides: Any) -> OracleConfig:
    valores: dict[str, Any] = {
        "user": "usuario_teste",
        "password": os.environ.get("ORACLE_TEST_PASSWORD", "placeholder-de-teste"),
        "dsn": "dbprd",
        "client_lib": "oracle_client",
        "tns_admin": "oracle_client/Network/Admin",
        "timeout": 10.0,
        "arraysize": 1000,
    }
    valores.update(overrides)
    return OracleConfig(**valores)


def _tools(conexao: Any = None, conn_mgr: Any = None) -> OracleMcpTools:
    if conn_mgr is None:
        conn_mgr = MagicMock()
        conn_mgr.get_connection.return_value = conexao
    return OracleMcpTools(conn_mgr, _config())


def _conexao(cursor: MagicMock) -> MagicMock:
    conn = MagicMock(name="conexao")
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------- guarda SQL


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 FROM DUAL",
        "WITH cte AS (SELECT 1 AS a FROM DUAL) SELECT * FROM cte",
    ],
)
def test_guarda_permite_leitura(sql: str) -> None:
    assert validate_read_only(sql) == (True, "")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM CAD_PRODUTO",
        "SELECT 1 FROM DUAL; SELECT 2 FROM DUAL",
        "BEGIN NULL; END;",
        "SELECT * FROM TABELA FOR UPDATE",
    ],
)
def test_guarda_bloqueia_mutacao_e_multiplas_instrucoes(sql: str) -> None:
    permitido, motivo = validate_read_only(sql)
    assert permitido is False
    assert motivo


# ---------------------------------------------------------- execute_sql


def test_execute_sql_formato_tabela_normaliza_valores() -> None:
    cursor = MagicMock()
    cursor.description = [("COL1", None), ("COL2", None)]
    cursor.fetchmany.return_value = [("a  ", 1), (None, 2.5)]
    texto = _tools(_conexao(cursor)).execute_sql("SELECT 1, 2 FROM DUAL")["text"]

    linhas = texto.splitlines()
    assert linhas[0] == "| COL1 | COL2 |"
    assert linhas[1] == "| ---- | ---- |"
    assert linhas[2] == "| a    | 1    |"
    assert linhas[3] == "|      | 2.5  |"
    assert re.fullmatch(r"\*Retornadas 2 linha\(s\) em [\d.]+ ms\*", linhas[5])


def test_execute_sql_marca_limite_de_linhas_atingido() -> None:
    cursor = MagicMock()
    cursor.description = [("X", None)]
    # Uma linha além do pedido (max_rows + 1) é a prova de que há mais dados.
    cursor.fetchmany.return_value = [(1,), (2,), (3,)]
    texto = _tools(_conexao(cursor)).execute_sql("SELECT 1 FROM DUAL", max_rows=2)[
        "text"
    ]
    assert "(limite de 2 linhas atingido)*" in texto
    assert "| 2 |" in texto
    assert "| 3 |" not in texto


def test_execute_sql_exatamente_max_rows_nao_marca_truncamento() -> None:
    cursor = MagicMock()
    cursor.description = [("X", None)]
    cursor.fetchmany.return_value = [(1,), (2,)]
    resultado = _tools(_conexao(cursor)).execute_sql(
        "SELECT 1 FROM DUAL", max_rows=2, output_format="json"
    )
    assert resultado["truncated"] is False
    assert resultado["row_count"] == 2


def test_execute_sql_formato_json() -> None:
    cursor = MagicMock()
    cursor.description = [("A", None), ("B", None)]
    cursor.fetchmany.return_value = [("x", None)]
    resultado = _tools(_conexao(cursor)).execute_sql(
        "SELECT 1 FROM DUAL", max_rows=5, output_format="json"
    )
    assert resultado["data"] == [{"A": "x", "B": None}]
    assert resultado["row_count"] == 1
    assert resultado["columns"] == ["A", "B"]
    assert resultado["truncated"] is False
    assert set(resultado) == {
        "data",
        "row_count",
        "columns",
        "duration_ms",
        "truncated",
    }


def test_execute_sql_sem_descricao_responde_vazio() -> None:
    cursor = MagicMock()
    cursor.description = None
    resultado = _tools(_conexao(cursor)).execute_sql("SELECT 1 FROM DUAL")
    assert resultado == {"columns": [], "rows": [], "row_count": 0, "duration_ms": 0}


def test_execute_sql_queda_de_sessao_fecha_conexao() -> None:
    cursor = MagicMock()
    cursor.execute.side_effect = Exception(
        "ORA-03113: end-of-file on communication channel"
    )
    mgr = MagicMock()
    mgr.get_connection.return_value = _conexao(cursor)
    resultado = _tools(conn_mgr=mgr).execute_sql("SELECT 1 FROM DUAL")
    assert resultado["error"] is True
    assert resultado["message"].startswith(
        "Sessão Oracle desconectada pela rede/servidor (ORA-03113"
    )
    assert resultado["message"].endswith(
        "A conexão com o Data Center da Unifique será restabelecida na próxima chamada."
    )
    mgr.discard_connection.assert_called_once()
    mgr.close.assert_not_called()


def test_execute_sql_erro_generico_do_banco() -> None:
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("ORA-00942: tabela ou view nao existe")
    resultado = _tools(_conexao(cursor)).execute_sql("SELECT 1 FROM DUAL")
    assert resultado == {
        "error": True,
        "message": "Erro Oracle durante a execução: ORA-00942: tabela ou view nao existe",
    }


def test_execute_sql_falha_de_conexao_vira_mensagem() -> None:
    mgr = MagicMock()
    mgr.get_connection.side_effect = RuntimeError("DPY-4011: rede fechou")
    resultado = _tools(conn_mgr=mgr).execute_sql("SELECT 1 FROM DUAL")
    assert resultado == {
        "error": True,
        "message": "Erro de conexão com o banco Oracle: DPY-4011: rede fechou",
    }


# ------------------------------------------------------ plano / listagem / descrição


def test_get_query_plan_bloqueia_mutacao() -> None:
    resultado = _tools().get_query_plan("DELETE FROM T")
    assert resultado["error"] is True
    assert resultado["message"].startswith("Segurança MCP: ")


def test_get_query_plan_devolve_linhas_do_plano() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [("PLAN LINHA 1",), ("PLAN LINHA 2",)]
    assert _tools(_conexao(cursor)).get_query_plan("SELECT 1 FROM DUAL") == {
        "text": "PLAN LINHA 1\nPLAN LINHA 2"
    }


def test_get_query_plan_falha_do_explain_vira_mensagem() -> None:
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("ORA-00900: comando invalido")
    resultado = _tools(_conexao(cursor)).get_query_plan("SELECT 1 FROM DUAL")
    assert resultado == {
        "error": True,
        "message": "Falha ao obter plano de execução: ORA-00900: comando invalido",
    }


def test_list_tables_limita_a_quinhentas_linhas() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [("SGTPRD", "CAD_X", "TABLE", 10, "USERS")]
    _tools(_conexao(cursor)).list_tables(pattern="cad_%", limit=99999)
    sql, params = cursor.execute.call_args.args
    assert sql.endswith("FETCH FIRST 500 ROWS ONLY")
    assert params == {"owner": "SGTPRD", "pattern": "CAD_%"}


def test_list_tables_formato_da_tabela() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [("SGTPRD", "CAD_X", "TABLE", 10, "USERS")]
    texto = _tools(_conexao(cursor)).list_tables()["text"]
    assert texto.splitlines()[0] == (
        "| OWNER  | TABLE_NAME | TYPE  | NUM_ROWS | TABLESPACE |"
    )


def test_list_tables_erro_vira_mensagem() -> None:
    cursor = MagicMock()
    cursor.execute.side_effect = Exception("ORA-00942")
    assert _tools(_conexao(cursor)).list_tables() == {
        "error": True,
        "message": "Erro ao listar tabelas: ORA-00942",
    }


def test_describe_table_nao_encontrada() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    assert _tools(_conexao(cursor)).describe_table("cad_nada") == {
        "error": True,
        "message": "Objeto 'CAD_NADA' não encontrado no schema 'SGTPRD'.",
    }


def test_describe_table_formata_colunas() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        (1, "ID", "NUMBER", "NUMBER(10,0)", "N", " chave "),
        (2, "NOME", "VARCHAR2", "VARCHAR2(40)", "Y", None),
    ]
    texto = _tools(_conexao(cursor)).describe_table("cad_x", owner="sgtprd")["text"]
    assert texto.startswith("### Tabela: SGTPRD.CAD_X\n\n")
    assert "| # | COLUNA | TIPO         | ANULÁVEL | COMENTÁRIO |" in texto
    assert re.search(r"\| 1 \| ID +\| NUMBER\(10,0\) \| NÃO +\| chave +\|", texto)
    assert re.search(r"\| 2 \| NOME +\| VARCHAR2\(40\) \| SIM +\| +\|", texto)


def test_check_connection_falha_vira_mensagem() -> None:
    mgr = MagicMock()
    mgr.get_connection.side_effect = RuntimeError("DPY-4011")
    resultado = _tools(conn_mgr=mgr).check_connection()
    assert resultado == {
        "error": True,
        "message": "Erro de diagnóstico: DPY-4011",
    }


# ---------------------------------------------------------- renderização


def test_render_tabela_sem_colunas_e_sem_linhas() -> None:
    assert OracleMcpTools._render_markdown_table([], []) == "*(sem colunas)*"
    assert OracleMcpTools._render_markdown_table(["A", "B"], []) == (
        "| A | B |\n| --- | --- |\n*(0 linhas retornadas)*"
    )


# ------------------------------------------------------------- protocolo


def test_initialize_informa_servidor_e_versao() -> None:
    resposta = McpServer().handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert resposta == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "oracledb", "version": "2.0.0"},
        },
    }


def test_notificacao_inicializada_nao_responde() -> None:
    assert McpServer().handle_request({"method": "notifications/initialized"}) is None


def test_notificacao_desconhecida_nao_recebe_erro() -> None:
    notificacao = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}}
    assert McpServer().handle_request(notificacao) is None


def test_ping_responde_vazio() -> None:
    assert McpServer().handle_request(
        {"jsonrpc": "2.0", "id": 7, "method": "ping"}
    ) == {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {},
    }


def test_tools_list_ordem_e_nomes() -> None:
    resposta = McpServer().handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    assert [t["name"] for t in resposta["result"]["tools"]] == [
        "execute_sql",
        "get_query_plan",
        "list_tables",
        "describe_table",
        "check_connection",
    ]


def test_metodo_desconhecido_erro_32601() -> None:
    resposta = McpServer().handle_request({"jsonrpc": "2.0", "id": 3, "method": "foo"})
    assert resposta == {
        "jsonrpc": "2.0",
        "id": 3,
        "error": {"code": -32601, "message": "Método não suportado: 'foo'"},
    }


def test_ferramenta_desconhecida_erro_32601() -> None:
    resposta = McpServer().handle_request(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "x"}}
    )
    assert resposta["error"] == {
        "code": -32601,
        "message": "Ferramenta desconhecida: 'x'",
    }


def test_tools_call_erro_vira_texto_com_prefixo() -> None:
    resposta = McpServer().handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "execute_sql", "arguments": {"sql": "DELETE FROM T"}},
        }
    )
    resultado = resposta["result"]
    assert resultado["isError"] is True
    assert resultado["content"] == [
        {"type": "text", "text": resultado["content"][0]["text"]}
    ]
    assert resultado["content"][0]["text"].startswith(
        "[ERRO] Segurança MCP (Read-Only Violation): "
    )


def test_tools_call_json_passa_o_dicionario_serializado() -> None:
    servidor = McpServer()
    retorno = {
        "data": [{"A": 1}],
        "row_count": 1,
        "columns": ["A"],
        "duration_ms": 1,
        "truncated": False,
    }
    servidor.tools.execute_sql = MagicMock(return_value=retorno)
    resposta = servidor.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "execute_sql",
                "arguments": {"sql": "SELECT 1 FROM DUAL", "format": "json"},
            },
        }
    )
    assert resposta["result"]["isError"] is False
    assert resposta["result"]["content"][0]["text"] == json.dumps(
        retorno, indent=2, ensure_ascii=False
    )
    servidor.tools.execute_sql.assert_called_once_with(
        "SELECT 1 FROM DUAL", 100, "json"
    )


def test_loop_stdio_trata_json_invalido_e_segue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO('nao-e-json\n\n{"jsonrpc":"2.0","id":1,"method":"ping"}\n'),
    )
    McpServer().run()
    saida = [json.loads(linha) for linha in capsys.readouterr().out.splitlines()]
    assert saida[0] == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error: JSON inválido"},
    }
    assert saida[1] == {"jsonrpc": "2.0", "id": 1, "result": {}}


# ------------------------------------------------------------- configuração


def test_load_config_usa_defaults_e_ignora_valores_invalidos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for chave in (
        "ORACLE_READONLY_USER",
        "ORACLE_USERNAME",
        "ORACLE_USER",
        "ORACLE_READONLY_PASSWORD",
        "ORACLE_PASSWORD",
        "ORACLE_CONNECT_STRING",
        "ORACLE_CONNECTION_STRING",
        "ORACLE_CLIENT_LIB_DIR",
        "ORACLE_CLIENT_PATH",
        "TNS_ADMIN",
    ):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setenv("ORACLE_USER", "via_fallback")
    monkeypatch.setenv("ORACLE_MCP_TIMEOUT", "abc")
    monkeypatch.setenv("ORACLE_MCP_ARRAYSIZE", "500")

    config = load_config()

    assert config.user == "via_fallback"
    assert config.dsn == "dbprd"
    assert config.tns_admin == DEFAULT_TNS_ADMIN
    assert config.timeout == DEFAULT_TIMEOUT
    assert config.arraysize == 500


def test_get_connection_sem_credenciais_levanta_erro_claro() -> None:
    mgr = OracleConnectionManager(_config(user="", password=""))
    with pytest.raises(ValueError, match="Credenciais Oracle ausentes"):
        mgr.get_connection()


# ------------------------------------------- instrumentação e pool (portados)


def test_execute_sql_instrumenta_sessao_oci() -> None:
    cursor = MagicMock()
    cursor.description = [("COL1", None)]
    cursor.fetchmany.return_value = [("Valor 1",)]
    conn = _conexao(cursor)

    _tools(conn).execute_sql("SELECT 1 FROM DUAL")

    assert conn.module == "HubAutomacoes.MCP"
    assert conn.action == "TOOL:execute_sql"
    assert conn.client_identifier.startswith("MCP:execute_sql:")
    assert "PID:" in conn.client_info
    assert conn.db_op == "TOOL_EXECUTE_SQL"


def test_connection_manager_usa_session_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = MagicMock()
    conn = MagicMock()
    pool.acquire.return_value = conn
    pool.opened = 2
    pool.busy = 1
    pool.max = 4
    monkeypatch.setattr("oracledb.create_pool", MagicMock(return_value=pool))
    # Sondagem do modo (modo auto) não pode abrir conexão real nos testes.
    monkeypatch.setattr(
        "mcp_server.connect_adaptive", MagicMock(return_value=MagicMock())
    )

    mgr = OracleConnectionManager(_config(dsn="host-teste:1521/dbprd"))
    assert mgr.acquire_connection() is conn
    pool.acquire.assert_called_once()
    status = mgr.get_pool_status()
    assert status["active"] is True
    assert status["max"] == 4

    mgr.release_connection(conn)
    pool.release.assert_called_once_with(conn)
    mgr.close()
    pool.close.assert_called_once_with(force=True)


def test_connection_manager_cai_para_conexao_avulsa_sem_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "oracledb.create_pool",
        MagicMock(side_effect=Exception("Driver não suporta pool neste ambiente")),
    )
    conn = MagicMock()
    # Primeira chamada: a sondagem do modo (fechada logo). Segunda: a conexão avulsa.
    sonda = MagicMock(name="sonda")
    monkeypatch.setattr(
        "mcp_server.connect_adaptive", MagicMock(side_effect=[sonda, conn])
    )

    mgr = OracleConnectionManager(_config(dsn="host-teste:1521/dbprd"))
    assert mgr.acquire_connection() is conn
    assert mgr.get_pool_status()["active"] is False

    sonda.close.assert_called_once()
    mgr.close()
    conn.close.assert_called_once()


def test_discard_connection_descarta_so_a_conexao_do_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão (achado 7): queda de uma conexão usa pool.drop, sem fechar o pool."""
    pool = MagicMock(name="pool")
    conn = MagicMock(name="conn")
    pool.acquire.return_value = conn
    monkeypatch.setattr("oracledb.create_pool", MagicMock(return_value=pool))
    monkeypatch.setattr(
        "mcp_server.connect_adaptive", MagicMock(return_value=MagicMock())
    )
    mgr = OracleConnectionManager(_config(dsn="host-teste:1521/dbprd"))
    assert mgr.acquire_connection() is conn

    mgr.discard_connection(conn)

    pool.drop.assert_called_once_with(conn)
    pool.close.assert_not_called()
    assert mgr.pool is pool


def test_pool_falho_tenta_de_novo_depois_da_janela(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão (achado 19): _pool_failed não é permanente."""
    import mcp_server  # pylint: disable=import-outside-toplevel

    criar = MagicMock(side_effect=[RuntimeError("rede fora"), MagicMock(name="pool")])
    monkeypatch.setattr("oracledb.create_pool", criar)
    monkeypatch.setattr(
        "mcp_server.connect_adaptive", MagicMock(return_value=MagicMock())
    )
    relogio = [1000.0]
    monkeypatch.setattr(mcp_server.time, "monotonic", lambda: relogio[0])
    mgr = OracleConnectionManager(_config(dsn="host-teste:1521/dbprd"))

    assert mgr.pool is None
    assert mgr.pool is None  # dentro da janela: não tenta de novo
    assert criar.call_count == 1
    relogio[0] += mcp_server.JANELA_NOVA_TENTATIVA_POOL_SEGUNDOS + 1
    assert mgr.pool is not None
    assert criar.call_count == 2


def test_tools_call_sem_id_nao_executa_nem_responde() -> None:
    """Regressão (achado 17): notificação JSON-RPC nunca recebe resposta."""
    servidor = McpServer()
    servidor.tools = MagicMock()
    notificacao = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "execute_sql", "arguments": {"sql": "SELECT 1 FROM DUAL"}},
    }
    assert servidor.handle_request(notificacao) is None
    servidor.tools.execute_sql.assert_not_called()


def test_describe_table_usa_all_tab_columns() -> None:
    """Regressão (achado 18): ALL_TAB_COLS traria colunas ocultas e virtuais."""
    cursor = MagicMock(name="cursor")
    cursor.fetchall.return_value = []
    conexao = MagicMock(name="conexao")
    conexao.cursor.return_value = cursor
    _tools(conexao).describe_table("OB")
    sqls = " ".join(str(c.args[0]) for c in cursor.execute.call_args_list)
    assert "ALL_TAB_COLUMNS" in sqls
    assert "ALL_TAB_COLS " not in sqls


def test_sem_caminho_padrao_do_client_12_2() -> None:
    """Regressão (achado 8): sem adivinhar 12.2 enquanto a máquina pode ter o 19c."""
    import mcp_server  # pylint: disable=import-outside-toplevel

    assert mcp_server.DEFAULT_LIB_DIR == ""
    assert "12.2" not in mcp_server.DEFAULT_TNS_ADMIN
