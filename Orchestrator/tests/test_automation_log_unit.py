"""Testes unitários de lib/python/automation_log.py (make_logger, ensure_utf8_streams)."""

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
    ensure_utf8_streams,
    make_logger,
)


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
    """Regressão: checar `.encoding != "utf-8"` (padrão antigo, divergente
    entre scripts) já lançava AttributeError num stream sem `.encoding` —
    `hasattr(..., "reconfigure")` é a guarda correta."""
    fake_stdout = MagicMock(spec=[])
    fake_stderr = MagicMock(spec=[])
    monkeypatch.setattr(sys, "stdout", fake_stdout)
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    ensure_utf8_streams()  # não deve lançar


def test_make_logger_escreve_em_stderr_com_tag_e_exec_id(capsys: Any) -> None:
    log = make_logger("PY-TEST")
    log("mensagem de teste", "INFO", "EXEC-1")

    captured = capsys.readouterr()
    assert "[PY-TEST]" in captured.err
    assert "[INFO]" in captured.err
    assert "[ExecId:EXEC-1]" in captured.err
    assert "mensagem de teste" in captured.err
    assert captured.out == ""
