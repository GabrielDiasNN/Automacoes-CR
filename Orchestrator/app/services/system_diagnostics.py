"""Serviços de diagnóstico operacional do Orchestrator."""
# pylint: disable=relative-beyond-top-level,too-many-locals,not-callable,too-many-branches,too-many-statements,line-too-long

from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import desc, func
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
    findings: list[dict[str, Any]],
    severity: str,
    component: str,
    message: str,
    details: dict[str, Any],
) -> None:
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


def build_operator_actions(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa ações sugeridas para o operador sem duplicar botões na UI."""
    severity_rank = {"ERROR": 0, "WARN": 1, "INFO": 2}
    actions: dict[str, dict[str, Any]] = {}

    for item in findings:
        action_code = item.get("action_code")
        if not action_code:
            continue
        current = actions.get(action_code)
        candidate = {
            "action_code": action_code,
            "action_label": item.get("action_label") or item.get("action_hint") or action_code,
            "severity": item.get("severity", "INFO"),
            "component": item.get("component", "system"),
            "reason": item.get("message", ""),
            "priority": int(item.get("priority", 3)),
        }
        if current is None:
            actions[action_code] = candidate
            continue
        current_rank = severity_rank.get(str(current.get("severity", "INFO")), 2)
        candidate_rank = severity_rank.get(str(candidate.get("severity", "INFO")), 2)
        if (candidate_rank, candidate["priority"]) < (current_rank, int(current.get("priority", 3))):
            actions[action_code] = candidate

    return sorted(
        actions.values(),
        key=lambda item: (
            severity_rank.get(str(item.get("severity", "INFO")), 2),
            int(item.get("priority", 3)),
            str(item.get("action_label", "")),
        ),
    )


def collect_failure_hotspots(db: Session) -> list[dict[str, Any]]:
    """Identifica automações com falhas recorrentes nas últimas 24h."""
    window_start = get_now_local() - timedelta(hours=24)
    rows = (
        db.query(
            models.Automation.id.label("automation_id"),
            models.Automation.name.label("automation_name"),
            models.Automation.notification_channels.label("notification_channels"),
            func.count(models.Execution.id).label("failures"),
            func.max(models.Execution.started_at).label("last_failure_at"),
        )
        .join(models.Execution, models.Execution.automation_id == models.Automation.id)
        .filter(
            models.Execution.status.in_(["ERROR", "TIMEOUT", "TERMINATED"]),
            models.Execution.started_at >= window_start,
        )
        .group_by(
            models.Automation.id,
            models.Automation.name,
            models.Automation.notification_channels,
        )
        .order_by(desc(func.count(models.Execution.id)))
        .limit(5)
        .all()
    )
    return [
        {
            "automation_id": row.automation_id,
            "automation_name": row.automation_name,
            "failures_24h": int(row.failures),
            "last_failure_at": schemas.format_dt_br(row.last_failure_at),
            "notification_channels": row.notification_channels,
        }
        for row in rows
    ]


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
    findings: list[dict[str, Any]] = []
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
    priority_rows = (
        db.query(models.Execution.priority, func.count(models.Execution.id))
        .filter(models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES))
        .group_by(models.Execution.priority)
        .all()
    )
    active_by_priority = {
        str(priority or "NORMAL"): int(count) for priority, count in priority_rows
    }
    group_rows = (
        db.query(models.Execution.queue_group, func.count(models.Execution.id))
        .filter(models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES))
        .group_by(models.Execution.queue_group)
        .all()
    )
    active_by_group = {
        str(group or "default"): int(count) for group, count in group_rows
    }
    failure_hotspots = collect_failure_hotspots(db)

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
            {
                "action_hint": "Executar diagnóstico de schema e revisar migração/backup antes de operar.",
                "action_code": "backup",
                "action_label": "Gerar backup antes de corrigir schema",
                "impact": "Risco de erro em leitura/escrita e de decisões operacionais baseadas em estrutura divergente.",
                "priority": 1,
            },
        )

    if schema_version != ORCHESTRATOR_SCHEMA_VERSION:
        add_finding(
            findings,
            SEVERITY_WARN,
            "database",
            f"Schema version divergente: banco={schema_version}, app={ORCHESTRATOR_SCHEMA_VERSION}.",
            {
                "action_hint": "Reiniciar o Orchestrator para reaplicar migracoes leves e validar o banco.",
                "action_code": "worker_recover",
                "action_label": "Reiniciar Orchestrator",
                "impact": "Pode indicar migração leve pendente ou instância desatualizada servindo a operação.",
                "priority": 2,
            },
        )

    wal_risk = "normal"
    if wal_size_mb >= 256:
        wal_risk = "critical"
        add_finding(
            findings,
            SEVERITY_ERROR,
            "database",
            f"WAL elevado ({wal_size_mb} MB).",
            {
                "action_hint": "Executar checkpoint e verificar contenção de escrita no SQLite.",
                "action_code": "checkpoint",
                "action_label": "Executar checkpoint",
                "impact": "Risco de degradação de I/O, crescimento de disco e lentidão no dashboard.",
                "priority": 1,
            },
        )
    elif wal_size_mb >= 64:
        wal_risk = "elevated"
        add_finding(
            findings,
            SEVERITY_WARN,
            "database",
            f"WAL acima do normal ({wal_size_mb} MB).",
            {
                "action_hint": "Agendar checkpoint operacional se o valor continuar crescendo.",
                "action_code": "checkpoint",
                "action_label": "Executar checkpoint",
                "impact": "Indica acúmulo de escrita; se crescer, pode virar incidente de banco.",
                "priority": 2,
            },
        )

    if not scheduler.running:
        add_finding(
            findings,
            SEVERITY_ERROR,
            "scheduler",
            "Scheduler está parado.",
            {
                "action_hint": "Reiniciar Orchestrator e confirmar carregamento dos jobs.",
                "action_code": "worker_recover",
                "action_label": "Recuperar Orchestrator",
                "impact": "Automações agendadas podem deixar de disparar.",
                "priority": 1,
            },
        )
    elif len(scheduler.get_jobs()) == 0:
        add_finding(
            findings,
            SEVERITY_WARN,
            "scheduler",
            "Scheduler está ativo, mas sem jobs carregados.",
            {
                "action_hint": "Verificar automações habilitadas com agenda configurada.",
                "action_code": "scheduler_reload",
                "action_label": "Sincronizar agenda",
                "impact": "Agenda vazia pode ser legítima, mas também pode indicar sincronismo quebrado.",
                "priority": 3,
            },
        )

    inconsistencies = collect_scheduler_inconsistencies(db, scheduler)
    for item in inconsistencies:
        add_finding(
            findings,
            SEVERITY_WARN,
            "scheduler",
            item,
            {
                "action_hint": "Sincronizar scheduler com o banco e revisar automações habilitadas.",
                "action_code": "scheduler_reload",
                "action_label": "Sincronizar agenda",
                "impact": "Banco e memória divergem; disparos podem ser omitidos ou ficar órfãos.",
                "priority": 2,
            },
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
            {
                "action_hint": "Recuperar o Orchestrator para reativar o worker e retomar a fila.",
                "action_code": "worker_recover" if active_count else "worker_wakeup",
                "action_label": "Recuperar worker" if active_count else "Acordar worker",
                "impact": "Execuções pendentes ou em andamento podem ficar sem processamento.",
                "priority": 1 if active_count else 2,
            },
        )

    if pending_age_seconds >= 900:
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            f"Execução pendente há {round(pending_age_seconds / 60, 1)} minutos.",
            {
                "action_hint": "Verificar worker, concorrência e bloqueios antes de reenfileirar.",
                "action_code": "worker_wakeup",
                "action_label": "Acordar worker",
                "impact": "Fila parada aumenta atraso operacional e pode esconder automação bloqueada.",
                "priority": 2,
            },
        )

    if running_age_seconds >= 3600:
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            f"Execução em RUNNING há {round(running_age_seconds / 60, 1)} minutos.",
            {
                "action_hint": "Consultar logs da execução e avaliar parada controlada se houver hang.",
                "action_code": "show_running",
                "action_label": "Ver execuções em andamento",
                "impact": "Pode representar processamento longo legítimo ou automação travada segurando recursos.",
                "priority": 2,
            },
        )

    for hotspot in failure_hotspots:
        if hotspot["failures_24h"] < 3:
            continue
        channels = str(hotspot.get("notification_channels") or "").lower()
        channel_hint = " e canais de notificação" if ("whatsapp" in channels or "email" in channels) else ""
        add_finding(
            findings,
            SEVERITY_WARN,
            "automation",
            f"{hotspot['automation_name']} falhou {hotspot['failures_24h']} vez(es) nas últimas 24h.",
            {
                "action_hint": f"Abrir histórico da automação e revisar logs{channel_hint} antes de nova tentativa.",
                "action_code": "show_errors",
                "action_label": "Ver falhas recentes",
                "impact": "Falha recorrente tende a virar ruído operacional e pode exigir correção de causa raiz.",
                "priority": 2,
            },
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
            "active_by_priority": active_by_priority,
            "active_by_group": active_by_group,
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
        "failure_hotspots": failure_hotspots,
        "operator_actions": build_operator_actions(findings),
        "schema_version": schema_version,
    }
