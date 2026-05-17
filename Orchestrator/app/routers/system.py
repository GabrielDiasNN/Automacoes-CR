# pylint: disable=all
# mypy: ignore-errors
"""

Router: System - Health check, metricas, backup, status do worker, audit log e endpoints enterprise v5.2.0

"""

import asyncio
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, func, text, case
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..constants import ORCHESTRATOR_VERSION
from ..database import (DB_PATH, get_db, get_db_size_mb, get_wal_size_mb,
                        purge_old_executions, run_wal_checkpoint,
                        validate_database_schema)
from ..middleware import get_api_key
from ..timezone import get_now_local
from ..utils import get_client_ip, log_audit

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/system", tags=["System"])

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

STARTUP_TIME = get_now_local()

def _extract_automation_id_from_job(job_id: str):
    if not job_id.startswith("job_"):
        return None
    parts = job_id.split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except (TypeError, ValueError):
        return None

def _backup_env_file(env_path: str) -> str:
    """Cria backup do .env antes de alteracao administrativa."""
    if not os.path.exists(env_path):
        return ""

    backup_dir = os.path.join(PROJECT_ROOT, "Backups", "env")
    os.makedirs(backup_dir, exist_ok=True)
    ts = get_now_local().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = os.path.join(backup_dir, f".env.{ts}.bak")
    shutil.copy2(env_path, backup_path)
    return os.path.relpath(backup_path, PROJECT_ROOT)

# ---------------------------------------------------------------------------

# HEALTH CHECK COMPLETO

# ---------------------------------------------------------------------------

@router.get("/health", response_model=schemas.SystemHealth)
def health_check(db: Session = Depends(get_db)):
    """Health check completo: DB, Scheduler, Worker, Disco."""

    from ..main import scheduler

    # Status do banco
    db_status = "online"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"erro: {str(e)}"

    # Status do scheduler
    sched_status = "executando" if scheduler.running else "parado"

    # Status do worker
    worker_status = _get_worker_status(db)

    # Tarefas pendentes
    pending = (
        db.query(models.Execution).filter(models.Execution.status == "PENDING").count()
    )

    # Tamanho do banco
    disk_mb = get_db_size_mb()

    # Determinar saude geral
    overall = "healthy"
    if db_status != "online" or not scheduler.running:
        overall = "unhealthy"
    elif not worker_status.is_alive:
        overall = "degraded"

    wal_mb = get_wal_size_mb()

    import psutil

    cpu = psutil.cpu_percent()

    ram = psutil.virtual_memory().percent

    return schemas.SystemHealth(
        status=overall,
        timestamp=get_now_local(),
        database=db_status,
        scheduler=sched_status,
        worker=worker_status,
        pending_tasks=pending,
        disk_usage_mb=disk_mb,
        wal_size_mb=wal_mb,
        cpu_usage=cpu,
        ram_usage_percent=ram,
    )

# ---------------------------------------------------------------------------

# WORKER STATUS

# ---------------------------------------------------------------------------

def _get_worker_status(db: Session) -> schemas.WorkerStatus:
    """Le o heartbeat do worker do banco."""

    hb = db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()

    if not hb or not hb.last_ping:

        return schemas.WorkerStatus(is_alive=False)

    # Worker e considerado "vivo" se o heartbeat foi nos ultimos 60 segundos

    now = get_now_local()

    last_ping = hb.last_ping

    is_alive = (now - last_ping).total_seconds() < 60

    return schemas.WorkerStatus(
        is_alive=is_alive,
        pid=hb.pid,
        last_ping=hb.last_ping,
        uptime_seconds=hb.uptime_seconds,
        tasks_completed=hb.tasks_completed,
        tasks_failed=hb.tasks_failed,
        active_tasks=hb.active_tasks,
        version=hb.version or "unknown",
    )

