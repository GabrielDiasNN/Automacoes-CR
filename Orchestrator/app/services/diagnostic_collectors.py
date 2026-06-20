"""Utilitários e coletores de diagnóstico: findings, DB queries, helpers de tempo.

Extraído de ``system_diagnostics`` para isolar a camada de coleta de dados
(queries SQLAlchemy + utilitários de tempo) da lógica de análise e montagem.
"""

# pylint: disable=relative-beyond-top-level,not-callable

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import (
    DIAGNOSTIC_DEFAULT_MAX_RUNTIME_MINUTES,
    DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS,
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
)
from ..timezone import get_now_local
from .scheduler_runtime import extract_automation_id_from_job


def add_finding(
    findings: list[dict[str, Any]],
    severity: str,
    component: str,
    message: str,
    details: dict[str, Any],
) -> None:
    """Acrescenta um finding padronizado à lista de diagnóstico."""
    findings.append(
        {
            "severity": severity,
            "component": component,
            "message": message,
            "action_hint": details["action_hint"],
            "action_code": details.get("action_code"),
            "action_label": details.get("action_label"),
            "impact": details.get(
                "impact",
                "Monitorar o componente e validar a operação antes de novas ações.",
            ),
            "priority": int(details.get("priority", 3)),
        }
    )


def seconds_since(value: datetime | None) -> float:
    """Retorna segundos decorridos desde ``value``, ou 0 se ausente."""
    if not value:
        return 0.0
    return round((get_now_local() - value).total_seconds(), 2)


def coerce_datetime(value: Any) -> datetime | None:
    """Converte ``value`` para datetime ou retorna None."""
    return value if isinstance(value, datetime) else None


def collect_scheduler_inconsistencies(db: Session, scheduler: Any) -> list[str]:
    """Detecta divergências entre jobs em memória e automações habilitadas no banco."""
    inconsistencies = []
    scheduled_automations = (
        db.query(models.Automation)
        .filter(
            models.Automation.enabled.is_(True), models.Automation.schedule.isnot(None)
        )
        .all()
    )
    expected_ids = {auto.id for auto in scheduled_automations}
    loaded_ids = {
        auto_id
        for auto_id in (
            extract_automation_id_from_job(job.id) for job in scheduler.get_jobs()
        )
        if auto_id is not None
    }

    missing_jobs = sorted(expected_ids - loaded_ids)
    orphan_jobs = sorted(loaded_ids - expected_ids)

    if missing_jobs:
        inconsistencies.append(
            "Automacoes habilitadas com agenda sem job carregado: "
            + ", ".join(map(str, missing_jobs[:10]))
        )
    if orphan_jobs:
        inconsistencies.append(
            "Jobs carregados sem automacao habilitada correspondente: "
            + ", ".join(map(str, orphan_jobs[:10]))
        )
    return inconsistencies


def collect_running_over_runtime(db: Session) -> list[dict[str, Any]]:
    """Lista execuções RUNNING que passaram do limite operacional cadastrado."""
    now = get_now_local()
    running = (
        db.query(models.Execution)
        .join(models.Automation, models.Automation.id == models.Execution.automation_id)
        .filter(models.Execution.status == EXECUTION_STATUS_RUNNING)
        .all()
    )
    stale: list[dict[str, Any]] = []
    for item in running:
        started_at = coerce_datetime(item.started_at)
        if not started_at:
            continue
        max_runtime_minutes = (
            item.automation.max_runtime_minutes
            or DIAGNOSTIC_DEFAULT_MAX_RUNTIME_MINUTES
        )
        age_seconds = round((now - started_at).total_seconds(), 2)
        limit_seconds = int(max_runtime_minutes) * 60
        if age_seconds <= limit_seconds + DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS:
            continue
        stale.append(
            {
                "exec_id": item.id,
                "automation_id": item.automation_id,
                "automation_name": item.automation.name if item.automation else None,
                "age_seconds": age_seconds,
                "max_runtime_minutes": int(max_runtime_minutes),
                "claimed_at": schemas.format_dt_br(item.claimed_at),
                "worker_instance_id": item.worker_instance_id,
                "worker_pid": item.worker_pid,
            }
        )
    return sorted(stale, key=lambda entry: entry["age_seconds"], reverse=True)


