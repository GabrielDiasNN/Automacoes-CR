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
    assert conn.call_timeout == 0
