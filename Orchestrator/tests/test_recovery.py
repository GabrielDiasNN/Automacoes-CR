"""Regressoes de recovery do Orchestrator no startup."""

from typing import Any

import app.main as main_module
import pytest
from app import models
from app.timezone import get_now_local


def _execution(
    exec_id: str,
    automation_id: Any,
    status: str,
    worker_instance_id: str | None = "worker-teste",
) -> models.Execution:
    """Execução de teste, por padrão COM dono registrado.

    Desde 31/07/2026 `mark_running_tasks_as_failed_by_reboot` só alcança
    execuções que têm `worker_instance_id` — é o que separa a órfã de um worker
    morto da telemetria externa viva, que não tem dono e seguia sendo carimbada
    como interrompida por reboot enquanto o processo real rodava.
    """
    return models.Execution(
        id=exec_id,
        automation_id=automation_id,
        status=status,
        requested_by="TEST",
        started_at=get_now_local(),
        worker_instance_id=worker_instance_id,
    )


def test_startup_recovery_preserves_pending_and_fails_running(
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auto = models.Automation(name="Recovery Task", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(_execution("EXEC_PENDING", auto.id, "PENDING"))
    db_session.add(_execution("EXEC_RUNNING", auto.id, "RUNNING"))
    db_session.commit()

    monkeypatch.setattr(main_module, "SessionLocal", lambda: db_session)

    main_module._cleanup_zombie_tasks()  # pylint: disable=protected-access

    statuses = {
        row.id: row.status
        for row in db_session.query(models.Execution)
        .order_by(models.Execution.id)
        .all()
    }
    assert statuses["EXEC_PENDING"] == "PENDING"
    assert statuses["EXEC_RUNNING"] == "FAILED_BY_REBOOT"

    running = (
        db_session.query(models.Execution)
        .filter(models.Execution.id == "EXEC_RUNNING")
        .first()
    )
    assert "[REBOOT] Interrompida." in running.logs
    assert (
        "[RECOVERY_AUDIT] actor=SYSTEM_STARTUP action=MARK_FAILED_BY_REBOOT"
        in running.logs
    )
    assert running.finished_at is not None
    assert running.failure_reason == "ORCHESTRATOR_REBOOT"
    assert running.recovery_action == "REQUEUE_IF_SAFE"
