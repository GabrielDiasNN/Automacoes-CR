"""Contrato do purge: manter sempre as últimas 50 execuções por automação.

Cobre também `purge_old_snapshots` (achado nº 12): job diário sem teste, que
retorna `0` em qualquer exceção — o `0` de "falhou" era indistinguível do `0`
de "não havia nada a remover". Os testes afirmam o **inteiro retornado**.
"""

from datetime import timedelta
from typing import Any

import pytest
from app import database as db_module, models
from app.database import purge_old_executions, purge_old_snapshots
from app.timezone import get_now_local
from sqlalchemy.orm import Session, sessionmaker


def _seed_automation(db: Session, name: str) -> int:
    automation = models.Automation(name=name, script_path="test/mock_success.ps1")
    db.add(automation)
    db.commit()
    return int(automation.id)


def _seed_executions(
    db: Session,
    automation_id: int,
    count: int,
    age_days: int,
    status: str = "SUCCESS",
) -> None:
    base = get_now_local() - timedelta(days=age_days)
    for i in range(count):
        db.add(
            models.Execution(
                id=f"exec-{automation_id}-{age_days}-{status}-{i:04d}",
                automation_id=automation_id,
                status=status,
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


def test_purge_remove_execucoes_partial_antigas(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regressão do achado #1: PARTIAL é status terminal e deve ser purgado; a
    # lista hardcoded antiga o omitia, preservando PARTIAL indefinidamente.
    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(bind=db_session.get_bind())
    )

    automation_id = _seed_automation(db_session, "auto-purge-partial")
    # 60 PARTIAL antigas: 50 preservadas pelo top-50, 10 além do cutoff saem.
    _seed_executions(
        db_session, automation_id, count=60, age_days=120, status="PARTIAL"
    )

    removed = purge_old_executions(retention_days=90)

    assert removed == 10
    remaining = (
        db_session.query(models.Execution)
        .filter(models.Execution.automation_id == automation_id)
        .count()
    )
    assert remaining == 50


def _seed_snapshots(db: Session, count: int, age_days: int) -> None:
    base = get_now_local() - timedelta(days=age_days)
    for i in range(count):
        db.add(
            models.SystemHealthSnapshot(
                timestamp=base + timedelta(minutes=i),
                overall_status="healthy",
            )
        )
    db.commit()


def test_purge_snapshots_remove_apenas_alem_do_cutoff(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(bind=db_session.get_bind())
    )
    _seed_snapshots(db_session, count=5, age_days=40)
    _seed_snapshots(db_session, count=3, age_days=10)

    removed = purge_old_snapshots(retention_days=30)

    assert removed == 5  # inteiro exato — distingue "removeu 5" de "0 / erro"
    assert db_session.query(models.SystemHealthSnapshot).count() == 3


def test_purge_snapshots_retorna_zero_quando_nada_a_remover(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(bind=db_session.get_bind())
    )
    _seed_snapshots(db_session, count=4, age_days=5)

    assert purge_old_snapshots(retention_days=30) == 0
    assert db_session.query(models.SystemHealthSnapshot).count() == 4


def test_purge_snapshots_engole_excecao_mas_loga(
    db_session: Session,  # pylint: disable=unused-argument
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def estoura(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("banco travado")

    monkeypatch.setattr(db_module, "session_scope", estoura)

    with caplog.at_level("ERROR", logger="orchestrator"):
        removed = purge_old_snapshots(retention_days=30)

    assert removed == 0
    assert any("purge de snapshots" in r.message.lower() for r in caplog.records)
