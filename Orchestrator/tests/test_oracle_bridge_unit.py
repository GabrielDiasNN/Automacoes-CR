"""Testes unitários do bridge Oracle via Node (`ORACLE_DRIVER_MODE=bridge`).

Cobrem o contrato que mantém o motor Node intercambiável com o Python: datas
em hora local, credenciais do chamador, SQL por arquivo, prazo, nenhum fallback
implícito e hash idêntico ao `compute_hash`.
"""

import json
import os
import shutil
import subprocess  # nosec B404
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "lib" / "python"))
_SRC_BENEF = _REPO / "Produção Beneficimento" / "src"
if str(_SRC_BENEF) not in sys.path:
    sys.path.insert(0, str(_SRC_BENEF))

import oracle_extract  # noqa: E402  pylint: disable=wrong-import-position
from beneficiamento import (  # noqa: E402  pylint: disable=wrong-import-position
    oracle as benef_oracle,
)
from oracle_extract import (  # noqa: E402  pylint: disable=wrong-import-position
    OracleBridgeError,
    OracleCredentials,
    compute_hash,
    fetch_all,
    run_node_bridge,
    serialize_rows,
)

pytestmark = pytest.mark.unitario

_SENHA_FICTICIA = "nao-usada"
_CREDS = OracleCredentials(
    user="u",
    password=_SENHA_FICTICIA,
    dsn="dbprd",
    client_lib="ic19",
    tns_admin="tns",
)


def _noop_log(*_args: Any, **_kwargs: Any) -> None:
    return None


def test_parametros_de_data_viajam_em_hora_local() -> None:
    encode = oracle_extract._encode_bridge_param  # pylint: disable=protected-access
    assert encode(date(2026, 10, 27)) == {"$date": "2026-10-27"}
    assert encode(datetime(2026, 10, 27, 8, 30)) == {"$date": "2026-10-27T08:30:00"}
    aware = datetime(2026, 10, 27, 11, 0, tzinfo=UTC)
    assert encode(aware) == {
        "$date": aware.astimezone().replace(tzinfo=None).isoformat()
    }
    assert encode(Decimal("1.5")) == 1.5


def test_run_node_bridge_passa_creds_sql_por_arquivo_e_prazo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capturado: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        capturado["cmd"] = cmd
        capturado["kwargs"] = kwargs
        capturado["sql"] = Path(cmd[2]).read_text(encoding="utf-8")
        stdout = json.dumps(
            {"columns": ["DT", "N"], "rows": [[{"$date": "2026-10-26T22:30:00"}, 1]]}
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("oracle_extract.shutil.which", lambda _n: "node")
    monkeypatch.setattr("oracle_extract.subprocess.run", fake_run)

    columns, rows = run_node_bridge(
        _CREDS,
        "SELECT 1 FROM DUAL",
        {"dt": datetime(2026, 10, 27)},
        timeout_seconds=20,
        max_rows=100,
    )

    assert columns == ["DT", "N"]
    assert rows == [(datetime(2026, 10, 26, 22, 30), 1)]
    assert capturado["sql"] == "SELECT 1 FROM DUAL"
    assert json.loads(capturado["cmd"][3]) == {"dt": {"$date": "2026-10-27T00:00:00"}}
    assert capturado["cmd"][4:] == ["100", "20"]
    env = capturado["kwargs"]["env"]
    assert env["ORACLE_CONNECT_STRING"] == "dbprd"
    assert env["TNS_ADMIN"] == "tns"
    assert capturado["kwargs"]["timeout"] == 25


def test_run_node_bridge_estouro_de_prazo_vira_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr("oracle_extract.shutil.which", lambda _n: "node")
    monkeypatch.setattr("oracle_extract.subprocess.run", fake_run)
    with pytest.raises(TimeoutError):
        run_node_bridge(_CREDS, "SELECT 1 FROM DUAL", timeout_seconds=1)


def test_fetch_all_nao_cai_no_bridge_quando_a_conexao_nativa_falha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "auto")
    monkeypatch.setattr(oracle_extract, "_registrar_saude_wan", _noop_log)
    bridge = MagicMock()
    monkeypatch.setattr(oracle_extract, "run_node_bridge", bridge)
    monkeypatch.setattr(
        oracle_extract,
        "connect_adaptive",
        MagicMock(side_effect=RuntimeError("ORA-01017: invalid username/password")),
    )
    with pytest.raises(RuntimeError, match="ORA-01017"):
        fetch_all(_CREDS, "SELECT 1", "EXEC-1", _noop_log)
    bridge.assert_not_called()


