"""Testes unitarios do modo adaptativo e do check_connection do MCP Oracle.

Nao toca o Oracle: a conexao e o driver sao substituidos por dublês.
"""

import os
import sys
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

import mcp_server
from carregadores_modulos import acessar_privado
from mcp_server import OracleConfig, OracleConnectionManager, OracleMcpTools
from oracle_client import DriverMode
from oracle_queue import OracleQueueError, QueueResult, _encode_params

pytestmark = pytest.mark.unitario


def _config(client_lib: str = "instantclient_19c") -> OracleConfig:
    return OracleConfig(
        user="usuario_teste",
        password=os.environ.get("ORACLE_TEST_PASSWORD", "placeholder-de-teste"),
        dsn="dbprd",
        client_lib=client_lib,
        tns_admin="instantclient_19c/network/admin",
        timeout=10.0,
        arraysize=1000,
    )


def _conexao_com_consulta_de_teste() -> MagicMock:
    conn = MagicMock(name="conexao")
    conn.version = "19.0.0.0.0"
    cursor = MagicMock(name="cursor")
    cursor.fetchone.return_value = ("SGTPRD", "DBPRD", "HOST01")
    conn.cursor.return_value = cursor
    return conn


def test_get_connection_delega_ao_connect_adaptive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chamadas: list[dict[str, object]] = []

    def falso(**kwargs: object) -> MagicMock:
        chamadas.append(kwargs)
        return MagicMock(name="conexao")

    monkeypatch.setenv("ORACLE_DRIVER_MODE", "auto")
    monkeypatch.setattr(mcp_server, "connect_adaptive", falso)
    mgr = OracleConnectionManager(_config())
    try:
        assert mgr.get_connection() is not None
        assert chamadas[0]["client_lib"] == "instantclient_19c"
        assert chamadas[0]["tns_admin"] == "instantclient_19c/network/admin"
        assert chamadas[0]["dsn"] == "dbprd"
    finally:
        mgr.close()


def test_check_connection_reporta_thin_sem_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "describe_driver_mode",
        lambda: DriverMode(
            "thin", "Thin Mode (python-oracledb 3.3.0, sem Oracle Client)", None
        ),
    )
    monkeypatch.setattr(mcp_server, "supports_native_call_timeout", lambda: True)
    mgr = MagicMock()
    mgr.get_connection.return_value = _conexao_com_consulta_de_teste()
    tools = OracleMcpTools(mgr, _config())

    texto = tools.check_connection()["text"]

    assert "Thin Mode (python-oracledb 3.3.0, sem Oracle Client)" in texto
    assert "19.0.0.0.0" in texto
    assert "Latência (RTT, consulta de teste)" in texto
    assert "nativo (`call_timeout`)" in texto
    assert "arraysize=1000, prefetchrows=1000" in texto
    assert "Client Lib" not in texto


def test_check_connection_reporta_thick_com_versao_do_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "describe_driver_mode",
        lambda: DriverMode(
            "thick", "Thick Mode (Oracle Client 19.25.0.0.0)", (19, 25, 0, 0, 0)
        ),
    )
    monkeypatch.setattr(mcp_server, "supports_native_call_timeout", lambda: True)
    mgr = MagicMock()
    mgr.get_connection.return_value = _conexao_com_consulta_de_teste()
    tools = OracleMcpTools(mgr, _config())

    texto = tools.check_connection()["text"]

    assert "Thick Mode (Oracle Client 19.25.0.0.0)" in texto
    assert "Client Lib" in texto
    assert "instantclient_19c" in texto


def test_check_connection_marca_watchdog_emulado_no_client_antigo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "describe_driver_mode",
        lambda: DriverMode(
            "thick", "Thick Mode (Oracle Client 12.2.0.1.0)", (12, 2, 0, 1, 0)
        ),
    )
    monkeypatch.setattr(mcp_server, "supports_native_call_timeout", lambda: False)
    mgr = MagicMock()
    mgr.get_connection.return_value = _conexao_com_consulta_de_teste()
    tools = OracleMcpTools(mgr, _config())

    assert "emulado" in tools.check_connection()["text"]


