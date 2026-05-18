# pylint: disable=all
# mypy: ignore-errors
"""Regressoes do contrato de fila entre Orchestrator e Worker."""

import time

from app import models
from app.timezone import get_now_local
from worker import _finalize_terminated_task, claim_next_task


def _add_execution(db_session, exec_id, automation_id, priority="NORMAL"):
    db_session.add(
        models.Execution(
            id=exec_id,
            automation_id=automation_id,
            status="PENDING",
            priority=priority,
            requested_by="TEST",
            started_at=get_now_local(),
        )
    )


def test_claim_next_task_marks_only_one_pending_execution(db_session):
    auto = models.Automation(name="Worker Claim", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()

    _add_execution(db_session, "EXEC_LOW", auto.id, "LOW")
    _add_execution(db_session, "EXEC_HIGH", auto.id, "HIGH")
    _add_execution(db_session, "EXEC_NORMAL", auto.id, "NORMAL")
    db_session.commit()

    claimed = claim_next_task(db_session)

    assert claimed == "EXEC_HIGH"
    statuses = {
        row.id: row.status
        for row in db_session.query(models.Execution)
        .order_by(models.Execution.id)
        .all()
    }
    assert statuses == {
        "EXEC_HIGH": "RUNNING",
        "EXEC_LOW": "PENDING",
        "EXEC_NORMAL": "PENDING",
    }


def test_worker_long_poll_endpoint_is_not_rate_limit_exempt():
    from app.middleware import RATE_LIMIT_EXEMPT_PATHS

    assert "/api/system/wait-for-task" not in RATE_LIMIT_EXEMPT_PATHS


def test_finalize_terminated_task_persists_terminal_metadata(db_session):
    auto = models.Automation(name="Worker Stop", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_STOP",
            automation_id=auto.id,
            status="RUNNING",
            requested_by="TEST",
            started_at=get_now_local(),
            logs="pre-stop\n",
        )
    )
    db_session.commit()

    _finalize_terminated_task(
        db_session,
        "EXEC_STOP",
        ["runtime log\n"],
        time.time() - 3,
    )

    stopped = (
        db_session.query(models.Execution)
        .filter(models.Execution.id == "EXEC_STOP")
        .first()
    )
    assert stopped.status == "TERMINATED"
    assert stopped.exit_code == -15
    assert stopped.duration_seconds >= 3
    assert stopped.failure_reason == "USER_TERMINATED"
    assert stopped.recovery_action == "REVIEW_LOGS_BEFORE_REQUEUE"
    assert "runtime log" in stopped.logs
    assert "[INTERROMPIDO PELO USUARIO]" in stopped.logs
