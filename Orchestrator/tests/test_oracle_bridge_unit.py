"""Testes do modo `ORACLE_DRIVER_MODE=bridge`, que foi removido.

O motor Node.js (node-oracledb) nunca foi validado contra o Oracle e saiu do
código. Estes testes provam que o modo é recusado com erro claro antes de
qualquer conexão, em `oracle_client.get_driver_mode`, em
`oracle_extract.fetch_all` e no Beneficiamento, sem depender de Node.
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "lib" / "python"))
_SRC_BENEF = _REPO / "Produção Beneficimento" / "src"
if str(_SRC_BENEF) not in sys.path:
    sys.path.insert(0, str(_SRC_BENEF))

import oracle_client
import oracle_extract
from beneficiamento import (
    oracle as benef_oracle,
)
from oracle_extract import OracleCredentials, fetch_all

pytestmark = pytest.mark.unitario

_SENHA_FICTICIA = "nao-usada"
_CREDS = OracleCredentials(
    user="u",
    password=_SENHA_FICTICIA,
    dsn="dbprd",
    client_lib="ic19",
    tns_admin="tns",
)
_MENSAGEM_RECUSA = "ORACLE_DRIVER_MODE=bridge foi removido"


def _noop_log(*_args: Any, **_kwargs: Any) -> None:
    return None


@pytest.mark.parametrize("valor", ["bridge", " Bridge "])
def test_get_driver_mode_recusa_bridge_com_mensagem_clara(
    monkeypatch: pytest.MonkeyPatch, valor: str
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", valor)
    with pytest.raises(
        ValueError, match="ORACLE_DRIVER_MODE=bridge foi removido"
    ) as info:
        oracle_client.get_driver_mode()
    mensagem = str(info.value)
    for modo_valido in ("auto", "thick", "queue"):
        assert modo_valido in mensagem


def test_fetch_all_recusa_bridge_antes_de_conectar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "bridge")
    conectar = MagicMock()
    monkeypatch.setattr(oracle_extract, "connect_adaptive", conectar)
    with pytest.raises(ValueError, match=_MENSAGEM_RECUSA):
        fetch_all(_CREDS, "SELECT 1", "exec-bridge", _noop_log)
    conectar.assert_not_called()


def test_beneficiamento_recusa_bridge_antes_de_conectar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "bridge")
    monkeypatch.setattr(benef_oracle, "_readonly_credentials", lambda: _CREDS)
    conectar = MagicMock()
    monkeypatch.setattr(benef_oracle, "connect_adaptive", conectar)
    with pytest.raises(ValueError, match=_MENSAGEM_RECUSA):
        benef_oracle.execute_query("SELECT 1", {}, wall_clock_budget_seconds=20)
    conectar.assert_not_called()


def test_motor_node_do_bridge_nao_existe_mais() -> None:
    assert not hasattr(oracle_extract, "run_node_bridge")
    assert not hasattr(oracle_extract, "OracleBridgeError")
    assert not hasattr(oracle_client, "DRIVER_MODE_BRIDGE")
