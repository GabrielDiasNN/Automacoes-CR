"""Serviços de diagnóstico operacional do Orchestrator (C1, C4)."""

# pylint: disable=relative-beyond-top-level,too-many-locals,too-many-statements

from time import perf_counter
from typing import Any, Callable

from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import (
    ACTION_CODE_BACKUP,
    ACTION_CODE_CHECKPOINT,
    ACTION_CODE_SCHEDULER_RELOAD,
    ACTION_CODE_WORKER_RECOVER,
    ACTION_CODE_WORKER_WAKEUP,
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS,
    DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_WAL_CRITICAL_MB,
    DIAGNOSTIC_WAL_ELEVATED_MB,
    DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
    EXECUTION_ACTIVE_STATUSES,
    ORCHESTRATOR_CONTRACT_VERSION,
    ORCHESTRATOR_VERSION,
)
from ..database import (
    DB_PATH,
    get_db_size_mb,
    get_schema_version,
    get_wal_size_mb,
    validate_database_schema,
)
from ..timezone import get_now_local
from . import metrics  # pylint: disable=no-name-in-module
from .diagnostic_checks import (
    check_failure_hotspots,
    check_orphaned_running,
    check_queue_health,
    check_running_over_runtime,
    check_scheduler_health,
    check_schema_integrity,
    check_wal_health,
    check_worker_health,
)
from .diagnostic_collectors import (
    collect_oldest_queue_items,
    collect_orphaned_running,
    collect_retry_pressure,
    collect_running_over_runtime,
    collect_scheduler_inconsistencies,
    collect_timeouts_24h_by_group,
    seconds_since,
    coerce_datetime,
)
from .operational_baseline import build_operational_baseline_summary
from .system_history import build_trend_summary


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
            "action_label": item.get("action_label")
            or item.get("action_hint")
            or action_code,
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
        if (candidate_rank, candidate["priority"]) < (
            current_rank,
            int(current.get("priority", 3)),
        ):
            actions[action_code] = candidate

    return sorted(
        actions.values(),
        key=lambda item: (
            severity_rank.get(str(item.get("severity", "INFO")), 2),
            int(item.get("priority", 3)),
            str(item.get("action_label", "")),
        ),
    )


def build_runtime_checks(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    worker_status: Any,
    scheduler: Any,
    jobs: list[Any],
    last_ping_age_seconds: float | None,
    pending_age_seconds: float,
    running_age_seconds: float,
    running_over_runtime: list[dict[str, Any]],
    wal_risk: str,
    wal_size_mb: float,
    schema_status: dict[str, Any],
    schema_version: str,
) -> list[dict[str, Any]]:
    """Monta lista de checks de runtime para o payload de diagnóstico."""
    return [
        {
            "code": "contract_version",
            "label": "Contrato de payload",
            "status": "ok",
            "detail": "Payload agregado do sistema está versionado para evolução controlada.",
            "value": ORCHESTRATOR_CONTRACT_VERSION,
        },
        {
            "code": "worker_heartbeat",
            "label": "Heartbeat do worker",
            "status": "ok" if worker_status.is_alive else "error",
            "detail": (
                "Worker respondendo via heartbeat recente."
                if worker_status.is_alive
                else "Worker sem heartbeat recente."
            ),
            "value": (
                str(last_ping_age_seconds)
                if last_ping_age_seconds is not None
                else None
            ),
        },
        {
            "code": "scheduler_jobs",
            "label": "Jobs carregados",
            "status": "ok" if scheduler.running and len(jobs) > 0 else "warn",
            "detail": (
                "Scheduler carregado com jobs em memória."
                if scheduler.running and len(jobs) > 0
                else "Scheduler sem jobs ativos ou não iniciado."
            ),
            "value": str(len(jobs)),
        },
        {
            "code": "queue_stalled",
            "label": "Fila parada",
            "status": (
                "warn"
                if pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS
                or running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS * 2
                else "ok"
            ),
            "detail": (
                "Há execuções envelhecidas na fila ou em execução."
                if pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS
                or running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS * 2
                else "Sem indício de fila parada."
            ),
            "value": f"pending={pending_age_seconds}s,running={running_age_seconds}s",
        },
        {
            "code": "running_over_runtime",
            "label": "Execuções acima do limite",
            "status": "warn" if running_over_runtime else "ok",
            "detail": (
                "Há execução em RUNNING acima do max_runtime cadastrado."
                if running_over_runtime
                else "Nenhuma execução ativa acima do limite cadastrado."
            ),
            "value": str(len(running_over_runtime)),
        },
        {
            "code": "wal_health",
            "label": "Saúde do WAL",
            "status": (
                "error"
                if wal_risk == "critical"
                else ("warn" if wal_risk == "elevated" else "ok")
            ),
            "detail": (
                "Tamanho do WAL dentro da faixa operacional."
                if wal_risk == "normal"
                else "WAL exige ação operacional."
            ),
            "value": str(wal_size_mb),
        },
        {
            "code": "schema_minimum",
            "label": "Consistência mínima de schema",
            "status": "ok" if schema_status["valid"] else "error",
            "detail": (
                "Schema consistente com o contrato esperado."
                if schema_status["valid"]
                else "Schema divergente do contrato esperado."
            ),
            "value": schema_version,
        },
    ]


