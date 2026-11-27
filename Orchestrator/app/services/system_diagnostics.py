"""Serviços de diagnóstico operacional do Orchestrator (C1, C4)."""

from collections.abc import Callable
from datetime import datetime
from time import perf_counter
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import (
    ACTION_CODE_BACKUP,
    ACTION_CODE_CHECKPOINT,
    ACTION_CODE_SCHEDULER_RELOAD,
    ACTION_CODE_WORKER_RECOVER,
    ACTION_CODE_WORKER_WAKEUP,
    BASELINE_STATUS_ATTENTION,
    BASELINE_STATUS_HEALTHY,
    BASELINE_STATUS_INCIDENT,
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS,
    DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_WAL_CRITICAL_MB,
    DIAGNOSTIC_WAL_ELEVATED_MB,
    DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
    DIAGNOSTIC_WORKER_SATURATION_WARN_SECONDS,
    EXECUTION_ACTIVE_STATUSES,
    ORCHESTRATOR_CONTRACT_VERSION,
    ORCHESTRATOR_VERSION,
    SEVERITY_ERROR,
    SEVERITY_WARN,
    WORKER_MAX_CONCURRENCY_PADRAO,
)
from ..database import (
    DB_PATH,
    get_db_size_mb,
    get_schema_version,
    get_wal_size_mb,
    validate_database_schema,
)
from ..runtime import get_worker_max_concurrency
from ..timezone import get_now_local
from . import metrics_queries as metrics
from .diagnostic_checks import (
    check_failure_hotspots,
    check_oracle_queue_worker_health,
    check_orphaned_running,
    check_queue_health,
    check_running_over_runtime,
    check_scheduler_health,
    check_schema_integrity,
    check_sla_breaches,
    check_wal_health,
    check_worker_health,
    check_worker_saturation,
)
from .diagnostic_collectors import (
    add_finding,
    coerce_datetime,
    collect_oldest_queue_items,
    collect_orphaned_running,
    collect_retry_pressure,
    collect_running_over_runtime,
    collect_scheduler_inconsistencies,
    collect_sla_breaches,
    collect_timeouts_24h_by_group,
    seconds_since,
)
from .operational_baseline import (
    SinaisFila,
    SinaisWorker,
    build_operational_baseline_summary,
)
from .oracle_queue_health import (
    collect_oracle_queue_health,
    is_oracle_queue_degraded,
)
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