def test_check_connection_erro_de_conexao_vira_mensagem() -> None:
    mgr = MagicMock()
    mgr.get_connection.side_effect = oracledb.OperationalError("DPY-4011: rede fechou")
    tools = OracleMcpTools(mgr, _config())

    resultado = tools.check_connection()

    assert resultado["error"] is True
    assert "DPY-4011" in resultado["message"]


def test_execute_sql_timeout_nativo_marca_watchdog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Com call_timeout nativo, o DPY-4024 do driver vira mensagem de timeout."""
    monkeypatch.setattr("oracle_session.supports_native_call_timeout", lambda: True)
    conn = MagicMock(name="conexao")
    cursor = MagicMock(name="cursor")
    cursor.execute.side_effect = oracledb.DatabaseError(
        "DPY-4024: call timeout of 10000 ms exceeded"
    )
    conn.cursor.return_value = cursor
    mgr = MagicMock()
    mgr.get_connection.return_value = conn
    tools = OracleMcpTools(mgr, _config())

    resultado = tools.execute_sql("SELECT 1 FROM DUAL")

    assert resultado["error"] is True
    assert "Timeout da consulta" in resultado["message"]
    assert "(prazo da chamada ou watchdog)" in resultado["message"]
    assert conn.call_timeout == 0


# ----------------------------------------------- sondagem do modo antes do pool (achado 6)


def _sonda_que_registra(eventos: list[str]) -> MagicMock:
    sonda = MagicMock(name="sonda")
    sonda.close.side_effect = lambda: eventos.append("fecha_sonda")
    return sonda


def test_modo_auto_sonda_o_driver_antes_de_criar_o_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão (achado 6): DPY-3015 só aparece no acquire; a sondagem vem antes do pool."""
    eventos: list[str] = []
    sonda = _sonda_que_registra(eventos)

    def sondagem(**_kwargs: object) -> MagicMock:
        eventos.append("sonda")
        return sonda

    def criar_pool(**_kwargs: object) -> MagicMock:
        eventos.append("create_pool")
        return MagicMock(name="pool")

    monkeypatch.setenv("ORACLE_DRIVER_MODE", "auto")
    monkeypatch.setattr(mcp_server, "connect_adaptive", sondagem)
    monkeypatch.setattr("oracledb.create_pool", criar_pool)
    mgr = OracleConnectionManager(_config())
    try:
        assert mgr.pool is not None
        assert eventos == ["sonda", "fecha_sonda", "create_pool"]
    finally:
        mgr.close()


@pytest.mark.parametrize(
    ("thin", "com_config_dir"),
    [(True, True), (False, False)],
)
def test_pool_so_recebe_config_dir_quando_o_modo_e_thin(
    monkeypatch: pytest.MonkeyPatch, thin: bool, com_config_dir: bool
) -> None:
    """O config_dir é do Thin: depois da sondagem, um Thick ativo não o recebe."""
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "auto")
    monkeypatch.setattr(
        mcp_server, "connect_adaptive", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr("oracledb.is_thin_mode", lambda: thin)
    criar = MagicMock(return_value=MagicMock(name="pool"))
    monkeypatch.setattr("oracledb.create_pool", criar)
    mgr = OracleConnectionManager(_config())
    try:
        assert mgr.pool is not None
        assert ("config_dir" in criar.call_args.kwargs) is com_config_dir
    finally:
        mgr.close()


def test_modo_thick_pedido_ativa_o_cliente_e_nao_sonda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eventos: list[str] = []

    def init_falso(*_a: object, **_k: object) -> None:
        eventos.append("init_thick")

    def criar_pool(**_k: object) -> MagicMock:
        eventos.append("create_pool")
        return MagicMock(name="pool")

    monkeypatch.setenv("ORACLE_DRIVER_MODE", "thick")
    monkeypatch.setattr(mcp_server, "init_oracle_thick_mode", init_falso)
    monkeypatch.setattr(
        mcp_server,
        "connect_adaptive",
        MagicMock(side_effect=AssertionError("sondagem não roda no thick pedido")),
    )
    monkeypatch.setattr("oracledb.create_pool", criar_pool)
    mgr = OracleConnectionManager(_config())
    try:
        assert mgr.pool is not None
        assert eventos == ["init_thick", "create_pool"]
    finally:
        mgr.close()


def test_falha_da_sondagem_marca_pool_falho_sem_levantar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "auto")
    monkeypatch.setattr(
        mcp_server,
        "connect_adaptive",
        MagicMock(side_effect=oracledb.OperationalError("DPY-4011: rede fechou")),
    )
    criar = MagicMock()
    monkeypatch.setattr("oracledb.create_pool", criar)
    mgr = OracleConnectionManager(_config())
    try:
        assert mgr.pool is None
        criar.assert_not_called()
        assert acessar_privado(mgr, "_pool_failed") is True
    finally:
        mgr.close()


