"""Serviços de visão agregada do painel operacional (C3, C4)."""

# pylint: disable=relative-beyond-top-level,too-many-locals,not-callable

from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..constants import ORCHESTRATOR_CONTRACT_VERSION, ORCHESTRATOR_VERSION
from ..timezone import get_now_local
from .automation_snapshot import (
    build_automation_response,
    build_next_run_lookup,
)
from . import metrics  # pylint: disable=no-name-in-module


def build_system_overview_payload(
    db: Session,
    scheduler: Any,
    health_payload: dict[str, Any],
    jobs: list[schemas.ScheduledJob],
    diagnostics_payload: dict[str, Any],
) -> dict[str, Any]:
    """Agrega métricas, estado operacional e diagnósticos para o dashboard (C3, C4)."""
    next_run_lookup = build_next_run_lookup(jobs)

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
    automation_ids = [int(auto.id) for auto in automations]
    metrics_by_automation = metrics.get_automation_metrics_24h(db, automation_ids)
    latest_execution_by_automation = metrics.get_latest_execution_snapshot_by_automation(
        db, automation_ids
    )

    # 2. Buscar duração média SUCCESS para cálculo do SLA sem N+1 (C3)
    sla_metrics = metrics.get_sla_metrics_by_automation_24h(db)

    autos_payload: list[dict[str, Any]] = []
    for auto in automations:
        auto_id = int(auto.id)
        metrics_row = metrics_by_automation.get(auto_id, {})
        response = build_automation_response(
            auto=auto,
            next_run_lookup=next_run_lookup,
            latest_execution_lookup=latest_execution_by_automation,
            metrics_24h_lookup=metrics_by_automation,
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

        auto_payload = response.model_dump()
        auto_payload["sla_status"] = sla_status
        auto_payload["sla_avg_duration_minutes"] = sla_avg_duration_minutes
        auto_payload["avg_duration_24h_seconds"] = metrics_row.get(
            "avg_duration_24h_seconds"
        )
        autos_payload.append(auto_payload)

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
        "trend_summary": diagnostics_payload.get("trend_summary", {}),
        "diagnostics": diagnostics_payload,
    }
