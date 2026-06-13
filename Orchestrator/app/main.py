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

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401 — registers ORM tables in Base.metadata
from .constants import ORCHESTRATOR_SCHEMA_VERSION, ORCHESTRATOR_VERSION
from .database import SessionLocal, session_scope
from .error_handlers import register_exception_handlers
from .logger_setup import setup_json_logger
from .middleware import (RateLimitMiddleware, RequestIdMiddleware,
                         TimingMiddleware)
from .routers import (automation_config, automation_ide, automations,
                      beneficiamento, executions, portfolio, system, websocket)
from .runtime import (get_allowed_origins, get_dashboard_path, get_lib_path,
                      scheduler)
from .services.execution_runtime import mark_running_tasks_as_failed_by_reboot
from .services.scheduler_runtime import (register_enterprise_jobs,
                                         reload_scheduled_tasks)

# ---------------------------------------------------------------------------
# Configuracao de Logs Estruturados (JSON)
# ---------------------------------------------------------------------------

log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Logs")
os.makedirs(log_dir, exist_ok=True)

is_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
log_filename = "orchestrator_test.jsonl" if is_pytest else "orchestrator.jsonl"

logger = setup_json_logger(
    "orchestrator",
    os.path.join(log_dir, log_filename),
    component="orchestrator",
    use_context_vars=True,
)


def _cleanup_zombie_tasks():
    with session_scope(SessionLocal) as db:
        zombie_count = mark_running_tasks_as_failed_by_reboot(db)
        if zombie_count:
            logger.info("Limpeza: %d tarefas recuperadas.", zombie_count)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pilar E - Escala: Garantir integridade do banco no startup
    from .timezone import get_now_local
    app.state.startup_time = get_now_local()
    from .database import (run_alembic_migrations, run_wal_checkpoint,
                           validate_database_schema)

    run_wal_checkpoint("TRUNCATE")

    migration_result = run_alembic_migrations()
    if migration_result.get("applied"):
        logger.info(
            "Migracoes estruturadas do Alembic aplicadas com sucesso: %s",
            ", ".join(migration_result["applied"]),
        )
    schema_status = validate_database_schema()
    if not schema_status["valid"]:
        logger.error(f"Schema do banco incompleto: {schema_status}")
        raise RuntimeError(f"Schema do banco incompleto: {schema_status}")
    _cleanup_zombie_tasks()
    reload_scheduled_tasks()
    retention = int(os.environ.get("EXECUTION_RETENTION_DAYS", "90"))
    register_enterprise_jobs(retention)

    if not scheduler.running:
        scheduler.start()
    logger.info(
        "Central de Automações v%s - Orchestrator online. Schema=%s",
        ORCHESTRATOR_VERSION,
        ORCHESTRATOR_SCHEMA_VERSION,
    )
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("Orchestrator offline.")


# ---------------------------------------------------------------------------
# Aplicativo FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Central de Automações", version=ORCHESTRATOR_VERSION, lifespan=lifespan
)

register_exception_handlers(app, logger)

# --- CORS Hardened: restrito a origens configuradas via .env ---
_allowed_origins = get_allowed_origins()

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
app.include_router(automation_config.router)
app.include_router(automation_ide.router)
app.include_router(executions.router)
app.include_router(beneficiamento.router)
app.include_router(portfolio.router)
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
dashboard_path = get_dashboard_path()
lib_path = get_lib_path()


class RevalidatedStaticFiles(StaticFiles):
    """StaticFiles com Cache-Control: no-cache.

    Forca o browser a revalidar (ETag/304) a cada request, garantindo que o
    Dashboard sempre sirva a versao atual sem depender de ?v= nos imports ES.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


if os.path.exists(dashboard_path):
    app.mount(
        "/dashboard",
        RevalidatedStaticFiles(directory=dashboard_path, html=True),
        name="dashboard",
    )
    logger.info(f"Dashboard montado em: {dashboard_path}")
else:
    logger.error(f"ERRO: Pasta Dashboard não encontrada em: {dashboard_path}")

if os.path.exists(lib_path):
    app.mount("/lib", StaticFiles(directory=lib_path), name="lib")


@app.get("/")
def read_root():
    return {
        "status": "online",
        "version": ORCHESTRATOR_VERSION,
        "scheduler_running": scheduler.running,
        "dashboard_url": "/dashboard/",
        "docs_url": "/docs",
    }
