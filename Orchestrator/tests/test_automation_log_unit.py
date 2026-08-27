"""Testes unitários de lib/python/automation_log.py.

Cobre as duas modalidades de `make_logger` (legada em stderr e estruturada em
stdout, ver docs/logging-standard.md) e `ensure_utf8_streams`.
"""

import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib", "python"
    ),
)

from automation_log import (  # noqa: E402  pylint: disable=wrong-import-position
    emit_event,
    ensure_utf8_streams,
    make_logger,
    new_trace_id,
    resolve_trace_id,
)

_HUB_ENV = (
    "HUB_LOG_STRUCTURED",
    "HUB_AUTOMATION",
    "HUB_EXEC_ID",
    "HUB_TRACE_ID",
    "HUB_STEP",
)


def _clear_hub_env(monkeypatch: Any) -> None:
    for name in _HUB_ENV:
        monkeypatch.delenv(name, raising=False)


def test_ensure_utf8_streams_reconfigura_quando_stream_suporta(
    monkeypatch: Any,
) -> None:
    fake_stdout = MagicMock(spec=["reconfigure"])
    fake_stderr = MagicMock(spec=["reconfigure"])
    monkeypatch.setattr(sys, "stdout", fake_stdout)
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    ensure_utf8_streams()

    fake_stdout.reconfigure.assert_called_once_with(encoding="utf-8")
    fake_stderr.reconfigure.assert_called_once_with(encoding="utf-8")


def test_ensure_utf8_streams_nao_lanca_quando_stream_nao_suporta_reconfigure(
    monkeypatch: Any,
) -> None:
    """Regressão: checar `.encoding != "utf-8"` já lançava AttributeError num
    stream sem `.encoding` — `hasattr(..., "reconfigure")` é a guarda correta."""
    fake_stdout = MagicMock(spec=[])
    fake_stderr = MagicMock(spec=[])
    monkeypatch.setattr(sys, "stdout", fake_stdout)
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    ensure_utf8_streams()  # não deve lançar


def test_make_logger_modo_legado_escreve_em_stderr(
    monkeypatch: Any, capsys: Any
) -> None:
    _clear_hub_env(monkeypatch)
    log = make_logger("PY-TEST")
    log("mensagem de teste", "INFO", "EXEC-1")

    captured = capsys.readouterr()
    assert "[PY-TEST]" in captured.err
    assert "[INFO]" in captured.err
    assert "[ExecId:EXEC-1]" in captured.err
    assert "mensagem de teste" in captured.err
    assert captured.out == ""


def test_make_logger_modo_estruturado_emite_json_em_stdout(
    monkeypatch: Any, capsys: Any
) -> None:
    _clear_hub_env(monkeypatch)
    monkeypatch.setenv("HUB_LOG_STRUCTURED", "1")
    monkeypatch.setenv("HUB_AUTOMATION", "OBs Restricao Branco")
    monkeypatch.setenv("HUB_EXEC_ID", "CRON_6_x")
    monkeypatch.setenv("HUB_TRACE_ID", "orb-20260827T070140Z-a4f2")
    monkeypatch.setenv("HUB_STEP", "extract")

    log = make_logger("ORB-EXTRACT")
    log("Extração de 120 OBs", "WARN")

    captured = capsys.readouterr()
    assert captured.err == ""
    evt = json.loads(captured.out.strip())
    assert evt["component"] == "python_domain"
    assert evt["event"] == "log"
    assert evt["level"] == "WARN"
    assert evt["automation"] == "OBs Restricao Branco"
    assert evt["exec_id"] == "CRON_6_x"
    assert evt["trace_id"] == "orb-20260827T070140Z-a4f2"
    assert evt["step"] == "extract"
    assert evt["message"] == "Extração de 120 OBs"
    assert evt["ts"].endswith("Z")


def test_make_logger_estruturado_normaliza_error_para_erro_e_mascara(
    monkeypatch: Any, capsys: Any
) -> None:
    _clear_hub_env(monkeypatch)
    monkeypatch.setenv("HUB_LOG_STRUCTURED", "1")
    log = make_logger("ORB-EXTRACT")
    log("conectar password=supersecret", "ERROR", "EXEC-9")

    evt = json.loads(capsys.readouterr().out.strip())
    assert evt["level"] == "ERRO"
    assert "supersecret" not in evt["message"]
    assert "[REDACTED]" in evt["message"]


def test_emit_event_evento_desconhecido_vira_log(capsys: Any) -> None:
    emit_event(
        "bogus.event",
        "INFO",
        "x",
        automation="A",
        exec_id="E",
        trace_id="T",
    )
    evt = json.loads(capsys.readouterr().out.strip())
    assert evt["event"] == "log"


def test_resolve_trace_id_herda_do_ambiente(monkeypatch: Any) -> None:
    _clear_hub_env(monkeypatch)
    monkeypatch.setenv("HUB_TRACE_ID", "herdado-123")
    assert resolve_trace_id("orb") == "herdado-123"


def test_new_trace_id_formato() -> None:
    tid = new_trace_id("orb")
    assert tid.startswith("orb-")
    assert tid.endswith(tuple("0123456789abcdef"))
    assert "Z-" in tid