def test_mcp_queue_mode_roteia_ferramentas_mantendo_guard_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    cfg = _config()
    mgr = OracleConnectionManager(cfg)
    tools = OracleMcpTools(mgr, cfg)
    try:
        # Guard continua bloqueando antes de encostar na fila
        bloq = tools.execute_sql("DELETE FROM CAD_PRODUTO")
        assert bloq["error"] is True
        assert "Segurança MCP" in bloq["message"]

        chamadas: list[tuple[str, Any, dict[str, Any]]] = []

        def _falso_exec(sql: str, params: Any = None, **kw: Any) -> QueueResult:
            chamadas.append((sql, params, kw))
            if "CURRENT_USER" in sql:
                return QueueResult(
                    columns=["U", "D", "H"],
                    types=["string", "string", "string"],
                    rows=[("SGT_RO", "DBPRD", "ora01")],
                    elapsed_ms=12,
                    worker="2.6.2",
                    raw_meta={"db_ms": 4},
                )
            if "ALL_TABLES" in sql:
                return QueueResult(
                    columns=[
                        "OWNER",
                        "TABLE_NAME",
                        "OBJECT_TYPE",
                        "NUM_ROWS",
                        "TABLESPACE_NAME",
                    ],
                    types=["string", "string", "string", "number", "string"],
                    rows=[("SGTPRD", "OB", "TABLE", 100, "USERS")],
                    elapsed_ms=8,
                    worker="2.6.2",
                )
            if "ALL_TAB_COLUMNS" in sql:
                return QueueResult(
                    columns=[
                        "COLUMN_ID",
                        "COLUMN_NAME",
                        "DATA_TYPE",
                        "FORMATTED_TYPE",
                        "NULLABLE",
                        "COMMENTS",
                    ],
                    types=["number", "string", "string", "string", "string", "string"],
                    rows=[(1, "ID", "NUMBER", "NUMBER(10,0)", "N", "pk")],
                    elapsed_ms=10,
                    worker="2.6.2",
                )
            return QueueResult(
                columns=["A"],
                types=["number"],
                rows=[(42,), (43,)],
                elapsed_ms=15,
                worker="2.6.2",
            )

        monkeypatch.setattr(mcp_server, "executar_consulta_fila", _falso_exec)
        monkeypatch.setattr(
            mcp_server, "verificar_objetos_fila", lambda *_a, **_k: None
        )
        monkeypatch.setattr(
            mcp_server,
            "explicar_plano_fila",
            lambda *_a, **_k: (["Plan hash value: 123"], 9.5),
        )
        monkeypatch.setattr(
            mcp_server,
            "status_fila_diagnostico",
            lambda: {
                "version": "2.6.2",
                "age_seconds": 1.2,
                "queue_dir": r"\\srv\fila",
            },
        )

        res_sql = tools.execute_sql(
            "SELECT :X AS A FROM DUAL", max_rows=5, params={"X": 42}
        )
        assert "| A" in res_sql["text"]
        assert "42" in res_sql["text"]
        assert chamadas[-1][1] == {"X": 42}
        assert chamadas[-1][2].get("max_rows") == 6
        assert "SELECT * FROM" not in chamadas[-1][0]

        res_json = tools.execute_sql(
            "SELECT 42 AS A FROM DUAL", max_rows=1, output_format="json"
        )
        assert res_json["row_count"] == 1
        assert res_json["truncated"] is True
        assert res_json["data"] == [{"A": 42}]
        assert chamadas[-1][2].get("max_rows") == 2

        res_list = tools.list_tables(pattern="OB%", owner="SGTPRD", limit=10)
        assert "SGTPRD" in res_list["text"]
        assert "OB" in res_list["text"]

        res_plan = tools.get_query_plan("SELECT 1 FROM DUAL")
        assert "Plan hash value: 123" in res_plan["text"]

        res_desc = tools.describe_table("OB")
        assert "SGTPRD.OB" in res_desc["text"]

        res_ping = tools.check_connection()
        assert "Queue Mode" in res_ping["text"]
        assert "v2.6.2" in res_ping["text"]
    finally:
        mgr.close()


