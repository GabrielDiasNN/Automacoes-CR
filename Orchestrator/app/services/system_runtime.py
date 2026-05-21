# pylint: disable=all
# mypy: ignore-errors
"""Serviços operacionais de runtime do Orchestrator."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import ORCHESTRATOR_VERSION
from ..database import get_db_size_mb, get_schema_version, get_wal_size_mb
from ..runtime import get_allowed_origins, scheduler
from ..timezone import get_now_local


def get_worker_status(db: Session) -> schemas.WorkerStatus:
    hb = db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()
    if not hb or not hb.last_ping:
        return schemas.WorkerStatus(is_alive=False)

    now = get_now_local()
    is_alive = (now - hb.last_ping).total_seconds() < 60
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


def build_health_payload(
    db: Session, worker_status: schemas.WorkerStatus
) -> schemas.SystemHealth:
    db_status = "online"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"erro: {str(exc)}"

    sched_status = "executando" if scheduler.running else "parado"
    pending = (
        db.query(models.Execution).filter(models.Execution.status == "PENDING").count()
    )
    overall = "healthy"
    if db_status != "online" or not scheduler.running:
        overall = "unhealthy"
    elif not worker_status.is_alive:
        overall = "degraded"

    import psutil

    return schemas.SystemHealth(
        status=overall,
        timestamp=get_now_local(),
        database=db_status,
        scheduler=sched_status,
        worker=worker_status,
        pending_tasks=pending,
        disk_usage_mb=get_db_size_mb(),
        wal_size_mb=get_wal_size_mb(),
        cpu_usage=psutil.cpu_percent(),
        ram_usage_percent=psutil.virtual_memory().percent,
    )


def launch_orchestrator_recovery(project_root: str) -> str:
    infrastructure_dir = os.path.join(project_root, "Infrastructure")
    candidates = ("Recover-Orchestrator.ps1", "Start-Orchestrator.ps1")

    for script_name in candidates:
        script_path = os.path.join(infrastructure_dir, script_name)
        if not os.path.exists(script_path):
            continue
        log_dir = os.path.join(project_root, "Orchestrator", "Logs")
        os.makedirs(log_dir, exist_ok=True)
        base_name = os.path.splitext(script_name)[0].lower()
        stdout_log = os.path.join(log_dir, f"{base_name}_stdout.log")
        stderr_log = os.path.join(log_dir, f"{base_name}_stderr.log")
        with open(stdout_log, "a", encoding="utf-8") as stdout, open(
            stderr_log, "a", encoding="utf-8"
        ) as stderr:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_path,
                ],
                cwd=project_root,
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        return script_name

    raise FileNotFoundError("Script canônico de recuperação não encontrado.")


def perform_manual_backup(db: Session, project_root: str) -> dict:
    backup_dir = os.path.join(project_root, "Backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = get_now_local().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"automacoes_backup_{ts}.db")

    db.execute(text(f"VACUUM INTO '{backup_path}'"))
    size_mb = round(os.path.getsize(backup_path) / (1024 * 1024), 2)

    backups = sorted(
        [
            os.path.join(backup_dir, item)
            for item in os.listdir(backup_dir)
            if item.endswith(".db")
        ]
    )
    if len(backups) > 7:
        for old_backup in backups[:-7]:
            os.remove(old_backup)

    return {
        "message": "Backup realizado com sucesso.",
        "path": backup_path,
        "size_mb": size_mb,
    }


def build_version_payload(startup_time: datetime) -> schemas.SystemVersion:
    uptime = get_now_local() - startup_time
    max_workers = int(os.environ.get("WORKER_MAX_CONCURRENCY", "4"))
    return schemas.SystemVersion(
        version=ORCHESTRATOR_VERSION,
        schema_version=get_schema_version(),
        python_version=sys.version.split()[0],
        started_at=schemas.format_dt_br(startup_time),
        uptime_seconds=round(uptime.total_seconds(), 2),
        max_workers=max_workers,
        allowed_origins=get_allowed_origins(),
    )
