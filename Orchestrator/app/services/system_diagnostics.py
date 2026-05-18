"""Serviços de diagnóstico operacional do Orchestrator."""
# pylint: disable=relative-beyond-top-level,too-many-locals,not-callable,too-many-branches,too-many-statements,line-too-long

from datetime import datetime
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import (
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    ORCHESTRATOR_SCHEMA_VERSION,
    ORCHESTRATOR_VERSION,
    SEVERITY_ERROR,
    SEVERITY_WARN,
)
from ..database import (
    DB_PATH,
    get_db_size_mb,
    get_schema_version,
    get_wal_size_mb,
    validate_database_schema,
)
from ..timezone import get_now_local


def extract_automation_id_from_job(job_id: str) -> int | None:
    if not job_id.startswith("job_"):
        return None
    parts = job_id.split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except (TypeError, ValueError):
        return None


def add_finding(
    findings: list[dict[str, str]],
    severity: str,
    component: str,
    message: str,
    action_hint: str,
) -> None:
    findings.append(
        {
            "severity": severity,
            "component": component,
            "message": message,
            "action_hint": action_hint,
        }
    )


def seconds_since(value: datetime | None) -> float:
    if not value:
        return 0.0
    return round((get_now_local() - value).total_seconds(), 2)

def coerce_datetime(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def collect_scheduler_inconsistencies(db: Session, scheduler: Any) -> list[str]:
    inconsistencies = []
    scheduled_automations = (
        db.query(models.Automation)
        .filter(models.Automation.enabled.is_(True), models.Automation.schedule.isnot(None))
        .all()
    )
    expected_ids = {auto.id for auto in scheduled_automations}
    loaded_ids = {
        auto_id
        for auto_id in (extract_automation_id_from_job(job.id) for job in scheduler.get_jobs())
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


def build_diagnostics_payload(
    db: Session,
    scheduler: Any,
    worker_status_fn: Callable[[Session], Any],
    wal_size_fn: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Monta diagnostico acionavel sem executar correcoes automaticas."""
    findings: list[dict[str, str]] = []
    schema_status = validate_database_schema()
    schema_version = get_schema_version()
    wal_provider = wal_size_fn or get_wal_size_mb
    wal_size_mb = wal_provider()
    db_size_mb = get_db_size_mb()
    worker_status = worker_status_fn(db)
    heartbeat = (
        db.query(models.WorkerHeartbeat)
        .filter(models.WorkerHeartbeat.id == 1)
        .first()
    )

    statuses = (
        db.query(models.Execution.status, func.count(models.Execution.id))
        .group_by(models.Execution.status)
        .all()
    )
    queue: dict[str, int] = {
        str(status): int(count) for status, count in statuses
    }
    active_count = sum(queue.get(status, 0) for status in EXECUTION_ACTIVE_STATUSES)

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

    if not schema_status["valid"]:
        add_finding(
            findings,
            "ERROR",
            "database",
            "Schema SQLite diverge do contrato esperado.",
            "Executar diagnóstico de schema e revisar migração/backup antes de operar.",
        )

    if schema_version != ORCHESTRATOR_SCHEMA_VERSION:
        add_finding(
            findings,
            SEVERITY_WARN,
            "database",
            f"Schema version divergente: banco={schema_version}, app={ORCHESTRATOR_SCHEMA_VERSION}.",
            "Reiniciar o Orchestrator para reaplicar migracoes leves e validar o banco.",
        )

    wal_risk = "normal"
    if wal_size_mb >= 256:
        wal_risk = "critical"
        add_finding(
            findings,
            SEVERITY_ERROR,
            "database",
            f"WAL elevado ({wal_size_mb} MB).",
            "Executar checkpoint e verificar contenção de escrita no SQLite.",
        )
    elif wal_size_mb >= 64:
        wal_risk = "elevated"
        add_finding(
            findings,
            SEVERITY_WARN,
            "database",
            f"WAL acima do normal ({wal_size_mb} MB).",
            "Agendar checkpoint operacional se o valor continuar crescendo.",
        )

    if not scheduler.running:
        add_finding(
            findings,
            SEVERITY_ERROR,
            "scheduler",
            "Scheduler está parado.",
            "Reiniciar Orchestrator e confirmar carregamento dos jobs.",
        )
    elif len(scheduler.get_jobs()) == 0:
        add_finding(
            findings,
            SEVERITY_WARN,
            "scheduler",
            "Scheduler está ativo, mas sem jobs carregados.",
            "Verificar automações habilitadas com agenda configurada.",
        )

    inconsistencies = collect_scheduler_inconsistencies(db, scheduler)
    for item in inconsistencies:
        add_finding(
            findings,
            SEVERITY_WARN,
            "scheduler",
            item,
            "Sincronizar scheduler com o banco e revisar automações habilitadas.",
        )

    last_ping_age_seconds = None
    if heartbeat and heartbeat.last_ping:
        last_ping_age_seconds = seconds_since(coerce_datetime(heartbeat.last_ping))
    if not worker_status.is_alive:
        add_finding(
            findings,
            SEVERITY_ERROR if active_count else SEVERITY_WARN,
            "worker",
            "Worker sem heartbeat recente.",
            "Recuperar o Orchestrator para reativar o worker e retomar a fila.",
        )

    if pending_age_seconds >= 900:
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            f"Execução pendente há {round(pending_age_seconds / 60, 1)} minutos.",
            "Verificar worker, concorrência e bloqueios antes de reenfileirar.",
        )

    if running_age_seconds >= 3600:
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            f"Execução em RUNNING há {round(running_age_seconds / 60, 1)} minutos.",
            "Consultar logs da execução e avaliar parada controlada se houver hang.",
        )

    severity_rank = {"INFO": 0, "WARN": 1, "ERROR": 2}
    max_severity = max((severity_rank.get(item["severity"], 0) for item in findings), default=0)
    overall_status = "healthy"
    if max_severity == 2:
        overall_status = "unhealthy"
    elif max_severity == 1:
        overall_status = "degraded"

    jobs = scheduler.get_jobs()
    next_runs = sorted((job.next_run_time for job in jobs if job.next_run_time))[:5]

    return {
        "version": ORCHESTRATOR_VERSION,
        "timestamp": get_now_local().isoformat(),
        "overall_status": overall_status,
        "findings": findings,
        "database": {
            "path": DB_PATH,
            "size_mb": db_size_mb,
            "wal_size_mb": wal_size_mb,
            "wal_risk": wal_risk,
            "schema": schema_status,
            "schema_version": schema_version,
        },
        "scheduler": {
            "running": scheduler.running,
            "jobs_loaded": len(jobs),
            "next_runs": [schemas.format_dt_br(item) for item in next_runs],
            "inconsistencies": inconsistencies,
        },
        "worker": worker_status.model_dump(),
        "queue": {
            "active_count": active_count,
            "by_status": queue,
            "oldest_pending": {
                "exec_id": oldest_pending.id if oldest_pending else None,
                "age_seconds": pending_age_seconds,
            },
            "oldest_running": {
                "exec_id": oldest_running.id if oldest_running else None,
                "age_seconds": running_age_seconds,
            },
        },
        "heartbeat": {
            "last_ping_age_seconds": last_ping_age_seconds,
        },
        "schema_version": schema_version,
    }
