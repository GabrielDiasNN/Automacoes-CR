"""Contrato do purge: manter sempre as últimas 50 execuções por automação."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import database as db_module
from app import models
from app.database import purge_old_executions
from app.timezone import get_now_local


def _seed_automation(db: Session, name: str) -> int:
    automation = models.Automation(name=name, script_path="test/mock_success.ps1")
    db.add(automation)
    db.commit()
    return int(automation.id)


def _seed_executions(
    db: Session, automation_id: int, count: int, age_days: int
) -> None:
    base = get_now_local() - timedelta(days=age_days)
    for i in range(count):
        db.add(
            models.Execution(
                id=f"exec-{automation_id}-{age_days}-{i:04d}",
                automation_id=automation_id,
                status="SUCCESS",
                started_at=base + timedelta(minutes=i),
                finished_at=base + timedelta(minutes=i + 1),
            )
        )
    db.commit()


def test_purge_preserva_ultimas_50_por_automacao(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(bind=db_session.get_bind())
    )

    automation_id = _seed_automation(db_session, "auto-purge-a")
    # 80 execuções todas mais antigas que a retenção: sem a regra das últimas
    # 50, o purge apagaria as 80.
    _seed_executions(db_session, automation_id, count=80, age_days=120)

    removed = purge_old_executions(retention_days=90)

    assert removed == 30
    remaining = (
        db_session.query(models.Execution)
        .filter(models.Execution.automation_id == automation_id)
        .count()
    )
    assert remaining == 50


def test_purge_remove_apenas_alem_do_cutoff(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(bind=db_session.get_bind())
    )

    automation_id = _seed_automation(db_session, "auto-purge-b")
    _seed_executions(db_session, automation_id, count=10, age_days=120)
    _seed_executions(db_session, automation_id, count=60, age_days=1)

    removed = purge_old_executions(retention_days=90)

    # As 60 recentes ocupam o top-50 + estão dentro da retenção; das 10 antigas
    # nenhuma está no top-50, então todas saem.
    assert removed == 10
