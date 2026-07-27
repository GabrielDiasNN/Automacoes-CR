"""Helpers compartilhados para snapshots operacionais de automações."""

# pylint: disable=relative-beyond-top-level,no-name-in-module

from typing import Any

from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import EXECUTION_ACTIVE_STATUSES
from . import metrics_queries as metrics


def build_next_run_lookup(jobs: list[schemas.ScheduledJob]) -> dict[int, Any]:
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


def _resolve_operational_state(
    auto: models.Automation,
    last_status: str | None,
    failures_24h: int,
    success_24h: int,
) -> str:
    """Deriva o estado operacional exibido no dashboard."""
    if not auto.enabled:
        return "paused"
    if last_status in EXECUTION_ACTIVE_STATUSES:
        return "in_progress"
    if failures_24h > 0:
        return "attention"
    if success_24h > 0:
        return "healthy"
    return "idle"


def build_automation_response(
    auto: models.Automation,
    next_run_lookup: dict[int, Any] | None = None,
    latest_execution_lookup: dict[int, dict[str, Any]] | None = None,
    metrics_24h_lookup: dict[int, dict[str, Any]] | None = None,
) -> schemas.AutomationResponse:
    """Monta o contrato completo consumido pela aba de automações."""
    auto_id = int(auto.id)
    auto_resp = schemas.AutomationResponse.model_validate(auto)
    latest_exec = (
        latest_execution_lookup.get(auto_id, {}) if latest_execution_lookup else {}
    )
    metrics_row = metrics_24h_lookup.get(auto_id, {}) if metrics_24h_lookup else {}

    success_24h = int(metrics_row.get("success_24h", 0) or 0)
    failures_24h = int(metrics_row.get("failures_24h", 0) or 0)
    timeouts_24h = int(metrics_row.get("timeouts_24h", 0) or 0)
    last_status = latest_exec.get("status")
    active_execution_count = 1 if last_status in EXECUTION_ACTIVE_STATUSES else 0

    auto_resp.last_status = str(last_status) if last_status else None
    auto_resp.last_execution_id = latest_exec.get("id")
    auto_resp.last_execution_started_at = schemas.format_dt_br(
        latest_exec.get("started_at")
    )
    auto_resp.last_execution_finished_at = schemas.format_dt_br(
        latest_exec.get("finished_at")
    )
    auto_resp.last_execution_duration_seconds = latest_exec.get("duration_seconds")
    auto_resp.last_failure_reason = latest_exec.get("failure_reason")
    auto_resp.last_recovery_action = latest_exec.get("recovery_action")
    auto_resp.last_requested_by = latest_exec.get("requested_by")
    auto_resp.next_run = (
        schemas.format_dt_br(next_run_lookup.get(auto_id)) if next_run_lookup else None
    )
    if auto_resp.next_run is None:
        try:
            parsed_schedule = schemas.parse_schedule(auto_resp.schedule)
        except (TypeError, ValueError):
            parsed_schedule = None
        if parsed_schedule:
            next_runs_preview = schemas.preview_next_runs(parsed_schedule, 1)
            if next_runs_preview:
                auto_resp.next_run = next_runs_preview[0]
    auto_resp.success_24h = success_24h
    auto_resp.failures_24h = failures_24h
    auto_resp.timeouts_24h = timeouts_24h
    auto_resp.error_24h = failures_24h
    auto_resp.active_execution_count = active_execution_count
    auto_resp.pending_count = active_execution_count
    auto_resp.operational_state = _resolve_operational_state(
        auto, auto_resp.last_status, failures_24h, success_24h
    )

    try:
        parsed_schedule = schemas.parse_schedule(auto_resp.schedule)
    except (TypeError, ValueError):
        parsed_schedule = None
    auto_resp.schedule_type = (
        parsed_schedule.get("schedule_type") if parsed_schedule else "manual"
    )
    auto_resp.schedule_summary = schemas.describe_schedule_payload(parsed_schedule)
    auto_resp.next_runs_preview = schemas.preview_next_runs(parsed_schedule, 3)
    return auto_resp


def build_automation_response_batch(
    automations: list[models.Automation],
    next_run_lookup: dict[int, Any] | None = None,
    latest_execution_lookup: dict[int, dict[str, Any]] | None = None,
    metrics_24h_lookup: dict[int, dict[str, Any]] | None = None,
) -> list[schemas.AutomationResponse]:
    """Aplica o helper em lote mantendo o contrato consistente entre endpoints."""
    return [
        build_automation_response(
            auto=auto,
            next_run_lookup=next_run_lookup,
            latest_execution_lookup=latest_execution_lookup,
            metrics_24h_lookup=metrics_24h_lookup,
        )
        for auto in automations
    ]


def load_snapshot_dependencies(
    db: Session, automations: list[models.Automation]
) -> dict[str, dict[int, Any]]:
    """Carrega todos os lookups necessários para snapshots em uma passada."""
    automation_ids = [int(auto.id) for auto in automations]
    return {
        "metrics_24h": metrics.get_automation_metrics_24h(db, automation_ids),
        "latest_execution": metrics.get_latest_execution_snapshot_by_automation(
            db, automation_ids
        ),
    }
