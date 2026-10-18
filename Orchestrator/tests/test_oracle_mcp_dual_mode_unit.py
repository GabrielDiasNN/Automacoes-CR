"""Testes unitarios do modo adaptativo e do check_connection do MCP Oracle.

Nao toca o Oracle: a conexao e o driver sao substituidos por dublês.
"""

# pylint: disable=import-error, wrong-import-position
import os
import sys
from pathlib import Path
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
from mcp_server import OracleConfig, OracleConnectionManager, OracleMcpTools
from oracle_client import DriverMode

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

    monkeypatch.setattr(mcp_server, "connect_adaptive", falso)
    mgr = OracleConnectionManager(_config())

    assert mgr.get_connection() is not None
    assert chamadas[0]["client_lib"] == "instantclient_19c"
    assert chamadas[0]["tns_admin"] == "instantclient_19c/network/admin"
    assert chamadas[0]["dsn"] == "dbprd"


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
    mgr.get_connection.side_effect = RuntimeError("DPY-4011: rede fechou")
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

    assert mgr.pool is not None
    assert eventos == ["sonda", "fecha_sonda", "create_pool"]


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

    assert mgr.pool is not None
    assert ("config_dir" in criar.call_args.kwargs) is com_config_dir


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

    assert mgr.pool is not None
    assert eventos == ["init_thick", "create_pool"]


def test_falha_da_sondagem_marca_pool_falho_sem_levantar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "auto")
    monkeypatch.setattr(
        mcp_server,
        "connect_adaptive",
        MagicMock(side_effect=RuntimeError("DPY-4011: rede fechou")),
    )
    criar = MagicMock()
    monkeypatch.setattr("oracledb.create_pool", criar)
    mgr = OracleConnectionManager(_config())

    assert mgr.pool is None
    criar.assert_not_called()
    assert mgr._pool_failed is True  # pylint: disable=protected-access