def build_queue_payload(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    queue: dict[str, int],
    active_count: int,
    active_by_priority: dict[str, int],
    active_by_group: dict[str, int],
    running_over_runtime: list[dict[str, Any]],
    orphaned_running: list[dict[str, Any]],
    retry_pressure: list[dict[str, Any]],
    timeouts_24h_by_group: list[dict[str, Any]],
    oldest_pending: models.Execution | None,
    oldest_running: models.Execution | None,
    pending_age_seconds: float,
    running_age_seconds: float,
) -> dict[str, Any]:
    """Monta o bloco ``queue`` do payload de diagnóstico."""
    return {
        "active_count": active_count,
        "by_status": queue,
        "active_by_priority": active_by_priority,
        "active_by_group": active_by_group,
        "running_over_runtime": running_over_runtime,
        "orphaned_running": orphaned_running,
        "retry_pressure": retry_pressure,
        "timeouts_24h_by_group": timeouts_24h_by_group,
        "oldest_pending": {
            "exec_id": oldest_pending.id if oldest_pending else None,
            "automation_id": oldest_pending.automation_id if oldest_pending else None,
            "automation_name": (
                oldest_pending.automation.name
                if oldest_pending and getattr(oldest_pending, "automation", None)
                else None
            ),
            "priority": oldest_pending.priority if oldest_pending else None,
            "queue_group": oldest_pending.queue_group if oldest_pending else None,
            "claimed_at": oldest_pending.claimed_at if oldest_pending else None,
            "worker_instance_id": (
                oldest_pending.worker_instance_id if oldest_pending else None
            ),
            "worker_pid": oldest_pending.worker_pid if oldest_pending else None,
            "orphaned": False,
            "age_seconds": pending_age_seconds,
        },
        "oldest_running": {
            "exec_id": oldest_running.id if oldest_running else None,
            "automation_id": oldest_running.automation_id if oldest_running else None,
            "automation_name": (
                oldest_running.automation.name
                if oldest_running and getattr(oldest_running, "automation", None)
                else None
            ),
            "priority": oldest_running.priority if oldest_running else None,
            "queue_group": oldest_running.queue_group if oldest_running else None,
            "claimed_at": oldest_running.claimed_at if oldest_running else None,
            "worker_instance_id": (
                oldest_running.worker_instance_id if oldest_running else None
            ),
            "worker_pid": oldest_running.worker_pid if oldest_running else None,
            "orphaned": bool(
                oldest_running
                and any(item["exec_id"] == oldest_running.id for item in orphaned_running)
            ),
            "age_seconds": running_age_seconds,
        },
    }


