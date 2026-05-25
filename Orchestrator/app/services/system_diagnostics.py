"""Serviços de diagnóstico operacional do Orchestrator (C1, C4)."""

# pylint: disable=relative-beyond-top-level,too-many-locals,not-callable,too-many-branches,too-many-statements,line-too-long

from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import (
    ACTION_CODE_BACKUP,
    ACTION_CODE_CHECKPOINT,
    ACTION_CODE_SCHEDULER_RELOAD,
    ACTION_CODE_WORKER_RECOVER,
    ACTION_CODE_WORKER_WAKEUP,
    EXECUTION_ACTIVE_STATUSES,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    ORCHESTRATOR_CONTRACT_VERSION,
    ORCHESTRATOR_SCHEMA_VERSION,
    ORCHESTRATOR_VERSION,
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS,
    DIAGNOSTIC_WAL_CRITICAL_MB,
    DIAGNOSTIC_WAL_ELEVATED_MB,
    DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS,
    DIAGNOSTIC_FAILURE_HOTSPOT_THRESHOLD,
    DIAGNOSTIC_DEFAULT_MAX_RUNTIME_MINUTES,
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
from .scheduler_runtime import extract_automation_id_from_job
from .system_history import build_trend_summary
from . import metrics  # pylint: disable=no-name-in-module

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
        max_runtime_minutes = item.automation.max_runtime_minutes or DIAGNOSTIC_DEFAULT_MAX_RUNTIME_MINUTES
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

# --- ANALISADORES FOCADOS (C1) ---

def check_schema_integrity(schema_status: dict[str, Any], schema_version: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not schema_status["valid"]:
        add_finding(
            findings,
            "ERROR",
            "database",
            "Schema SQLite diverge do contrato esperado.",
            {
                "action_hint": "Executar diagnóstico de schema e revisar migração/backup antes de operar.",
                "action_code": ACTION_CODE_BACKUP,
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
                "action_code": ACTION_CODE_WORKER_RECOVER,
                "action_label": "Reiniciar Orchestrator",
                "impact": "Pode indicar migração leve pendente ou instância desatualizada servindo a operação.",
                "priority": 2,
            },
        )
    return findings

def check_wal_health(wal_size_mb: float) -> tuple[list[dict[str, Any]], str]:
    findings: list[dict[str, Any]] = []
    wal_risk = "normal"
    if wal_size_mb >= DIAGNOSTIC_WAL_CRITICAL_MB:
        wal_risk = "critical"
        add_finding(
            findings,
            SEVERITY_ERROR,
            "database",
            f"WAL elevado ({wal_size_mb} MB).",
            {
                "action_hint": "Executar checkpoint e verificar contenção de escrita no SQLite.",
                "action_code": ACTION_CODE_CHECKPOINT,
                "action_label": "Executar checkpoint",
                "impact": "Risco de degradação de I/O, crescimento de disco e lentidão no dashboard.",
                "priority": 1,
            },
        )
    elif wal_size_mb >= DIAGNOSTIC_WAL_ELEVATED_MB:
        wal_risk = "elevated"
        add_finding(
            findings,
            SEVERITY_WARN,
            "database",
            f"WAL acima do normal ({wal_size_mb} MB).",
            {
                "action_hint": "Agendar checkpoint operacional se o valor continuar crescendo.",
                "action_code": ACTION_CODE_CHECKPOINT,
                "action_label": "Executar checkpoint",
                "impact": "Indica acúmulo de escrita; se crescer, pode virar incidente de banco.",
                "priority": 2,
            },
        )
    return findings, wal_risk

def check_scheduler_health(scheduler: Any, inconsistencies: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not scheduler.running:
        add_finding(
            findings,
            SEVERITY_ERROR,
            "scheduler",
            "Scheduler está parado.",
            {
                "action_hint": "Reiniciar Orchestrator e confirmar carregamento dos jobs.",
                "action_code": ACTION_CODE_WORKER_RECOVER,
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
                "action_code": ACTION_CODE_SCHEDULER_RELOAD,
                "action_label": "Sincronizar agenda",
                "impact": "Agenda vazia pode ser legítima, mas também pode indicar sincronismo quebrado.",
                "priority": 3,
            },
        )

    for item in inconsistencies:
        add_finding(
            findings,
            SEVERITY_WARN,
            "scheduler",
            item,
            {
                "action_hint": "Sincronizar scheduler com o banco e revisar automações habilitadas.",
                "action_code": ACTION_CODE_SCHEDULER_RELOAD,
                "action_label": "Sincronizar agenda",
                "impact": "Banco e memória divergem; disparos podem ser omitidos ou ficar órfãos.",
                "priority": 2,
            },
        )
    return findings

def check_worker_health(worker_status: Any, active_count: int, last_ping_age_seconds: float | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not worker_status.is_alive:
        add_finding(
            findings,
            (
                SEVERITY_ERROR
                if active_count
                or (last_ping_age_seconds or 0) >= DIAGNOSTIC_WORKER_OFFLINE_WARN_SECONDS
                else SEVERITY_WARN
            ),
            "worker",
            "Worker sem heartbeat recente.",
            {
                "action_hint": "Recuperar o Orchestrator para reativar o worker e retomar a fila.",
                "action_code": "worker_recover" if active_count else "worker_wakeup",
                "action_label": (
                    "Recuperar worker" if active_count else "Acordar worker"
                ),
                "impact": "Execuções pendentes ou em andamento podem ficar sem processamento.",
                "priority": 1 if active_count else 2,
            },
        )
    return findings

def check_queue_health(pending_age_seconds: float, running_age_seconds: float) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if pending_age_seconds >= DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS:
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

    if running_age_seconds >= DIAGNOSTIC_RUNNING_STALLED_WARN_SECONDS:
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
    return findings

def check_running_over_runtime(running_over_runtime: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if running_over_runtime:
        first_stale = running_over_runtime[0]
        add_finding(
            findings,
            SEVERITY_WARN,
            "queue",
            (
                f"{first_stale['automation_name'] or first_stale['exec_id']} excedeu "
                f"o max_runtime cadastrado ({first_stale['max_runtime_minutes']} min)."
            ),
            {
                "action_hint": "Abrir logs da execução, confirmar se há progresso real e avaliar parada controlada.",
                "action_code": "show_running",
                "action_label": "Ver execuções em andamento",
                "impact": "Execução acima do limite pode indicar subprocesso travado, timeout não aplicado ou automação sem heartbeat operacional.",
                "priority": 1,
            },
        )
    return findings

def check_failure_hotspots(failure_hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for hotspot in failure_hotspots:
        if hotspot["failures_24h"] < DIAGNOSTIC_FAILURE_HOTSPOT_THRESHOLD:
            continue
        channels = str(hotspot.get("notification_channels") or "").lower()
        channel_hint = (
            " e canais de notificação"
            if ("whatsapp" in channels or "email" in channels)
            else ""
        )
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
    return findings


def check_orphaned_running(orphaned_running: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not orphaned_running:
        return findings
    top = orphaned_running[0]
    add_finding(
        findings,
        SEVERITY_ERROR,
        "queue",
        (
            "Execução RUNNING sem ownership válido detectada: "
            f"{top['exec_id']} ({top.get('automation_name') or 'automação desconhecida'})."
        ),
        {
            "action_hint": "Executar recovery do worker e revisar logs antes de novo requeue.",
            "action_code": ACTION_CODE_WORKER_RECOVER,
            "action_label": "Recuperar worker",
            "impact": "Execução pode ter ficado órfã após falha de worker ou troca de instância.",
            "priority": 1,
        },
    )
    return findings

# --- ORQUESTRADOR CENTRAL (C1) ---

def build_diagnostics_payload(
    db: Session,
    scheduler: Any,
    worker_status_fn: Callable[[Session], Any],
    wal_size_fn: Callable[[], float] | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    """Monta diagnostico acionavel delegando para sub-funções focadas (C1)."""
    findings: list[dict[str, Any]] = []

    # 1. Obter informações fundamentais
    schema_status = validate_database_schema()
    schema_version = get_schema_version()
    wal_provider = wal_size_fn or get_wal_size_mb
    wal_size_mb = wal_provider()
    db_size_mb = get_db_size_mb()
    worker_status = worker_status_fn(db)
    heartbeat = (
        db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()
    )

    # 2. Utilizar as consultas centralizadas de services/metrics.py (C4)
    queue = metrics.get_status_breakdown(db)
    active_count = sum(queue.get(status, 0) for status in EXECUTION_ACTIVE_STATUSES)
    active_by_priority = metrics.get_active_by_priority(db)
    active_by_group = metrics.get_active_by_group(db)
    failure_hotspots = metrics.get_failure_hotspots_24h(db)

    running_over_runtime = collect_running_over_runtime(db)
    orphaned_running = collect_orphaned_running(db, worker_status)

    # Retry pressure (métrica complementar de diagnóstico)
    retry_pressure_rows = (
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
    retry_pressure = [
        {
            "queue_group": str(row.queue_group or "default"),
            "priority": str(row.priority or "NORMAL"),
            "active_count": int(row.active_count or 0),
        }
        for row in retry_pressure_rows
    ]

    # Timeouts nas últimas 24h
    timeout_rows = (
        db.query(
            models.Execution.queue_group,
            func.count(models.Execution.id).label("timeouts_24h"),
        )
        .filter(
            models.Execution.status == "TIMEOUT",
            models.Execution.started_at >= get_now_local() - timedelta(hours=24),
        )
        .group_by(models.Execution.queue_group)
        .order_by(desc(func.count(models.Execution.id)))
        .limit(10)
        .all()
    )
    timeouts_24h_by_group = [
        {
            "queue_group": str(row.queue_group or "default"),
            "timeouts_24h": int(row.timeouts_24h or 0),
        }
        for row in timeout_rows
    ]

    # Execuções mais antigas
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

    # 3. Executar as análises através das funções puras focadas (C1)
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

    # 4. Consolidar o status geral e ações recomendadas
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

    # 5. Criar checks formatados para telemetria
    checks = [
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
    trend_summary = (
        build_trend_summary(db, 24)
        if include_history
        else schemas.DiagnosticsTrendSummary().model_dump()
    )

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
        "queue": {
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
                "worker_instance_id": oldest_pending.worker_instance_id if oldest_pending else None,
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
                "worker_instance_id": oldest_running.worker_instance_id if oldest_running else None,
                "worker_pid": oldest_running.worker_pid if oldest_running else None,
                "orphaned": bool(
                    oldest_running
                    and any(item["exec_id"] == oldest_running.id for item in orphaned_running)
                ),
                "age_seconds": running_age_seconds,
            },
        },
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
        "schema_version": schema_version,
    }