def test_fetch_all_em_modo_bridge_usa_as_creds_do_chamador(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "bridge")
    monkeypatch.setattr(oracle_extract, "_registrar_saude_wan", _noop_log)
    bridge = MagicMock(return_value=(["A"], [(1,)]))
    monkeypatch.setattr(oracle_extract, "run_node_bridge", bridge)

    assert fetch_all(_CREDS, "SELECT 1", "EXEC-1", _noop_log, params={"x": 1}) == (
        ["A"],
        [(1,)],
    )
    bridge.assert_called_once_with(_CREDS, "SELECT 1", {"x": 1})


def test_beneficiamento_bridge_dedup_colunas_e_nova_tentativa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORACLE_DRIVER_MODE", "bridge")
    monkeypatch.setattr(benef_oracle, "_readonly_credentials", lambda: _CREDS)
    chamadas: list[dict[str, Any]] = []

    def fake_bridge(_creds: Any, _sql: str, _params: Any, **kwargs: Any) -> Any:
        chamadas.append(kwargs)
        if len(chamadas) == 1:
            raise OracleBridgeError("Oracle Bridge falhou: ORA-03113: end-of-file")
        return ["X", "X"], [(1, 2)]

    monkeypatch.setattr(benef_oracle, "run_node_bridge", fake_bridge)
    result = benef_oracle.execute_query(
        "SELECT 1", {}, wall_clock_budget_seconds=20, max_rows=10
    )

    assert result.columns == ["X", "X__2"]
    assert result.duplicate_columns == {"X": [1, 2]}
    assert result.metadata["attempts"] == 2
    assert result.metadata["max_rows_limit"] == 10
    assert chamadas[0]["max_rows"] == 10
    assert chamadas[0]["timeout_seconds"] <= 20


_NODE = shutil.which("node")
_COMMON_JS = _REPO / "lib" / "node" / "oracle_common.js"
_ORACLEDB_JS = _REPO / "node_modules" / "oracledb"


@pytest.mark.skipif(
    not _NODE or not _ORACLEDB_JS.exists(), reason="node/oracledb indisponível"
)
def test_hash_e_datas_do_node_iguais_ao_python() -> None:
    linhas = [
        [10, " B ", "2026-10-26T22:30:00", 1.5, None],
        [9, "Ação", "2026-10-27T08:00:00", 2.25, "x"],
    ]
    colunas = ["NUMERO_OB", "FASE_ATUAL", "DT", "KG", "OBS"]
    script = (
        f"const oc=require({json.dumps(str(_COMMON_JS))});"
        f"const rows={json.dumps(linhas)}.map(r=>{{r[2]=oc.parseLocalIso(r[2]);return r;}});"
        f"const data=oc.serializeRows({json.dumps(colunas)},rows,"
        "r=>[r.NUMERO_OB||'',r.FASE_ATUAL||'']);"
        "process.stdout.write(JSON.stringify({hash:oc.computeHash({rows:data}),data}));"
    )
    proc = subprocess.run(  # nosec B603
        [str(_NODE), "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        cwd=os.fspath(_REPO),
    )
    saida = json.loads(proc.stdout)

    py_rows = [
        (10, " B ", datetime(2026, 10, 26, 22, 30), 1.5, None),
        (9, "Ação", datetime(2026, 10, 27, 8, 0), 2.25, "x"),
    ]
    esperado = serialize_rows(
        colunas,
        py_rows,
        sort_key=lambda r: (r.get("NUMERO_OB") or "", r.get("FASE_ATUAL") or ""),
    )
    assert saida["data"] == esperado
    assert saida["hash"] == compute_hash({"rows": esperado})
