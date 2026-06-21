# pylint: disable=protected-access, wrong-import-position, import-outside-toplevel
"""Smoke tests da automação de Receitas Emitidas."""

import io
import json
import os
import sys
from typing import Any

AUTOMATION_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Receitas Emitidas")
)
sys.path.append(AUTOMATION_PATH)

import generate_html_report


def test_html_escape_converts_portuguese_entities() -> None:
    """Garante que o HTML final protege caracteres PT-BR em entidades."""
    escaped = generate_html_report.html_escape("Tinturaria & ação")
    assert "&amp;" in escaped
    assert "&ccedil;" in escaped or "ç" not in escaped
    assert "&atilde;" in escaped or "ã" not in escaped


def test_generate_html_smoke_from_stdin(monkeypatch: Any) -> None:
    """Executa o gerador HTML com payload sintético e valida o conteúdo mínimo."""
    payload = [
        {
            "MQ_TING": "MQ-01",
            "GRUPO": "10",
            "NUMERO_OB": "OB-1001",
            "INICIO_TING": "2026-05-24T14:30:00",
        },
        {
            "MQ_TING": "MQ-01",
            "GRUPO": "10",
            "NUMERO_OB": "OB-1002",
            "INICIO_TING": "2026-05-24T15:00:00",
        },
    ]

    stdin_buffer = io.StringIO(json.dumps(payload, ensure_ascii=False))
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    monkeypatch.setattr(sys, "argv", ["generate_html_report.py", "EXEC_SMOKE"])
    monkeypatch.setattr(sys, "stdin", stdin_buffer)
    monkeypatch.setattr(sys, "stdout", stdout_buffer)
    monkeypatch.setattr(sys, "stderr", stderr_buffer)

    generate_html_report.generate_html()

    html = stdout_buffer.getvalue()
    assert "Controle de Receitas Emitidas" in html
    assert "MQ-01" in html
    assert "OB-1001" in html
    assert "OB-1002" in html