def _build_oracle_queue_worker_check(
    oracle_queue_worker: dict[str, Any],
) -> dict[str, Any]:
    reachable = bool(oracle_queue_worker.get("reachable"))
    alive = bool(oracle_queue_worker.get("alive"))
    oracle_ok = oracle_queue_worker.get("oracle_ok")
    status = (
        "error"
        if (not reachable or not alive)
        else ("warn" if oracle_ok is False else "ok")
    )
    if not reachable:
        detail = "Pasta da fila Oracle inacessível."
    elif not alive:
        detail = "Worker Oracle do TSplus está offline."
    elif oracle_ok is False:
        detail = "Worker Oracle ativo, mas sem conexão com o banco PRD."
    else:
        detail = "Worker Oracle do TSplus ativo e saudável."
    age_seconds = oracle_queue_worker.get("age_seconds")
    age_txt = f"{age_seconds}s" if age_seconds is not None else "n/a"
    return {
        "code": "oracle_queue_worker",
        "label": "Worker Oracle (Fila TSplus)",
        "status": status,
        "detail": detail,
        "value": f"v{oracle_queue_worker.get('version') or '?'};age={age_txt}",
    }


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
    oracle_queue_worker: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Monta lista de checks de runtime para o payload de diagnóstico."""
    checks: list[dict[str, Any]] = [
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
            # Limiar alinhado ao finding de `diagnostic_checks` e ao nível
            # `attention` do `operational_baseline` (1×). O `* 2` anterior fazia
            # o card responder "ok" a uma RUNNING de 1h30 que o resto do sistema
            # já sinalizava, e ainda contradizia o campo
            # `running_stalled_warn_seconds` (1h) publicado na mesma resposta.
            "status": (
                "warn"
                if pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS
                or running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS
                else "ok"
            ),
            "detail": (
                "Há execuções envelhecidas na fila ou em execução."
                if pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS
                or running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS
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
    if oracle_queue_worker and oracle_queue_worker.get("enabled"):
        checks.append(_build_oracle_queue_worker_check(oracle_queue_worker))
    return checks


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
                and any(
                    item["exec_id"] == oldest_running.id for item in orphaned_running
                )
            ),
            "age_seconds": running_age_seconds,
        },
    }


class _Fundamentos(TypedDict):
    """Dados base coletados antes das consultas de fila (etapa 1)."""

    schema_status: dict[str, Any]
    schema_version: str
    wal_size_mb: float
    db_size_mb: float
    worker_status: Any
    heartbeat: models.WorkerHeartbeat | None


class _Fila(TypedDict):
    """Métricas de fila e execuções coletadas no banco (etapa 2)."""

    queue: dict[str, int]
    active_count: int
    active_by_priority: dict[str, int]
    active_by_group: dict[str, int]
    failure_hotspots: list[dict[str, Any]]
    retry_pressure: list[dict[str, Any]]
    timeouts_24h_by_group: list[dict[str, Any]]
    oldest_pending: models.Execution | None
    oldest_running: models.Execution | None
    pending_age_seconds: float
    running_age_seconds: float
    running_over_runtime: list[dict[str, Any]]
    orphaned_running: list[dict[str, Any]]
    sla_breaches: list[dict[str, Any]]


class _Analise(TypedDict):
    """Findings e sinais derivados das etapas 1 e 2 (etapa 3)."""

    findings: list[dict[str, Any]]
    wal_risk: str
    inconsistencies: list[str]
    last_ping_age_seconds: float | None
    oracle_queue_worker: dict[str, Any]


def _coletar_fundamentos(
    db: Session,
    worker_status_fn: Callable[[Session], Any],
    wal_size_fn: Callable[[], float] | None,
) -> _Fundamentos:
    schema_status = validate_database_schema()
    schema_version = get_schema_version()
    wal_provider = wal_size_fn or get_wal_size_mb
    wal_size_mb = wal_provider()
    db_size_mb = get_db_size_mb()
    worker_status = worker_status_fn(db)
    heartbeat = (
        db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()
    )
    return {
        "schema_status": schema_status,
        "schema_version": schema_version,
        "wal_size_mb": wal_size_mb,
        "db_size_mb": db_size_mb,
        "worker_status": worker_status,
        "heartbeat": heartbeat,
    }


def _coletar_fila(db: Session, worker_status: Any, reference_now: datetime) -> _Fila:
    queue = metrics.get_status_breakdown(db)
    active_by_priority = metrics.get_active_by_priority(db)
    active_by_group = metrics.get_active_by_group(db)
    failure_hotspots = metrics.get_failure_hotspots_24h(db)
    retry_pressure = collect_retry_pressure(db)
    timeouts_24h_by_group = collect_timeouts_24h_by_group(db, reference_now)
    oldest = collect_oldest_queue_items(db)
    running_over_runtime = collect_running_over_runtime(db)
    orphaned_running = collect_orphaned_running(db, worker_status)
    sla_breaches = collect_sla_breaches(db, reference_now)
    return {
        "queue": queue,
        "active_count": sum(
            queue.get(status, 0) for status in EXECUTION_ACTIVE_STATUSES
        ),
        "active_by_priority": active_by_priority,
        "active_by_group": active_by_group,
        "failure_hotspots": failure_hotspots,
        "retry_pressure": retry_pressure,
        "timeouts_24h_by_group": timeouts_24h_by_group,
        "oldest_pending": oldest[0],
        "oldest_running": oldest[1],
        "pending_age_seconds": oldest[2],
        "running_age_seconds": oldest[3],
        "running_over_runtime": running_over_runtime,
        "orphaned_running": orphaned_running,
        "sla_breaches": sla_breaches,
    }


def _analisar(db: Session, fund: _Fundamentos, fila: _Fila, scheduler: Any) -> _Analise:
    worker_status = fund["worker_status"]
    findings: list[dict[str, Any]] = []
    findings.extend(
        check_schema_integrity(fund["schema_status"], fund["schema_version"])
    )

    wal_findings, wal_risk = check_wal_health(fund["wal_size_mb"])
    findings.extend(wal_findings)

    inconsistencies = collect_scheduler_inconsistencies(db, scheduler)
    findings.extend(check_scheduler_health(scheduler, inconsistencies))

    heartbeat = fund["heartbeat"]
    last_ping_age_seconds = None
    if heartbeat and heartbeat.last_ping:
        last_ping_age_seconds = seconds_since(coerce_datetime(heartbeat.last_ping))

    findings.extend(
        check_worker_health(worker_status, fila["active_count"], last_ping_age_seconds)
    )
    findings.extend(
        check_queue_health(fila["pending_age_seconds"], fila["running_age_seconds"])
    )
    findings.extend(check_running_over_runtime(fila["running_over_runtime"]))
    findings.extend(check_orphaned_running(fila["orphaned_running"]))
    findings.extend(check_failure_hotspots(fila["failure_hotspots"]))
    findings.extend(check_sla_breaches(fila["sla_breaches"]))
    oracle_queue_worker = collect_oracle_queue_health()
    findings.extend(check_oracle_queue_worker_health(oracle_queue_worker))
    try:
        max_workers = get_worker_max_concurrency()
    except ValueError as exc:
        # Configuração inválida vira finding: o diagnóstico é justamente a tela que
        # precisa apontá-la, então não pode responder 500.
        add_finding(
            findings,
            SEVERITY_ERROR,
            "worker",
            str(exc),
            {
                "action_hint": "Corrigir WORKER_MAX_CONCURRENCY no .env (inteiro maior que zero) e reiniciar o worker.",
                "priority": 1,
            },
        )
        max_workers = WORKER_MAX_CONCURRENCY_PADRAO
    findings.extend(
        check_worker_saturation(
            getattr(worker_status, "pool_saturated_seconds", None), max_workers
        )
    )
    return {
        "findings": findings,
        "wal_risk": wal_risk,
        "inconsistencies": inconsistencies,
        "last_ping_age_seconds": last_ping_age_seconds,
        "oracle_queue_worker": oracle_queue_worker,
    }


def _status_geral(findings: list[dict[str, Any]]) -> str:
    severity_rank = {"INFO": 0, "WARN": 1, "ERROR": 2}
    # Falha isolada de dependência externa (`oracle_queue`) degrada a operação
    # sem marcar o Orchestrator como "unhealthy" (alinhado com /health/full).
    max_severity = max(
        (
            1
            if item.get("component") == "oracle_queue"
            and item.get("severity") == SEVERITY_ERROR
            else severity_rank.get(item["severity"], 0)
            for item in findings
        ),
        default=0,
    )
    if max_severity == 2:
        return "unhealthy"
    if max_severity == 1:
        return "degraded"
    return "healthy"


def _breaches_slo(
    fund: _Fundamentos, fila: _Fila, analise: _Analise
) -> dict[str, bool]:
    worker_status = fund["worker_status"]
    wal_size_mb = fund["wal_size_mb"]
    last_ping_age_seconds = analise["last_ping_age_seconds"]
    running_age_seconds = fila["running_age_seconds"]
    return {
        "pending_stalled": fila["pending_age_seconds"]
        >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
        "running_stalled": running_age_seconds
        >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
        "running_over_runtime": bool(fila["running_over_runtime"]),
        "worker_offline": not worker_status.is_alive
        and (last_ping_age_seconds or 0) >= DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
        "wal_elevated": wal_size_mb >= DIAGNOSTIC_WAL_ELEVATED_MB,
        "wal_critical": wal_size_mb >= DIAGNOSTIC_WAL_CRITICAL_MB,
        "orphaned_running": bool(fila["orphaned_running"]),
        "sla_breached": bool(fila["sla_breaches"]),
        "worker_saturated": (
            getattr(worker_status, "pool_saturated_seconds", None) or 0.0
        )
        >= DIAGNOSTIC_WORKER_SATURATION_WARN_SECONDS,
        "oracle_queue_degraded": is_oracle_queue_degraded(
            analise["oracle_queue_worker"]
        ),
    }


def _montar_resumo(
    scheduler: Any, fund: _Fundamentos, fila: _Fila, analise: _Analise
) -> dict[str, Any]:
    """Status geral, ações, checks e SLO: a parte de consolidação da etapa 4."""
    overall_status = _status_geral(analise["findings"])
    jobs = scheduler.get_jobs()
    next_runs = sorted(job.next_run_time for job in jobs if job.next_run_time)[:5]
    operator_actions = build_operator_actions(analise["findings"])
    checks = build_runtime_checks(
        worker_status=fund["worker_status"],
        scheduler=scheduler,
        jobs=jobs,
        last_ping_age_seconds=analise["last_ping_age_seconds"],
        pending_age_seconds=fila["pending_age_seconds"],
        running_age_seconds=fila["running_age_seconds"],
        running_over_runtime=fila["running_over_runtime"],
        wal_risk=analise["wal_risk"],
        wal_size_mb=fund["wal_size_mb"],
        schema_status=fund["schema_status"],
        schema_version=fund["schema_version"],
        oracle_queue_worker=analise["oracle_queue_worker"],
    )
    has_unactionable_issue = any(
        item.get("severity") in (SEVERITY_ERROR, SEVERITY_WARN)
        for item in analise["findings"]
    )
    recommended_action = (
        operator_actions[0]["action_code"]
        if operator_actions
        else (None if has_unactionable_issue else ACTION_CODE_WORKER_WAKEUP)
    )
    return {
        "overall_status": overall_status,
        "jobs": jobs,
        "next_runs": next_runs,
        "operator_actions": operator_actions,
        "checks": checks,
        "recommended_action": recommended_action,
        "slo_breaches": _breaches_slo(fund, fila, analise),
    }


def _oracle_queue_baseline_metric(
    oracle_q: dict[str, Any],
) -> schemas.OperationalBaselineMetric:
    reachable = bool(oracle_q.get("reachable"))
    alive = bool(oracle_q.get("alive"))
    oracle_ok = oracle_q.get("oracle_ok")
    age = oracle_q.get("age_seconds")
    if not reachable:
        status = BASELINE_STATUS_ATTENTION
        current_value = "SMB inacessível"
        detail = "Pasta da fila Oracle (SMB) está inacessível."
    elif not alive:
        status = BASELINE_STATUS_ATTENTION
        current_value = "offline"
        detail = "Worker Oracle do TSplus está offline; extrações em modo queue não serão atendidas."
    elif oracle_ok is False:
        status = BASELINE_STATUS_ATTENTION
        current_value = "sem Oracle PRD"
        detail = "Worker Oracle no TSplus reportou perda de conexão com o banco Oracle PRD."
    else:
        status = BASELINE_STATUS_HEALTHY
        current_value = f"{age} s" if age is not None else "online"
        detail = "Worker Oracle do TSplus ativo e conectado ao banco PRD."
    return schemas.OperationalBaselineMetric(
        code="oracle_queue_worker",
        label="Worker Oracle (TSplus)",
        status=status,
        current_value=current_value,
        attention_threshold="offline ou sem Oracle PRD",
        incident_threshold=None,
        detail=detail,
        action_code=None,
    )


def _baseline_operacional(
    fund: _Fundamentos, fila: _Fila, analise: _Analise
) -> dict[str, Any]:
    evaluated_at = get_now_local()
    summary = build_operational_baseline_summary(
        evaluated_at=evaluated_at,
        worker=SinaisWorker(
            is_alive=fund["worker_status"].is_alive,
            last_ping_age_seconds=analise["last_ping_age_seconds"],
            active_count=fila["active_count"],
        ),
        fila=SinaisFila(
            pending_age_seconds=fila["pending_age_seconds"],
            running_age_seconds=fila["running_age_seconds"],
            running_over_runtime_count=len(fila["running_over_runtime"]),
            orphaned_running_count=len(fila["orphaned_running"]),
        ),
        wal_size_mb=fund["wal_size_mb"],
    )
    oracle_q = analise.get("oracle_queue_worker")
    if oracle_q and oracle_q.get("enabled"):
        metrics_list = [*summary.metrics, _oracle_queue_baseline_metric(oracle_q)]
        attention_count = sum(
            1 for item in metrics_list if item.status == BASELINE_STATUS_ATTENTION
        )
        incident_count = sum(
            1 for item in metrics_list if item.status == BASELINE_STATUS_INCIDENT
        )
        status = BASELINE_STATUS_HEALTHY
        if incident_count:
            status = BASELINE_STATUS_INCIDENT
        elif attention_count:
            status = BASELINE_STATUS_ATTENTION
        summary = schemas.OperationalBaselineSummary(
            evaluated_at=evaluated_at,
            status=status,
            attention_count=attention_count,
            incident_count=incident_count,
            recommended_action=summary.recommended_action,
            metrics=metrics_list,
        )
    return summary.model_dump()


def build_diagnostics_payload(
    db: Session,
    scheduler: Any,
    worker_status_fn: Callable[[Session], Any],
    wal_size_fn: Callable[[], float] | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    """Monta diagnostico acionavel em etapas focadas (C1).

    Cada etapa (fundamentos, fila, análise, consolidação, histórico) é uma
    função própria; esta apenas encadeia as etapas e mede o tempo de cada uma.
    """
    total_started_at = perf_counter()
    timings_ms: dict[str, float] = {}
    reference_now = get_now_local()

    stage_started_at = perf_counter()
    fund = _coletar_fundamentos(db, worker_status_fn, wal_size_fn)
    timings_ms["fundamentals_ms"] = round((perf_counter() - stage_started_at) * 1000, 2)

    stage_started_at = perf_counter()
    fila = _coletar_fila(db, fund["worker_status"], reference_now)
    timings_ms["queue_metrics_ms"] = round(
        (perf_counter() - stage_started_at) * 1000, 2
    )

    stage_started_at = perf_counter()
    analise = _analisar(db, fund, fila, scheduler)
    timings_ms["analysis_ms"] = round((perf_counter() - stage_started_at) * 1000, 2)

    stage_started_at = perf_counter()
    resumo = _montar_resumo(scheduler, fund, fila, analise)
    timings_ms["assembly_ms"] = round((perf_counter() - stage_started_at) * 1000, 2)

    stage_started_at = perf_counter()
    trend_summary = (
        build_trend_summary(db, 24)
        if include_history
        else schemas.DiagnosticsTrendSummary().model_dump()
    )
    operational_baseline = _baseline_operacional(fund, fila, analise)
    timings_ms["history_baseline_ms"] = round(
        (perf_counter() - stage_started_at) * 1000, 2
    )
    timings_ms["total_ms"] = round((perf_counter() - total_started_at) * 1000, 2)

    return {
        "version": ORCHESTRATOR_VERSION,
        "contract_version": ORCHESTRATOR_CONTRACT_VERSION,
        "timestamp": schemas.format_dt_br(get_now_local()),
        "overall_status": resumo["overall_status"],
        "findings": analise["findings"],
        "database": {
            "path": DB_PATH,
            "size_mb": fund["db_size_mb"],
            "wal_size_mb": fund["wal_size_mb"],
            "wal_risk": analise["wal_risk"],
            "schema": fund["schema_status"],
            "schema_version": fund["schema_version"],
        },
        "scheduler": {
            "running": scheduler.running,
            "jobs_loaded": len(resumo["jobs"]),
            "next_runs": [schemas.format_dt_br(item) for item in resumo["next_runs"]],
            "inconsistencies": analise["inconsistencies"],
        },
        "worker": fund["worker_status"].model_dump(),
        "oracle_queue_worker": analise["oracle_queue_worker"],
        "queue": build_queue_payload(
            queue=fila["queue"],
            active_count=fila["active_count"],
            active_by_priority=fila["active_by_priority"],
            active_by_group=fila["active_by_group"],
            running_over_runtime=fila["running_over_runtime"],
            orphaned_running=fila["orphaned_running"],
            retry_pressure=fila["retry_pressure"],
            timeouts_24h_by_group=fila["timeouts_24h_by_group"],
            oldest_pending=fila["oldest_pending"],
            oldest_running=fila["oldest_running"],
            pending_age_seconds=fila["pending_age_seconds"],
            running_age_seconds=fila["running_age_seconds"],
        ),
        "heartbeat": {
            "last_ping_age_seconds": analise["last_ping_age_seconds"],
        },
        "failure_hotspots": fila["failure_hotspots"],
        "sla_breaches": fila["sla_breaches"],
        "operator_actions": resumo["operator_actions"],
        "checks": resumo["checks"],
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
            "recommended_action": resumo["recommended_action"],
        },
        "slo": {
            "thresholds": {
                "pending_stalled_warn_seconds": DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
                "running_stalled_warn_seconds": DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
                "running_over_runtime_grace_seconds": DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS,
                "worker_offline_warn_seconds": DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
                "wal_elevated_mb": DIAGNOSTIC_WAL_ELEVATED_MB,
                "wal_critical_mb": DIAGNOSTIC_WAL_CRITICAL_MB,
                "worker_saturation_warn_seconds": DIAGNOSTIC_WORKER_SATURATION_WARN_SECONDS,
            },
            "breaches": resumo["slo_breaches"],
        },
        "slo_breaches": resumo["slo_breaches"],
        "trend_summary": trend_summary,
        "operational_baseline": operational_baseline,
        "performance": {
            "timings_ms": timings_ms,
        },
        "schema_version": fund["schema_version"],
    }