def collect_orphaned_running(
    db: Session,
    worker_status: Any,
) -> list[dict[str, Any]]:
    """Lista execuções RUNNING sem ownership válido do worker atual."""
    running = (
        db.query(models.Execution)
        .join(models.Automation, models.Automation.id == models.Execution.automation_id)
        .filter(models.Execution.status == EXECUTION_STATUS_RUNNING)
        .all()
    )
    orphaned: list[dict[str, Any]] = []
    for item in running:
        reason = None
        if not worker_status.is_alive:
            reason = "worker_offline"
        elif item.worker_instance_id and worker_status.instance_id:
            if item.worker_instance_id != worker_status.instance_id:
                reason = "worker_instance_mismatch"
        if not reason:
            continue
        orphaned.append(
            {
                "exec_id": item.id,
                "automation_id": item.automation_id,
                "automation_name": item.automation.name if item.automation else None,
                "priority": item.priority,
                "queue_group": item.queue_group,
                "claimed_at": schemas.format_dt_br(item.claimed_at),
                "worker_instance_id": item.worker_instance_id,
                "worker_pid": item.worker_pid,
                "age_seconds": seconds_since(coerce_datetime(item.started_at)),
                "reason": reason,
                "orphaned": True,
            }
        )
    return sorted(orphaned, key=lambda entry: entry["age_seconds"], reverse=True)


def collect_retry_pressure(db: Session) -> list[dict[str, Any]]:
    """Retorna grupos de fila com maior contagem de execuções ativas em retry."""
    rows = (
        db.query(
            models.Execution.queue_group,
            models.Execution.priority,
            func.count(models.Execution.id).label("active_count"),
        )
        .filter(
            models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES),
            models.Execution.retry_count > 0,
        )
        .group_by(models.Execution.queue_group, models.Execution.priority)
        .order_by(desc(func.count(models.Execution.id)))
        .limit(10)
        .all()
    )
    return [
        {
            "queue_group": str(row.queue_group or "default"),
            "priority": str(row.priority or "NORMAL"),
            "active_count": int(row.active_count or 0),
        }
        for row in rows
    ]


def collect_timeouts_24h_by_group(
    db: Session,
    reference_now: datetime,
) -> list[dict[str, Any]]:
    """Conta timeouts nas últimas 24h agrupados por queue_group."""
    rows = (
        db.query(
            models.Execution.queue_group,
            func.count(models.Execution.id).label("timeouts_24h"),
        )
        .filter(
            models.Execution.status == "TIMEOUT",
            models.Execution.started_at >= reference_now - timedelta(hours=24),
        )
        .group_by(models.Execution.queue_group)
        .order_by(desc(func.count(models.Execution.id)))
        .limit(10)
        .all()
    )
    return [
        {
            "queue_group": str(row.queue_group or "default"),
            "timeouts_24h": int(row.timeouts_24h or 0),
        }
        for row in rows
    ]


def collect_oldest_queue_items(
    db: Session,
) -> tuple[models.Execution | None, models.Execution | None, float, float]:
    """Retorna as execuções mais antigas em PENDING e RUNNING com suas idades."""
    oldest_pending = (
        db.query(models.Execution)
        .filter(models.Execution.status == EXECUTION_STATUS_PENDING)
        .order_by(models.Execution.started_at.asc())
        .first()
    )
    oldest_running = (
        db.query(models.Execution)
        .filter(models.Execution.status == EXECUTION_STATUS_RUNNING)
        .order_by(models.Execution.started_at.asc())
        .first()
    )
    pending_age_seconds = seconds_since(
        coerce_datetime(oldest_pending.started_at) if oldest_pending else None
    )
    running_age_seconds = seconds_since(
        coerce_datetime(oldest_running.started_at) if oldest_running else None
    )
    return oldest_pending, oldest_running, pending_age_seconds, running_age_seconds
