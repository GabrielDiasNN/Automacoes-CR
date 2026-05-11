"""
Router: System - Health check, metricas, backup, status do worker, audit log e endpoints enterprise v5.0.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db, get_db_size_mb, get_wal_size_mb, run_wal_checkpoint, purge_old_executions, DB_PATH
from ..middleware import get_api_key

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/system", tags=["System"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STARTUP_TIME = datetime.now()


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
        db_status = f"error: {str(e)}"

    # Status do scheduler
    sched_status = "running" if scheduler.running else "stopped"

    # Status do worker
    worker_status = _get_worker_status(db)

    # Tarefas pendentes
    pending = db.query(models.Execution).filter(models.Execution.status == "PENDING").count()

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
        timestamp=datetime.now(),
        database=db_status,
        scheduler=sched_status,
        worker=worker_status,
        pending_tasks=pending,
        disk_usage_mb=disk_mb,
        wal_size_mb=wal_mb,
        cpu_usage=cpu,
        ram_usage_percent=ram
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
    now = datetime.now()
    last_ping = hb.last_ping
    # Lidar com timezone awareness
    if last_ping.tzinfo is not None:
        from datetime import timezone
        now = datetime.now(timezone.utc)

    is_alive = (now - last_ping).total_seconds() < 60

    return schemas.WorkerStatus(
        is_alive=is_alive,
        pid=hb.pid,
        last_ping=hb.last_ping,
        uptime_seconds=hb.uptime_seconds,
        tasks_completed=hb.tasks_completed,
        tasks_failed=hb.tasks_failed,
        active_tasks=hb.active_tasks,
        version=hb.version or "4.0.0",
    )


@router.get("/worker/status", response_model=schemas.WorkerStatus)
def get_worker_status(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retorna status detalhado do Worker."""
    return _get_worker_status(db)


# ---------------------------------------------------------------------------
# METRICAS ENRIQUECIDAS
# ---------------------------------------------------------------------------

@router.get("/metrics", response_model=schemas.MetricsResponse)
def get_metrics(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Metricas completas do sistema."""
    total_execs = db.query(models.Execution).count()
    success_count = db.query(models.Execution).filter(models.Execution.status == "SUCCESS").count()
    error_count = db.query(models.Execution).filter(models.Execution.status == "ERROR").count()
    pending_count = db.query(models.Execution).filter(models.Execution.status == "PENDING").count()

    # Duracao media global
    avg_dur = db.query(func.avg(models.Execution.duration_seconds)).filter(
        models.Execution.status == "SUCCESS",
        models.Execution.duration_seconds.isnot(None),
    ).scalar() or 0

    success_rate = round((success_count / total_execs * 100), 2) if total_execs > 0 else 0

    # Metricas por automacao
    automation_stats = []
    automations = db.query(models.Automation).all()
    for auto in automations:
        auto_success = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto.id, models.Execution.status == "SUCCESS")
            .count()
        )
        auto_errors = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto.id, models.Execution.status == "ERROR")
            .count()
        )
        auto_avg = (
            db.query(func.avg(models.Execution.duration_seconds))
            .filter(
                models.Execution.automation_id == auto.id,
                models.Execution.status == "SUCCESS",
                models.Execution.duration_seconds.isnot(None),
            )
            .scalar() or 0
        )
        last_exec = (
            db.query(models.Execution)
            .filter(models.Execution.automation_id == auto.id)
            .order_by(desc(models.Execution.started_at))
            .first()
        )

        automation_stats.append(schemas.AutomationMetric(
            name=auto.name,
            total_success=auto_success,
            total_errors=auto_errors,
            avg_duration_sec=round(auto_avg, 2),
            last_status=last_exec.status if last_exec else None,
            last_run=last_exec.started_at if last_exec else None,
            test_mode=auto.test_mode,
        ))

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
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Realiza backup atomico do banco de dados SQLite."""
    backup_dir = os.path.join(PROJECT_ROOT, "Backups")
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"automacoes_backup_{ts}.db")

    try:
        db.execute(text(f"VACUUM INTO '{backup_path}'"))
        size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)
        logger.info(f"Backup manual concluido: {backup_path} ({size_mb}MB)")

        # Rotacao: manter apenas os 7 mais recentes
        backups = sorted([
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir) if f.endswith(".db")
        ])
        if len(backups) > 7:
            for old_b in backups[:-7]:
                os.remove(old_b)
                logger.info(f"Backup antigo removido: {old_b}")

        # Registrar auditoria
        entry = models.AuditLog(
            action="BACKUP", entity_type="SYSTEM", actor="MANUAL",
            details=json.dumps({"path": backup_path, "size_mb": size_mb})
        )
        db.add(entry)
        db.commit()

        return {"message": "Backup realizado com sucesso.", "path": backup_path, "size_mb": size_mb}
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
    uptime = datetime.now() - STARTUP_TIME
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
                auto = db.query(models.Automation).filter(models.Automation.id == auto_id).first()
                if auto:
                    auto_name = auto.name
            except (IndexError, ValueError):
                pass
        elif job.id.startswith("enterprise_"):
            auto_name = f"System: {job.id.replace('enterprise_', '').replace('_', ' ').title()}"

        jobs.append(schemas.ScheduledJob(
            id=job.id,
            automation_id=auto_id,
            automation_name=auto_name,
            next_run_time=job.next_run_time,
            trigger=str(job.trigger)
        ))
    
    # Ordenar por proxima execucao
    return sorted(jobs, key=lambda x: x.next_run_time if x.next_run_time else datetime.max)