@router.get("/worker/status", response_model=schemas.WorkerStatus)
def get_worker_status(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna status detalhado do Worker."""

    return _get_worker_status(db)

# ---------------------------------------------------------------------------

# METRICAS ENRIQUECIDAS (N+1 Query Eliminada)

# ---------------------------------------------------------------------------

@router.get("/metrics", response_model=schemas.MetricsResponse)
def get_metrics(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Metricas completas do sistema (Otimizado sem N+1)."""

    total_execs = db.query(models.Execution).count()

    success_count = (
        db.query(models.Execution).filter(models.Execution.status == "SUCCESS").count()
    )

    error_count = (
        db.query(models.Execution).filter(models.Execution.status == "ERROR").count()
    )

    pending_count = (
        db.query(models.Execution).filter(models.Execution.status == "PENDING").count()
    )

    # Duracao media global

    avg_dur = (
        db.query(func.avg(models.Execution.duration_seconds))
        .filter(
            models.Execution.status == "SUCCESS",
            models.Execution.duration_seconds.isnot(None),
        )
        .scalar()
        or 0
    )

    success_rate = (
        round((success_count / total_execs * 100), 2) if total_execs > 0 else 0
    )

    # Agregacao de metricas por automacao em uma unica query
    stats_query = db.query(
        models.Execution.automation_id,
        func.count(case((models.Execution.status == 'SUCCESS', 1))).label("total_success"),
        func.count(case((models.Execution.status == 'ERROR', 1))).label("total_errors"),
        func.avg(case((models.Execution.status == 'SUCCESS', models.Execution.duration_seconds))).label("avg_duration")
    ).group_by(models.Execution.automation_id).all()

    stats_map = {row.automation_id: row for row in stats_query}

    # Subquery para ultima execucao
    subq = db.query(
        models.Execution.automation_id,
        func.max(models.Execution.started_at).label("max_started_at")
    ).group_by(models.Execution.automation_id).subquery()

    last_execs = db.query(
        models.Execution.automation_id,
        models.Execution.status,
        models.Execution.started_at
    ).join(
        subq,
        (models.Execution.automation_id == subq.c.automation_id) &
        (models.Execution.started_at == subq.c.max_started_at)
    ).all()

    last_execs_map = {row.automation_id: row for row in last_execs}

    automation_stats = []
    automations = db.query(models.Automation).all()

    for auto in automations:
        stat = stats_map.get(auto.id)
        last_ex = last_execs_map.get(auto.id)

        automation_stats.append(
            schemas.AutomationMetric(
                name=auto.name,
                total_success=stat.total_success if stat else 0,
                total_errors=stat.total_errors if stat else 0,
                avg_duration_sec=round(stat.avg_duration, 2) if stat and stat.avg_duration else 0,
                last_status=last_ex.status if last_ex else None,
                last_run=last_ex.started_at if last_ex else None,
                test_mode=auto.test_mode,
            )
        )

    return schemas.MetricsResponse(
        summary=schemas.MetricsSummary(
            total_executions=total_execs,
            success_count=success_count,
            error_count=error_count,
            success_rate=success_rate,
            pending_count=pending_count,
            avg_duration_sec=round(avg_dur, 2),
        ),
        automations=automation_stats,
    )

# ---------------------------------------------------------------------------

# BACKUP MANUAL

# ---------------------------------------------------------------------------

@router.post("/backup")
def manual_backup(
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Realiza backup atomico do banco de dados SQLite."""

    backup_dir = os.path.join(PROJECT_ROOT, "Backups")

    os.makedirs(backup_dir, exist_ok=True)

    ts = get_now_local().strftime("%Y%m%d_%H%M%S")

    backup_path = os.path.join(backup_dir, f"automacoes_backup_{ts}.db")

    try:

        db.execute(text(f"VACUUM INTO '{backup_path}'"))

        size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)

        logger.info(f"Backup manual concluido: {backup_path} ({size_mb}MB)")

        # Rotacao: manter apenas os 7 mais recentes

        backups = sorted(
            [
                os.path.join(backup_dir, f)
                for f in os.listdir(backup_dir)
                if f.endswith(".db")
            ]
        )

        if len(backups) > 7:

            for old_b in backups[:-7]:

                os.remove(old_b)

                logger.info(f"Backup antigo removido: {old_b}")

        log_audit(
            db,
            "BACKUP",
            "SYSTEM",
            "GLOBAL",
            get_client_ip(request),
            json.dumps({"path": backup_path, "size_mb": size_mb}),
        )

        db.commit()

        return {
            "message": "Backup realizado com sucesso.",
            "path": backup_path,
            "size_mb": size_mb,
        }

    except Exception as e:

        logger.error(f"Falha no backup manual: {e}")

        raise HTTPException(status_code=500, detail=f"Falha no backup: {str(e)}")

# ---------------------------------------------------------------------------

# AUDIT LOG

# ---------------------------------------------------------------------------

@router.get("/audit", response_model=list[schemas.AuditEntry])
def list_audit_log(
    limit: int = 50,
    action: str = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna as entradas mais recentes do log de auditoria."""

    query = db.query(models.AuditLog)

    if action:

        query = query.filter(models.AuditLog.action == action.upper())

    entries = query.order_by(desc(models.AuditLog.timestamp)).limit(limit).all()

    return entries

# ---------------------------------------------------------------------------

# UPTIME

# ---------------------------------------------------------------------------

@router.get("/uptime")
def get_uptime(api_key: str = Depends(get_api_key)):
    """Retorna o tempo de atividade do Orchestrator."""

    uptime = get_now_local() - STARTUP_TIME

    return {
        "started_at": STARTUP_TIME.isoformat(),
        "uptime_seconds": round(uptime.total_seconds(), 2),
        "uptime_human": str(uptime).split(".")[0],
    }

# ---------------------------------------------------------------------------

# AGENDAMENTO - Lista de tarefas programadas

# ---------------------------------------------------------------------------

@router.get("/scheduler/jobs", response_model=List[schemas.ScheduledJob])
def list_scheduled_jobs(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna a lista de tarefas agendadas no APScheduler."""

    from ..main import scheduler

    jobs = []

    for job in scheduler.get_jobs():

        # Tentar extrair automation_id do ID do job (ex: job_1)

        auto_id = None

        auto_name = "Enterprise Job"

        if job.id.startswith("job_"):

            try:

                auto_id = int(job.id.split("_")[1])

                auto = (
                    db.query(models.Automation)
                    .filter(models.Automation.id == auto_id)
                    .first()
                )

                if auto:

                    auto_name = auto.name

            except (IndexError, ValueError):

                pass

        elif job.id.startswith("enterprise_"):

            auto_name = (
                f"System: {job.id.replace('enterprise_', '').replace('_', ' ').title()}"
            )

        jobs.append(
            schemas.ScheduledJob(
                id=job.id,
                automation_id=auto_id,
                automation_name=auto_name,
                next_run_time=job.next_run_time,
                trigger=str(job.trigger),
            )
        )

    # Ordenar por proxima execucao

    return sorted(
        jobs, key=lambda x: x.next_run_time if x.next_run_time else datetime.max
    )

@router.get("/overview")
def get_system_overview(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Agrega métricas, saúde, jobs e eventos recentes para o dashboard operacional."""
    from ..main import scheduler

    health_payload = health_check(db).model_dump()
    jobs = list_scheduled_jobs(db, api_key)
    next_run_lookup = {}
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
    status_breakdown = {status: count for status, count in status_rows}

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
    recent_payload = []
    for ex in recent_execs:
        summary = schemas.ExecutionSummary.model_validate(ex)
        if ex.automation:
            summary.automation_name = ex.automation.name
        recent_payload.append(summary)

    automations = db.query(models.Automation).order_by(models.Automation.name.asc()).all()
    autos_payload = []
    for auto in automations:
        last_exec = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto.id)
            .order_by(desc(models.Execution.started_at))
            .first()
        )
        autos_payload.append(
            {
                "id": auto.id,
                "name": auto.name,
                "enabled": auto.enabled,
                "test_mode": auto.test_mode,
                "last_status": last_exec.status if last_exec else None,
                "next_run": schemas.format_dt_br(next_run_lookup.get(auto.id)),
            }
        )

    next_window = min(
        (job.next_run_time for job in jobs if job.next_run_time),
        default=None,
    )

    return {
        "generated_at": get_now_local().isoformat(),
        "version": ORCHESTRATOR_VERSION,
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
    }

# ---------------------------------------------------------------------------

# VERSION - Endpoint enterprise de versao e build

# ---------------------------------------------------------------------------

@router.get("/version", response_model=schemas.SystemVersion)
def get_version():
    """Retorna informacoes detalhadas de versao e build do Orchestrator."""

    uptime = get_now_local() - STARTUP_TIME

    max_workers = int(os.environ.get("WORKER_MAX_CONCURRENCY", "4")) # Aumentado para 4 (Pragmatic Performance)

    allowed_origins = [
        o.strip()
        for o in os.environ.get(
            "ALLOWED_ORIGINS",
            "http://localhost,http://127.0.0.1,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if o.strip()
    ]

    return schemas.SystemVersion(
        version=ORCHESTRATOR_VERSION,
        python_version=sys.version.split()[0],
        started_at=STARTUP_TIME.isoformat(),
        uptime_seconds=round(uptime.total_seconds(), 2),
        max_workers=max_workers,
        allowed_origins=allowed_origins,
    )

@router.get("/diagnostics")
def get_diagnostics(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna diagnostico operacional consolidado do Orchestrator."""
    from ..main import scheduler

    statuses = (
        db.query(models.Execution.status, func.count(models.Execution.id))
        .group_by(models.Execution.status)
        .all()
    )
    queue = {status: count for status, count in statuses}
    active_count = sum(queue.get(status, 0) for status in ("PENDING", "RUNNING"))

    return {
        "version": ORCHESTRATOR_VERSION,
        "timestamp": get_now_local().isoformat(),
        "database": {
            "path": DB_PATH,
            "size_mb": get_db_size_mb(),
            "wal_size_mb": get_wal_size_mb(),
            "schema": validate_database_schema(),
        },
        "scheduler": {
            "running": scheduler.running,
            "jobs_loaded": len(scheduler.get_jobs()),
        },
        "worker": _get_worker_status(db).model_dump(),
        "queue": {
            "active_count": active_count,
            "by_status": queue,
        },
    }

# ---------------------------------------------------------------------------

# CHECKPOINT - WAL manual

# ---------------------------------------------------------------------------

@router.post("/checkpoint")
def manual_checkpoint(
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Executa WAL checkpoint manual no banco SQLite."""

    result = run_wal_checkpoint()

    logger.info(f"Checkpoint manual executado: {result}")

    log_audit(
        db,
        "CHECKPOINT",
        "SYSTEM",
        "GLOBAL",
        get_client_ip(request),
        json.dumps(result),
    )

    db.commit()

    return {"message": "WAL Checkpoint executado com sucesso.", "result": result}

# ---------------------------------------------------------------------------

# PURGE - Limpeza de execucoes antigas

# ---------------------------------------------------------------------------

@router.post("/purge")
def manual_purge(
    request: Request,
    retention_days: int = 90,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Remove execucoes finalizadas mais antigas que retention_days (default: 90)."""

    if retention_days < 7:

        raise HTTPException(status_code=400, detail="retention_days deve ser >= 7.")

    removed = purge_old_executions(retention_days)

    logger.info(
        f"Purge manual: {removed} execucoes removidas (>{retention_days} dias)."
    )

    log_audit(
        db,
        "PURGE",
        "SYSTEM",
        "GLOBAL",
        get_client_ip(request),
        json.dumps({"retention_days": retention_days, "removed": removed}),
    )

    db.commit()

    return {
        "message": f"{removed} execução(ões) removida(s).",
        "retention_days": retention_days,
        "removed_count": removed,
    }

# ---------------------------------------------------------------------------
# ENV MANAGEMENT - Gestao global
# ---------------------------------------------------------------------------

@router.get("/wait-for-task")
async def wait_for_task(api_key: str = Depends(get_api_key)):
    """Endpoint de long-polling para wake-up do Worker (v6.2.0)."""
    from ..main import task_queued_event
    try:
        # Espera ate 30 segundos por um evento
        await asyncio.wait_for(task_queued_event.wait(), timeout=30)
        task_queued_event.clear()
        return {"status": "wakeup"}
    except asyncio.TimeoutError:
        return {"status": "timeout"}

@router.get("/env", response_model=schemas.EnvContent)
def get_env_content(api_key: str = Depends(get_api_key)):
    """Lê o conteúdo do arquivo .env global."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return schemas.EnvContent(content="")

    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()
    return schemas.EnvContent(content=content)

@router.put("/env")
def update_env_content(
    payload: schemas.EnvContent,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Atualiza o arquivo .env global de forma segura."""
    env_path = os.path.join(PROJECT_ROOT, ".env")

    try:
        backup_relpath = _backup_env_file(env_path)
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(payload.content)

        logger.info("Arquivo .env global atualizado via API.")

        log_audit(
            db,
            "UPDATE_ENV",
            "SYSTEM",
            "GLOBAL",
            "API_ADMIN",
            json.dumps(
                {
                    "message": "O arquivo .env foi modificado via Dashboard.",
                    "backup": backup_relpath,
                }
            )
        )
        db.commit()

        return {
            "message": "Arquivo .env salvo com sucesso. Reinicie o Orchestrator para aplicar certas mudanças.",
            "backup": backup_relpath,
        }
    except Exception as e:
        logger.error(f"Erro ao salvar .env: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar o arquivo: {str(e)}")