def build_diagnostics_payload(
    db: Session,
    scheduler: Any,
    worker_status_fn: Callable[[Session], Any],
    wal_size_fn: Callable[[], float] | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    """Monta diagnostico acionavel delegando para sub-funções focadas (C1)."""
    total_started_at = perf_counter()
    findings: list[dict[str, Any]] = []
    timings_ms: dict[str, float] = {}
    reference_now = get_now_local()

    # 1. Obter informações fundamentais
    stage_started_at = perf_counter()
    schema_status = validate_database_schema()
    schema_version = get_schema_version()
    wal_provider = wal_size_fn or get_wal_size_mb
    wal_size_mb = wal_provider()
    db_size_mb = get_db_size_mb()
    worker_status = worker_status_fn(db)
    heartbeat = (
        db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()
    )
    timings_ms["fundamentals_ms"] = round((perf_counter() - stage_started_at) * 1000, 2)

    # 2. Utilizar as consultas centralizadas de services/metrics.py (C4)
    stage_started_at = perf_counter()
    queue = metrics.get_status_breakdown(db)
    active_count = sum(queue.get(status, 0) for status in EXECUTION_ACTIVE_STATUSES)
    active_by_priority = metrics.get_active_by_priority(db)
    active_by_group = metrics.get_active_by_group(db)
    failure_hotspots = metrics.get_failure_hotspots_24h(db)
    retry_pressure = collect_retry_pressure(db)
    timeouts_24h_by_group = collect_timeouts_24h_by_group(db, reference_now)
    oldest_pending, oldest_running, pending_age_seconds, running_age_seconds = (
        collect_oldest_queue_items(db)
    )
    running_over_runtime = collect_running_over_runtime(db)
    orphaned_running = collect_orphaned_running(db, worker_status)
    timings_ms["queue_metrics_ms"] = round(
        (perf_counter() - stage_started_at) * 1000, 2
    )

    # 3. Executar as análises através das funções puras focadas (C1)
    stage_started_at = perf_counter()
    findings.extend(check_schema_integrity(schema_status, schema_version))

    wal_findings, wal_risk = check_wal_health(wal_size_mb)
    findings.extend(wal_findings)

    inconsistencies = collect_scheduler_inconsistencies(db, scheduler)
    findings.extend(check_scheduler_health(scheduler, inconsistencies))

    last_ping_age_seconds = None
    if heartbeat and heartbeat.last_ping:
        last_ping_age_seconds = seconds_since(coerce_datetime(heartbeat.last_ping))

    findings.extend(check_worker_health(worker_status, active_count, last_ping_age_seconds))
    findings.extend(check_queue_health(pending_age_seconds, running_age_seconds))
    findings.extend(check_running_over_runtime(running_over_runtime))
    findings.extend(check_orphaned_running(orphaned_running))
    findings.extend(check_failure_hotspots(failure_hotspots))
    timings_ms["analysis_ms"] = round((perf_counter() - stage_started_at) * 1000, 2)

    # 4. Consolidar o status geral e ações recomendadas
    stage_started_at = perf_counter()
    severity_rank = {"INFO": 0, "WARN": 1, "ERROR": 2}
    max_severity = max(
        (severity_rank.get(item["severity"], 0) for item in findings), default=0
    )
    overall_status = "healthy"
    if max_severity == 2:
        overall_status = "unhealthy"
    elif max_severity == 1:
        overall_status = "degraded"

    jobs = scheduler.get_jobs()
    next_runs = sorted((job.next_run_time for job in jobs if job.next_run_time))[:5]
    operator_actions = build_operator_actions(findings)
    checks = build_runtime_checks(
        worker_status=worker_status,
        scheduler=scheduler,
        jobs=jobs,
        last_ping_age_seconds=last_ping_age_seconds,
        pending_age_seconds=pending_age_seconds,
        running_age_seconds=running_age_seconds,
        running_over_runtime=running_over_runtime,
        wal_risk=wal_risk,
        wal_size_mb=wal_size_mb,
        schema_status=schema_status,
        schema_version=schema_version,
    )
    recommended_action = (
        operator_actions[0]["action_code"]
        if operator_actions
        else ACTION_CODE_WORKER_WAKEUP
    )
    slo_breaches = {
        "pending_stalled": pending_age_seconds
        >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
        "running_stalled": running_age_seconds
        >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
        "running_over_runtime": bool(running_over_runtime),
        "worker_offline": not worker_status.is_alive
        and (last_ping_age_seconds or 0) >= DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
        "wal_elevated": wal_size_mb >= DIAGNOSTIC_WAL_ELEVATED_MB,
        "wal_critical": wal_size_mb >= DIAGNOSTIC_WAL_CRITICAL_MB,
        "orphaned_running": bool(orphaned_running),
    }
    timings_ms["assembly_ms"] = round((perf_counter() - stage_started_at) * 1000, 2)
    stage_started_at = perf_counter()
    trend_summary = (
        build_trend_summary(db, 24)
        if include_history
        else schemas.DiagnosticsTrendSummary().model_dump()
    )
    operational_baseline = build_operational_baseline_summary(
        evaluated_at=get_now_local(),
        worker_is_alive=worker_status.is_alive,
        worker_last_ping_age_seconds=last_ping_age_seconds,
        active_count=active_count,
        pending_age_seconds=pending_age_seconds,
        running_age_seconds=running_age_seconds,
        running_over_runtime_count=len(running_over_runtime),
        orphaned_running_count=len(orphaned_running),
        wal_size_mb=wal_size_mb,
    ).model_dump()
    timings_ms["history_baseline_ms"] = round(
        (perf_counter() - stage_started_at) * 1000, 2
    )
    timings_ms["total_ms"] = round((perf_counter() - total_started_at) * 1000, 2)

    return {
        "version": ORCHESTRATOR_VERSION,
        "contract_version": ORCHESTRATOR_CONTRACT_VERSION,
        "timestamp": schemas.format_dt_br(get_now_local()),
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
        "queue": build_queue_payload(
            queue=queue,
            active_count=active_count,
            active_by_priority=active_by_priority,
            active_by_group=active_by_group,
            running_over_runtime=running_over_runtime,
            orphaned_running=orphaned_running,
            retry_pressure=retry_pressure,
            timeouts_24h_by_group=timeouts_24h_by_group,
            oldest_pending=oldest_pending,
            oldest_running=oldest_running,
            pending_age_seconds=pending_age_seconds,
            running_age_seconds=running_age_seconds,
        ),
        "heartbeat": {
            "last_ping_age_seconds": last_ping_age_seconds,
        },
        "failure_hotspots": failure_hotspots,
        "operator_actions": operator_actions,
        "checks": checks,
        "recovery": {
            "light_actions": [
                ACTION_CODE_WORKER_WAKEUP,
                ACTION_CODE_SCHEDULER_RELOAD,
                ACTION_CODE_CHECKPOINT,
            ],
            "strong_actions": [
                ACTION_CODE_WORKER_RECOVER,
                ACTION_CODE_BACKUP,
            ],
            "recommended_action": recommended_action,
        },
        "slo": {
            "thresholds": {
                "pending_stalled_warn_seconds": DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
                "running_stalled_warn_seconds": DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
                "running_over_runtime_grace_seconds": DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS,
                "worker_offline_warn_seconds": DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
                "wal_elevated_mb": DIAGNOSTIC_WAL_ELEVATED_MB,
                "wal_critical_mb": DIAGNOSTIC_WAL_CRITICAL_MB,
            },
            "breaches": slo_breaches,
        },
        "slo_breaches": slo_breaches,
        "trend_summary": trend_summary,
        "operational_baseline": operational_baseline,
        "performance": {
            "timings_ms": timings_ms,
        },
        "schema_version": schema_version,
    }
