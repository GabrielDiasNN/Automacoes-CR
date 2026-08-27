"""Testes de Tools/log_event_validator.py contra docs/log-event.schema.json."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Tools")
)

from log_event_validator import (  # noqa: E402  pylint: disable=wrong-import-position,import-error
    _Enums,
    _load_schema,
    validate_event,
    validate_file,
)

ENUMS = _Enums(_load_schema())

_BASE = {
    "ts": "2026-08-27T07:01:51Z",
    "level": "INFO",
    "component": "ps_script",
    "event": "log",
    "automation": "OBs Restricao Branco",
    "exec_id": "CRON_6_x",
    "trace_id": "orb-20260827T070140Z-a4f2",
    "message": "linha ok",
}


def test_evento_minimo_valido() -> None:
    assert validate_event(dict(_BASE), ENUMS) == []


def test_ts_fora_do_formato_utc_z() -> None:
    evt = {**_BASE, "ts": "2026-08-27 07:01:51"}
    assert any("ISO-8601" in e for e in validate_event(evt, ENUMS))


def test_campo_desconhecido_e_rejeitado() -> None:
    evt = {**_BASE, "foo": 1}
    assert any("desconhecido" in e for e in validate_event(evt, ENUMS))


def test_step_end_exige_step_ok_duration() -> None:
    evt = {**_BASE, "event": "step.end"}
    erros = validate_event(evt, ENUMS)
    assert any("'step'" in e for e in erros)
    assert any("'ok'" in e for e in erros)
    assert any("'duration_ms'" in e for e in erros)


def test_step_custom_exige_step_name() -> None:
    evt = {**_BASE, "event": "step.start", "step": "custom"}
    assert any("step_name" in e for e in validate_event(evt, ENUMS))


def test_execution_end_completo_valido() -> None:
    evt = {
        **_BASE,
        "event": "execution.end",
        "outcome_code": 2,
        "outcome_reason": "idempotente",
        "duration_ms": 100,
        "steps": [{"step": "extract", "ok": True, "duration_ms": 80}],
    }
    assert validate_event(evt, ENUMS) == []


def test_validate_file_modo_rollout_ignora_linha_legada(tmp_path: Path) -> None:
    alvo = tmp_path / "x.jsonl"
    alvo.write_text(
        '{"timestamp":"2026-08-27","level":"INFO","message":"legada"}\n'
        + '{"ts":"2026-08-27 ruim","level":"INFO","component":"ps_script","event":"log",'
        + '"automation":"A","exec_id":"E","trace_id":"T","message":"nova ruim"}\n',
        encoding="utf-8",
    )
    # sem rollout: as duas linhas contam (a legada não casa o schema)
    assert len(validate_file(alvo, ENUMS, rollout=False)) >= 2
    # com rollout: só a linha nova (tem trace_id) é cobrada
    problemas = validate_file(alvo, ENUMS, rollout=True)
    assert len(problemas) == 1
    assert "ISO-8601" in problemas[0]


def test_load_schema_tem_enums_esperados() -> None:
    assert "python_domain" in ENUMS.component
    assert "retry.attempt" in ENUMS.event
    assert "custom" in ENUMS.step


def test_golden_samples_conformes_ao_schema() -> None:
    """docs/log-event.samples.jsonl e a ancora de conformidade do CI: todo
    evento nele deve validar no modo estrito (sem --rollout)."""
    samples = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "log-event.samples.jsonl"
    )
    assert samples.exists(), f"golden samples ausente: {samples}"
    problemas = validate_file(samples, ENUMS, rollout=False)
    assert problemas == [], "\n".join(problemas)
    # cobertura de tipos: todo `event` do enum aparece pelo menos uma vez
    linhas = [
        json.loads(x)
        for x in samples.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    eventos = {e["event"] for e in linhas}
    assert ENUMS.event.issubset(eventos), f"faltam exemplos de: {ENUMS.event - eventos}"
