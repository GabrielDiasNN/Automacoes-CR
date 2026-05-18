"""Serviços de visão agregada do painel operacional."""
# pylint: disable=relative-beyond-top-level,too-many-locals,not-callable

from datetime import timedelta
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..constants import ORCHESTRATOR_CONTRACT_VERSION, ORCHESTRATOR_VERSION
from ..timezone import get_now_local


def build_system_overview_payload(
    db: Session,
    scheduler: Any,
    health_payload: dict[str, Any],
    jobs: list[schemas.ScheduledJob],
    diagnostics_payload: dict[str, Any],
) -> dict[str, Any]:
    """Agrega métricas, estado operacional e diagnósticos para o dashboard."""
    next_run_lookup: dict[int, Any] = {}
    for job in jobs:
        if job.automation_id is None or not job.next_run_time:
            continue
        current = next_run_lookup.get(job.automation_id)
        if current is None or job.next_run_time < current:
            next_run_lookup[job.automation_id] = job.next_run_time

    window_start = get_now_local() - timedelta(hours=24)
    success_24h = (
        db.query(models.Execution)
        .filter(
            models.Execution.status == "SUCCESS",
            models.Execution.started_at >= window_start,
        )
        .count()
    )
    errors_24h = (
        db.query(models.Execution)
        .filter(
            models.Execution.status.in_(["ERROR", "TIMEOUT", "TERMINATED"]),
            models.Execution.started_at >= window_start,
        )
        .count()
    )
    pending_now = (
        db.query(models.Execution)
        .filter(models.Execution.status.in_(["PENDING", "RUNNING"]))
        .count()
    )

    status_rows = (
        db.query(models.Execution.status, func.count(models.Execution.id))
        .group_by(models.Execution.status)
        .all()
    )
    status_breakdown: dict[str, int] = {
        str(status): int(count) for status, count in status_rows
    }

    top_failures_rows = (
        db.query(
            models.Automation.id.label("automation_id"),
            models.Automation.name.label("automation_name"),
            func.count(models.Execution.id).label("failures"),
        )
        .join(models.Execution, models.Execution.automation_id == models.Automation.id)
        .filter(
            models.Execution.status.in_(["ERROR", "TIMEOUT", "TERMINATED"]),
            models.Execution.started_at >= window_start,
        )
        .group_by(models.Automation.id, models.Automation.name)
        .order_by(desc(func.count(models.Execution.id)))
        .limit(5)
        .all()
    )
    top_failures = [
        {
            "automation_id": row.automation_id,
            "automation_name": row.automation_name,
            "failures": row.failures,
        }
        for row in top_failures_rows
    ]

    recent_execs = (
        db.query(models.Execution)
        .options(joinedload(models.Execution.automation))
        .order_by(desc(models.Execution.started_at))
        .limit(12)
        .all()
    )
    recent_payload: list[schemas.ExecutionSummary] = []
    for ex in recent_execs:
        summary = schemas.ExecutionSummary.model_validate(ex)
        if ex.automation:
            summary.automation_name = ex.automation.name
        recent_payload.append(summary)

    automations = db.query(models.Automation).order_by(models.Automation.name.asc()).all()
    autos_payload: list[dict[str, Any]] = []
    for auto in automations:
        auto_id = int(auto.id)
        last_exec = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto_id)
            .order_by(desc(models.Execution.started_at))
            .first()
        )
        autos_payload.append(
            {
                "id": auto_id,
                "name": auto.name,
                "enabled": auto.enabled,
                "test_mode": auto.test_mode,
                "last_status": last_exec.status if last_exec else None,
                "next_run": schemas.format_dt_br(next_run_lookup.get(auto_id)),
            }
        )

    next_window = min((job.next_run_time for job in jobs if job.next_run_time), default=None)

    return {
        "generated_at": get_now_local().isoformat(),
        "version": ORCHESTRATOR_VERSION,
        "schema_version": diagnostics_payload["schema_version"],
        "contract_version": diagnostics_payload.get(
            "contract_version",
            ORCHESTRATOR_CONTRACT_VERSION,
        ),
        "kpis": {
            "active_automations": sum(1 for auto in automations if auto.enabled),
            "success_24h": success_24h,
            "errors_24h": errors_24h,
            "pending_now": pending_now,
            "next_window": schemas.format_dt_br(next_window),
        },
        "health": health_payload,
        "status_breakdown": status_breakdown,
        "jobs": [job.model_dump() for job in jobs],
        "recent": [item.model_dump() for item in recent_payload],
        "automations": autos_payload,
        "top_failures": top_failures,
        "scheduler": {
            "running": scheduler.running,
            "jobs_loaded": len(scheduler.get_jobs()),
        },
        "queue": {
            "active_count": pending_now,
            "by_status": status_breakdown,
        },
        "diagnostics": diagnostics_payload,
    }