def test_mcp_queue_mode_bloqueio_objetos_e_erro_oracle_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    cfg = _config()
    mgr = OracleConnectionManager(cfg)
    tools = OracleMcpTools(mgr, cfg)
    try:
        monkeypatch.setattr(
            mcp_server,
            "verificar_objetos_fila",
            lambda *_a, **_k: "Objeto executável proibido: SGTPRD.FN_X",
        )
        bloq = tools.execute_sql("SELECT SGTPRD.FN_X FROM DUAL")
        assert bloq["error"] is True
        assert "Segurança MCP" in bloq["message"]
        assert "FN_X" in bloq["message"]

        monkeypatch.setattr(
            mcp_server, "verificar_objetos_fila", lambda *_a, **_k: None
        )

        def _falhar_fila(*_a: Any, **_k: Any) -> Any:
            raise OracleQueueError("oracle", "ORA-00942: table or view does not exist")

        monkeypatch.setattr(mcp_server, "executar_consulta_fila", _falhar_fila)
        err = tools.execute_sql("SELECT 1 FROM INEXISTENTE")
        assert err["error"] is True
        assert "Erro Oracle (fila SMB)" in err["message"]
        assert "ORA-00942" in err["message"]
    finally:
        mgr.close()


def test_mcp_queue_mode_param_list_vira_erro_de_ferramenta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TypeError do encoder da fila (param list/dict) vira erro da ferramenta, não -32603."""
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "queue")
    cfg = _config()
    mgr = OracleConnectionManager(cfg)
    tools = OracleMcpTools(mgr, cfg)
    try:
        monkeypatch.setattr(
            mcp_server, "verificar_objetos_fila", lambda *_a, **_k: None
        )

        def _exec_com_encoder_real(_sql: str, params: Any = None, **_kw: Any) -> Any:
            # Encoder real da fila: list/dict levanta TypeError antes de chegar ao SMB.
            _encode_params(params or {})
            raise AssertionError("o pedido não deveria chegar à fila")

        monkeypatch.setattr(mcp_server, "executar_consulta_fila", _exec_com_encoder_real)
        res = tools.execute_sql("SELECT :X AS A FROM DUAL", params={"X": [1]})
        assert res["error"] is True
        assert "Parâmetro inválido para a fila Oracle" in res["message"]
        assert "não suportado na fila" in res["message"]
    finally:
        mgr.close()


def test_mcp_valida_tipos_de_argumentos_list_tables_e_describe_table() -> None:
    motivo_invalido = acessar_privado(mcp_server, "_motivo_argumentos_invalidos")
    assert motivo_invalido("list_tables", {"limit": True})
    assert motivo_invalido("list_tables", {"limit": "10"})
    assert motivo_invalido("list_tables", {"pattern": 123})
    assert motivo_invalido("list_tables", {"owner": 99})
    assert (
        motivo_invalido(
            "list_tables", {"pattern": "OB%", "owner": "SGTPRD", "limit": 10}
        )
        is None
    )

    assert motivo_invalido("describe_table", {"table_name": 123})
    assert motivo_invalido("describe_table", {"table_name": "OB", "owner": 123})
    assert (
        motivo_invalido("describe_table", {"table_name": "OB", "owner": None}) is None
    )
