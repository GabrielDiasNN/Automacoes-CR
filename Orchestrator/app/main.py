# pylint: disable=all
# mypy: ignore-errors
"""
Orchestrator Central de Automacoes v5.0.0 - Ponto de Entrada.

Responsabilidades:
  1. Inicializar FastAPI e agendador
  2. Servir Dashboard SPA (arquivos estaticos)
  3. Logging estruturado JSON (Padrao Ouro)
  4. Rotas de compatibilidade legada
  5. Jobs enterprise: WAL checkpoint + purge automatico (Pilares E + G)
"""

import ast
import asyncio
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import models
from .database import SessionLocal, engine
from .middleware import (RateLimitMiddleware, RequestIdMiddleware,
                         TimingMiddleware)
from .routers import automations, executions, system, websocket
from .timezone import get_now_local

# ---------------------------------------------------------------------------
# Configuracao de Ambiente
# ---------------------------------------------------------------------------

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
load_dotenv(os.path.join(project_root, ".env"))

# ---------------------------------------------------------------------------
# Configuracao de Logs Estruturados (JSON)
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Formatter customizado para emitir logs em JSON estruturado (Pilar L)."""

    def format(self, record):
        log_record = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
            "request_id": getattr(record, "request_id", "SYSTEM"),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Logs"
)
os.makedirs(log_dir, exist_ok=True)

LOG_FILE = os.path.join(log_dir, "orchestrator.log")
handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))

# Console em formato legivel
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console_handler.setFormatter(console_formatter)

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.addHandler(console_handler)

# ---------------------------------------------------------------------------
# Motor de Agendamento (APScheduler)
# ---------------------------------------------------------------------------

# Nota: pytz deve estar disponivel se usado explicitamente
import pytz

scheduler = BackgroundScheduler(timezone=pytz.timezone("America/Sao_Paulo"))


def _scheduled_task_wrapper(automation_id: int):
    db = SessionLocal()
    try:
        db_auto = (
            db.query(models.Automation)
            .filter(models.Automation.id == automation_id)
            .first()
        )
        if not db_auto or not db_auto.enabled:
            return

        existing = (
            db.query(models.Execution)
            .filter(
                models.Execution.automation_id == automation_id,
                models.Execution.status.in_(["PENDING", "RUNNING"]),
            )
            .first()
        )

        if existing:
            logger.info(f"Agendamento ignorado: {db_auto.name} j\u00e1 tem execu\u00e7\u00e3o ativa.")
            return

        exec_id = f"CRON_{automation_id}_{int(time.time())}"
        db_exec = models.Execution(
            id=exec_id, automation_id=db_auto.id, status="PENDING", requested_by="CRON"
        )
        db.add(db_exec)
        db.commit()
        logger.info(f"Disparo agendado: {db_auto.name} -> {exec_id}")
    except Exception as e:
        logger.error(f"Erro no disparo agendado id={automation_id}: {e}")
    finally:
        db.close()


def reload_scheduled_tasks():
    # Remover apenas jobs de automacoes (preservar jobs enterprise)
    for job in scheduler.get_jobs():
        if job.id.startswith("job_"):
            scheduler.remove_job(job.id)
    db = SessionLocal()
    try:
        automations_db = (
            db.query(models.Automation).filter(models.Automation.enabled == True).all()
        )
        for auto in automations_db:
            if not auto.schedule:
                continue
            try:
                sched_data = json.loads(auto.schedule)
                days = ",".join(map(str, sched_data.get("daysOfWeek", [])))
                hours = ",".join(map(str, sched_data.get("hours", [])))
                minutes = ",".join(map(str, sched_data.get("minutes", [])))
                trigger = CronTrigger(
                    day_of_week=days if days else "*",
                    hour=hours if hours else "*",
                    minute=minutes if minutes else "0",
                )
                scheduler.add_job(
                    _scheduled_task_wrapper,
                    trigger,
                    args=[auto.id],
                    id=f"job_{auto.id}",
                )
            except Exception as e:
                logger.error(f"Erro ao agendar {auto.name}: {e}")
    finally:
        db.close()


def _cleanup_zombie_tasks():
    db = SessionLocal()
    try:
        zombies = (
            db.query(models.Execution)
            .filter(models.Execution.status.in_(["RUNNING", "PENDING"]))
            .all()
        )
        for task in zombies:
            task.status = "FAILED_BY_REBOOT"
            task.finished_at = get_now_local()
            task.logs = (task.logs or "") + "\n[REBOOT] Interrompida."
        db.commit()
        if zombies:
            logger.info(f"Limpeza: {len(zombies)} tarefas recuperadas.")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pilar E - Escala: Garantir integridade do banco no startup
    from .database import run_wal_checkpoint
    run_wal_checkpoint("TRUNCATE")

    models.Base.metadata.create_all(bind=engine)
    _cleanup_zombie_tasks()
    reload_scheduled_tasks()

    # --- Jobs Enterprise (Pilar E + G) ---
    import os as _os

    from .database import purge_old_executions, run_wal_checkpoint

    retention = int(_os.environ.get("EXECUTION_RETENTION_DAYS", "90"))

    # WAL Checkpoint a cada 30 minutos
    scheduler.add_job(
        run_wal_checkpoint,
        "interval",
        minutes=30,
        id="enterprise_wal_checkpoint",
        replace_existing=True,
    )
    # Purge diario as 03:00
    scheduler.add_job(
        lambda: purge_old_executions(retention),
        CronTrigger(hour=3, minute=0),
        id="enterprise_daily_purge",
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
    logger.info("Central de Automa\u00e7\u00f5es v5.2.0 - Orchestrator online.")
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("Orchestrator offline.")


# ---------------------------------------------------------------------------
# Aplicativo FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="Central de Automa\u00e7\u00f5es", version="5.2.0", lifespan=lifespan)

# --- CORS Hardened: restrito a origens configuradas via .env ---
_raw_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost,http://127.0.0.1,http://localhost:8000,http://127.0.0.1:8000",
)
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(RateLimitMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(automations.router)
app.include_router(executions.router)
app.include_router(system.router)
app.include_router(websocket.router)


# --- ROTAS DE COMPATIBILIDADE LEGADA ---
@app.get("/api/health")
def legacy_health():
    return RedirectResponse(url="/api/system/health")


@app.get("/api/metrics")
def legacy_metrics():
    return RedirectResponse(url="/api/system/metrics")


# --- SERVICO DE ARQUIVOS ESTATICOS (DASHBOARD) ---
# Resolvendo raiz do projeto (C:\Automacoes)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dashboard_path = os.path.join(BASE_DIR, "Dashboard")
lib_path = os.path.join(BASE_DIR, "lib")

if os.path.exists(dashboard_path):
    app.mount(
        "/dashboard", StaticFiles(directory=dashboard_path, html=True), name="dashboard"
    )
    logger.info(f"Dashboard montado em: {dashboard_path}")
else:
    logger.error(f"ERRO: Pasta Dashboard n\u00e3o encontrada em: {dashboard_path}")

if os.path.exists(lib_path):
    app.mount("/lib", StaticFiles(directory=lib_path), name="lib")


@app.get("/")
def read_root():
    return {
        "status": "online",
        "version": "5.2.0",
        "scheduler_running": scheduler.running,
        "dashboard_url": "/dashboard/",
        "docs_url": "/docs",
    }
