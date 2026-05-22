"""Serviços de visão agregada do painel operacional (C3, C4)."""

# pylint: disable=relative-beyond-top-level,too-many-locals,not-callable

from datetime import timedelta
from typing import Any

from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..constants import ORCHESTRATOR_CONTRACT_VERSION, ORCHESTRATOR_VERSION
from ..timezone import get_now_local
from . import metrics  # pylint: disable=no-name-in-module


def _build_next_run_lookup(jobs: list[schemas.ScheduledJob]) -> dict[int, Any]:
    """Normaliza o próximo disparo por automação em datetime comparável."""
    next_run_lookup: dict[int, Any] = {}
    for job in jobs:
        if job.automation_id is None or not job.next_run_time:
            continue
        candidate = schemas.parse_dt_br(job.next_run_time)
        if candidate is None:
            continue
        current = next_run_lookup.get(job.automation_id)
        if current is None or candidate < current:
            next_run_lookup[job.automation_id] = candidate
    return next_run_lookup


def build_system_overview_payload(
    db: Session,
    scheduler: Any,
    health_payload: dict[str, Any],
    jobs: list[schemas.ScheduledJob],
    diagnostics_payload: dict[str, Any],
) -> dict[str, Any]:
    """Agrega métricas, estado operacional e diagnósticos para o dashboard (C3, C4)."""
    next_run_lookup = _build_next_run_lookup(jobs)

    window_start = get_now_local() - timedelta(hours=24)
    success_24h, errors_24h = metrics.get_success_errors_count_24h(db)

    pending_now = (
        db.query(models.Execution)
        .filter(models.Execution.status.in_(["PENDING", "RUNNING"]))
        .count()
    )

    status_breakdown = metrics.get_status_breakdown(db)
    top_failures = [
        {
            "automation_id": item["automation_id"],
            "automation_name": item["automation_name"],
            "failures": item["failures_24h"],
        }
        for item in metrics.get_failure_hotspots_24h(db)
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

    automations = (
        db.query(models.Automation).order_by(models.Automation.name.asc()).all()
    )

    # 1. Buscar métricas agregadas por automação (24h)
    automation_metrics_rows = (
        db.query(
            models.Execution.automation_id.label("automation_id"),
            func.sum(case((models.Execution.status == "SUCCESS", 1), else_=0)).label(
                "success_24h"
            ),
            func.sum(
                case(
                    (
                        models.Execution.status.in_(["ERROR", "TIMEOUT", "TERMINATED"]),
                        1,
                    ),
                    else_=0,
                )
            ).label("failures_24h"),
            func.sum(case((models.Execution.status == "TIMEOUT", 1), else_=0)).label(
                "timeouts_24h"
            ),
            func.avg(models.Execution.duration_seconds).label("avg_duration_24h_seconds"),
        )
        .filter(models.Execution.started_at >= window_start)
        .group_by(models.Execution.automation_id)
        .all()
    )
    metrics_by_automation = {
        int(row.automation_id): row for row in automation_metrics_rows if row.automation_id
    }

    # 2. Buscar duração média SUCCESS para cálculo do SLA sem N+1 (C3)
    sla_metrics = metrics.get_sla_metrics_by_automation_24h(db)

    autos_payload: list[dict[str, Any]] = []
    for auto in automations:
        auto_id = int(auto.id)
        metrics_row = metrics_by_automation.get(auto_id)
        schedule_value = auto.schedule if isinstance(auto.schedule, str) else None
        try:
            parsed_schedule = (
                schemas.parse_schedule(schedule_value) if schedule_value else None
            )
        except (TypeError, ValueError):
            parsed_schedule = None

        last_exec = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto_id)
            .order_by(desc(models.Execution.started_at))
            .first()
        )

        # --- Cálculo de SLA Otimizado (C3) ---
        sla_minutes = auto.sla_minutes
        sla_status = "unknown"
        sla_avg_duration_minutes: float | None = None
        if sla_minutes:
            metrics_entry = sla_metrics.get(auto_id)
            if metrics_entry is not None:
                avg_min = metrics_entry["avg_duration_minutes"]
                sla_avg_duration_minutes = avg_min
                ratio = avg_min / sla_minutes
                if ratio <= 0.80:
                    sla_status = "ok"
                elif ratio <= 1.0:
                    sla_status = "at_risk"
                else:
                    sla_status = "violated"
            else:
                sla_status = "ok"  # sem execuções recentes = sem violação

        autos_payload.append(
            {
                "id": auto_id,
                "name": auto.name,
                "description": auto.description,
                "script_path": auto.script_path,
                "enabled": auto.enabled,
                "test_mode": auto.test_mode,
                "queue_group": auto.queue_group,
                "max_runtime_minutes": auto.max_runtime_minutes,
                "max_retries": auto.max_retries,
                "cooldown_minutes": auto.cooldown_minutes,
                "notification_channels": auto.notification_channels,
                "sla_minutes": sla_minutes,
                "sla_status": sla_status,
                "sla_avg_duration_minutes": sla_avg_duration_minutes,
                "success_24h": int(getattr(metrics_row, "success_24h", 0) or 0),
                "failures_24h": int(getattr(metrics_row, "failures_24h", 0) or 0),
                "timeouts_24h": int(getattr(metrics_row, "timeouts_24h", 0) or 0),
                "avg_duration_24h_seconds": (
                    round(
                        float(
                            getattr(metrics_row, "avg_duration_24h_seconds", 0) or 0
                        ),
                        2,
                    )
                    if getattr(metrics_row, "avg_duration_24h_seconds", None)
                    is not None
                    else None
                ),
                "last_status": last_exec.status if last_exec else None,
                "last_execution_id": last_exec.id if last_exec else None,
                "last_execution_started_at": schemas.format_dt_br(
                    last_exec.started_at if last_exec else None
                ),
                "last_execution_finished_at": schemas.format_dt_br(
                    last_exec.finished_at if last_exec else None
                ),
                "last_execution_duration_seconds": (
                    round(float(last_exec.duration_seconds), 2)
                    if last_exec and last_exec.duration_seconds is not None
                    else None
                ),
                "last_failure_reason": last_exec.failure_reason if last_exec else None,
                "last_recovery_action": last_exec.recovery_action if last_exec else None,
                "last_requested_by": last_exec.requested_by if last_exec else None,
                "next_run": schemas.format_dt_br(next_run_lookup.get(auto_id)),
                "schedule_summary": schemas.describe_schedule_payload(parsed_schedule),
                "next_runs_preview": schemas.preview_next_runs(parsed_schedule, 3),
                "active_execution_count": (
                    1 if last_exec and last_exec.status in ["PENDING", "RUNNING"] else 0
                ),
                "pending_count": (
                    1 if last_exec and last_exec.status in ["PENDING", "RUNNING"] else 0
                ),
                "operational_state": (
                    "paused"
                    if not auto.enabled
                    else "in_progress"
                    if last_exec and last_exec.status in ["PENDING", "RUNNING"]
                    else "attention"
                    if int(getattr(metrics_row, "failures_24h", 0) or 0) > 0
                    else "healthy"
                    if int(getattr(metrics_row, "success_24h", 0) or 0) > 0
                    else "idle"
                ),
            }
        )

    next_window = min(
        (job.next_run_time for job in jobs if job.next_run_time), default=None
    )

    return {
        "generated_at": schemas.format_dt_br(get_now_local()),
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
            "active_by_priority": (
                diagnostics_payload.get("queue", {}).get("active_by_priority", {})
            ),
        },
        "diagnostics": diagnostics_payload,
    }
