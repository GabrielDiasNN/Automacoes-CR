"""Testes unitários do log_audit (auditoria best-effort com JSON válido)."""

import json
from dataclasses import dataclass, field
from typing import Any, cast

from app.utils import log_audit
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session


@dataclass
class _FakeSession:
    """Dublê de sessão apenas para capturar chamadas de add()."""

    added: list[Any] = field(default_factory=list)

    def add(self, entry: Any) -> None:
        self.added.append(entry)


@dataclass
class _BrokenSession:
    """Dublê de sessão que simula falha de banco em add()."""

    def add(self, entry: Any) -> None:
        raise InvalidRequestError("db indisponível")


def test_log_audit_details_longos_geram_json_valido() -> None:
    db = _FakeSession()
    details = json.dumps({"payload": "X" * 50000})

    entry = log_audit(cast(Session, db), "QA", "TEST", 1, "tester", details)

    assert db.added == [entry]
    parsed = json.loads(str(entry.details))
    assert parsed["truncated"] is True
    assert "correlation_id" in parsed


def test_log_audit_details_nao_json_viram_message() -> None:
    db = _FakeSession()

    entry = log_audit(
        cast(Session, db), "QA", "TEST", 1, "tester", "texto livre não-JSON"
    )

    parsed = json.loads(str(entry.details))
    assert parsed["message"] == "texto livre não-JSON"


def test_log_audit_nao_propaga_falha_do_banco() -> None:
    entry = log_audit(cast(Session, _BrokenSession()), "QA", "TEST", 1, "tester", None)

    assert entry is not None
    parsed = json.loads(str(entry.details))
    assert "correlation_id" in parsed
