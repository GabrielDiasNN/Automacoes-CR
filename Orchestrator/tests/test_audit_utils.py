# pylint: disable=all
# mypy: ignore-errors
"""Testes unitários do log_audit (auditoria best-effort com JSON válido)."""

import json

from app.utils import log_audit


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, entry):
        self.added.append(entry)


class _BrokenSession:
    def add(self, entry):
        raise RuntimeError("db indisponível")


def test_log_audit_details_longos_geram_json_valido():
    db = _FakeSession()
    details = json.dumps({"payload": "X" * 50000})

    entry = log_audit(db, "QA", "TEST", 1, "tester", details)

    assert db.added == [entry]
    parsed = json.loads(entry.details)
    assert parsed["truncated"] is True
    assert "correlation_id" in parsed


def test_log_audit_details_nao_json_viram_message():
    db = _FakeSession()

    entry = log_audit(db, "QA", "TEST", 1, "tester", "texto livre não-JSON")

    parsed = json.loads(entry.details)
    assert parsed["message"] == "texto livre não-JSON"


def test_log_audit_nao_propaga_falha_do_banco():
    entry = log_audit(_BrokenSession(), "QA", "TEST", 1, "tester", None)

    assert entry is not None
    parsed = json.loads(entry.details)
    assert "correlation_id" in parsed
