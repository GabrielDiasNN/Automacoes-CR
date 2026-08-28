"""Serviços operacionais de runtime do Orchestrator."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, cast

import psutil
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import ORCHESTRATOR_VERSION
from ..database import get_db_size_mb, get_schema_version, get_wal_size_mb
from ..runtime import get_allowed_origins, scheduler
from ..timezone import get_now_local

logger = logging.getLogger("orchestrator")


def _probe_database(db: Session) -> bool:
    """SELECT 1 no banco. Loga o erro internamente; nunca propaga a mensagem."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Falha ao consultar o banco no health check: %s", exc)
        return False


def build_liveness_payload(
    db: Session, worker_status: schemas.WorkerStatus
) -> schemas.SystemLiveness:
    """Liveness público: só o veredito, sem métricas internas nem exceção crua.

    Contraparte reduzida de ``build_health_payload``, servida por
    ``GET /api/system/health`` (rota pública — ver ``docs/security-policy.md``).
    """
    db_ok = _probe_database(db)
    if not db_ok or not scheduler.running:
        status = "unhealthy"
    elif not worker_status.is_alive:
        status = "degraded"
    else:
        status = "ok"
    return schemas.SystemLiveness(status=status, timestamp=get_now_local())


def get_worker_status(db: Session) -> schemas.WorkerStatus:
    hb = db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()
    if not hb or not hb.last_ping:
        return schemas.WorkerStatus(is_alive=False)

    now = get_now_local()
    # Tolerância de 90s (6x o intervalo de 15s), permitindo absorver contenções de
    # lock SQLite (busy_timeout=30s) sem declarar falso worker offline.
    is_alive = (now - hb.last_ping).total_seconds() < 90
    return schemas.WorkerStatus(
        is_alive=is_alive,
        pid=cast(int | None, hb.pid),
        instance_id=cast(str | None, hb.instance_id),
        host=cast(str | None, hb.host),
        last_ping=hb.last_ping,
        uptime_seconds=cast(float | None, hb.uptime_seconds),
        tasks_completed=cast(int, hb.tasks_completed),
        tasks_failed=cast(int, hb.tasks_failed),
        active_tasks=cast(int, hb.active_tasks),
        pool_saturated_seconds=cast(float | None, hb.pool_saturated_seconds) or 0.0,
        version=str(hb.version or "unknown"),
    )


def build_health_payload(
    db: Session, worker_status: schemas.WorkerStatus
) -> schemas.SystemHealth:
    # `str(exc)` de um sqlite3.OperationalError costuma trazer o caminho
    # absoluto do .db; num payload não autenticado isso vaza layout de disco.
    # O detalhe vai só para o logger interno (ver `_probe_database`).
    db_status = "online" if _probe_database(db) else "erro"

    sched_status = "executando" if scheduler.running else "parado"
    pending = (
        db.query(models.Execution).filter(models.Execution.status == "PENDING").count()
    )
    overall = "healthy"
    if db_status != "online" or not scheduler.running:
        overall = "unhealthy"
    elif not worker_status.is_alive:
        overall = "degraded"

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
        with (
            open(stdout_log, "a", encoding="utf-8") as stdout,
            open(stderr_log, "a", encoding="utf-8") as stderr,
        ):
            subprocess.Popen(  # pylint: disable=consider-using-with
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


def perform_manual_backup(db: Session, project_root: str) -> dict[str, Any]:
    backup_dir = os.path.join(project_root, "Backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = get_now_local().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"automacoes_backup_{ts}.db")

    # `VACUUM INTO` não aceita bind parameter para o destino, então o caminho
    # entra por f-string. Hoje `backup_path` é 100% derivado no servidor (raiz do
    # projeto + timestamp), sem entrada do cliente; a checagem de aspa é uma
    # trava barata para o dia em que a raiz do projeto contiver um caractere que
    # quebre o literal SQL (achado de baixa severidade — risco futuro, não atual).
    if "'" in backup_path:
        raise ValueError("Caminho de backup inválido para VACUUM INTO.")
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