# ---------------------------------------------------------------------------
# VERSION - Endpoint enterprise de versao e build
# ---------------------------------------------------------------------------

@router.get("/version", response_model=schemas.SystemVersion)
def get_version():
    """Retorna informacoes detalhadas de versao e build do Orchestrator."""
    uptime = datetime.now() - STARTUP_TIME
    max_workers = int(os.environ.get("WORKER_MAX_CONCURRENCY", "2"))
    allowed_origins = [
        o.strip()
        for o in os.environ.get(
            "ALLOWED_ORIGINS",
            "http://localhost,http://127.0.0.1,http://localhost:8000,http://127.0.0.1:8000"
        ).split(",")
        if o.strip()
    ]
    return schemas.SystemVersion(
        version="5.0.0",
        python_version=sys.version.split()[0],
        started_at=STARTUP_TIME.isoformat(),
        uptime_seconds=round(uptime.total_seconds(), 2),
        max_workers=max_workers,
        allowed_origins=allowed_origins,
    )


# ---------------------------------------------------------------------------
# CHECKPOINT - WAL manual
# ---------------------------------------------------------------------------

@router.post("/checkpoint")
def manual_checkpoint(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Executa WAL checkpoint manual no banco SQLite."""
    result = run_wal_checkpoint()
    logger.info(f"Checkpoint manual executado: {result}")

    from .. import models as _models
    entry = _models.AuditLog(
        action="CHECKPOINT", entity_type="SYSTEM", actor="MANUAL",
        details=json.dumps(result)
    )
    db.add(entry)
    db.commit()

    return {"message": "WAL Checkpoint executado com sucesso.", "result": result}


# ---------------------------------------------------------------------------
# PURGE - Limpeza de execucoes antigas
# ---------------------------------------------------------------------------

@router.post("/purge")
def manual_purge(
    retention_days: int = 90,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Remove execucoes finalizadas mais antigas que retention_days (default: 90)."""
    if retention_days < 7:
        raise HTTPException(status_code=400, detail="retention_days deve ser >= 7.")

    removed = purge_old_executions(retention_days)
    logger.info(f"Purge manual: {removed} execucoes removidas (>{retention_days} dias).")

    entry = models.AuditLog(
        action="PURGE", entity_type="SYSTEM", actor="MANUAL",
        details=json.dumps({"retention_days": retention_days, "removed": removed})
    )
    db.add(entry)
    db.commit()

    return {
        "message": f"{removed} execucao(oes) removida(s).",
        "retention_days": retention_days,
        "removed_count": removed,
    }
