# pylint: disable=all
# mypy: ignore-errors
"""Regressoes de recovery do Orchestrator no startup."""

from app import models
from app.timezone import get_now_local


def _execution(exec_id, automation_id, status):
    return models.Execution(
        id=exec_id,
        automation_id=automation_id,
        status=status,
        requested_by="TEST",
        started_at=get_now_local(),
    )


def test_startup_recovery_preserves_pending_and_fails_running(
    db_session,
    monkeypatch,
):
    import app.main as main_module

    auto = models.Automation(name="Recovery Task", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(_execution("EXEC_PENDING", auto.id, "PENDING"))
    db_session.add(_execution("EXEC_RUNNING", auto.id, "RUNNING"))
    db_session.commit()

    monkeypatch.setattr(main_module, "SessionLocal", lambda: db_session)

    main_module._cleanup_zombie_tasks()

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
    assert running.finished_at is not None
