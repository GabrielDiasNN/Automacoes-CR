"""
Orchestrator Central de Automacoes v1.0.0 - Ponto de Entrada.

Responsabilidades:
  1. Inicializar FastAPI e agendador
  2. Servir Dashboard SPA (arquivos estaticos)
  3. Logging estruturado JSON (Padrao Ouro)
  4. Rotas de compatibilidade legada
  5. Jobs enterprise: WAL checkpoint + purge automatico (Pilares E + G)
"""

import asyncio
import os
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from . import models  # noqa: F401 pylint: disable=unused-import
from .constants import ORCHESTRATOR_SCHEMA_VERSION, ORCHESTRATOR_VERSION
from .database import (
    SessionLocal,
    run_alembic_migrations,
    run_wal_checkpoint,
    session_scope,
    validate_database_schema,
)
from .error_handlers import register_exception_handlers
from .logger_setup import setup_json_logger
from .middleware import RateLimitMiddleware, RequestIdMiddleware, TimingMiddleware
from .routers import (
    automation_config,
    automation_ide,
    automations,
    beneficiamento,
    executions,
    portfolio,
    system,
    websocket,
)
from .runtime import (
    get_allowed_origins,
    get_dashboard_path,
    get_lib_path,
    register_event_loop,
    scheduler,
)
from .services.execution_runtime import mark_running_tasks_as_failed_by_reboot
from .services.scheduler_runtime import register_enterprise_jobs, reload_scheduled_tasks
from .telemetry import setup_telemetry
from .timezone import get_now_local

# ---------------------------------------------------------------------------
# Configuracao de Logs Estruturados (JSON)
# ---------------------------------------------------------------------------

log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Logs"
)
os.makedirs(log_dir, exist_ok=True)

is_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
LOG_FILENAME = "orchestrator_test.jsonl" if is_pytest else "orchestrator.jsonl"

logger = setup_json_logger(
    "orchestrator",
    os.path.join(log_dir, LOG_FILENAME),
    component="orchestrator",
    use_context_vars=True,
)


def _cleanup_zombie_tasks() -> None:
    with session_scope(SessionLocal) as db:
        zombie_count = mark_running_tasks_as_failed_by_reboot(db)
        if zombie_count:
            logger.info("Limpeza: %d tarefas recuperadas.", zombie_count)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncGenerator[None, None]:
    # Pilar E - Escala: Garantir integridade do banco no startup
    fastapi_app.state.startup_time = get_now_local()
    register_event_loop(asyncio.get_running_loop())
    run_wal_checkpoint("TRUNCATE")

    migration_result = run_alembic_migrations()
    if migration_result.get("applied"):
        logger.info(
            "Migracoes estruturadas do Alembic aplicadas com sucesso: %s",
            ", ".join(migration_result["applied"]),
        )
    schema_status = validate_database_schema()
    if not schema_status["valid"]:
        logger.error("Schema do banco incompleto: %s", schema_status)
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


class SecurityHeadersMiddleware(
    BaseHTTPMiddleware
):  # pylint: disable=too-few-public-methods
    """Injeta Content-Security-Policy e headers de segurança em todas as respostas (F1/1.6)."""

    async def dispatch(
        self,
        request: StarletteRequest,
        call_next: Callable[[StarletteRequest], Awaitable[StarletteResponse]],
    ) -> StarletteResponse:
        response: StarletteResponse = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            # Sem 'unsafe-inline' em script-src: o build do Vite emite apenas
            # <script type="module" src=...> externo, nenhum script inline — a
            # permissão era desnecessária e neutralizava a proteção anti-XSS da
            # CSP (achado #43). Mantido em style-src, onde o React/Vite ainda
            # injeta estilos inline.
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            # 'self' já cobre o WebSocket same-origin (CSP3): o Dashboard monta a
            # URL a partir de location.host com o protocolo casado. Os esquemas
            # abertos "ws: wss:" permitiam exfiltração via WS para qualquer host
            # em caso de XSS (achado #31).
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app = FastAPI(
    title="Central de Automações", version=ORCHESTRATOR_VERSION, lifespan=lifespan
)

register_exception_handlers(app, logger)

# --- CORS Hardened: restrito a origens configuradas via .env ---
_allowed_origins = get_allowed_origins()

setup_telemetry(app)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
# Registrado por ÚLTIMO de propósito: add_middleware empilha em LIFO, então o
# último registrado é a camada mais externa. Só assim os headers de segurança
# alcançam também as respostas short-circuit geradas por middlewares internos
# (ex.: o 429 do RateLimitMiddleware, que retorna sem chamar call_next) — antes
# elas saíam sem CSP/X-Frame-Options (achado #31).
app.add_middleware(SecurityHeadersMiddleware)

# Registrar routers
app.include_router(automations.router)
app.include_router(automation_config.router)
app.include_router(automation_ide.router)
app.include_router(executions.router)
app.include_router(beneficiamento.router)
app.include_router(portfolio.router)
app.include_router(system.router)
app.include_router(websocket.router)


# --- SERVICO DE ARQUIVOS ESTATICOS (DASHBOARD) ---
# Resolvendo raiz do projeto (C:\Automacoes)
dashboard_path = get_dashboard_path()
lib_path = get_lib_path()


class RevalidatedStaticFiles(StaticFiles):
    """StaticFiles com Cache-Control: no-cache.

    Forca o browser a revalidar (ETag/304) a cada request, garantindo que o
    Dashboard sempre sirva a versao atual sem depender de ?v= nos imports ES.
    """

    async def get_response(
        self, path: str, scope: MutableMapping[str, Any]
    ) -> StarletteResponse:
        # SPA fallback: rotas client-side (react-router, ex.: /dashboard/execucoes)
        # nao existem como arquivo; ao recarregar a pagina caem em index.html.
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response = await super().get_response("index.html", scope)
        if response.status_code == 404:
            response = await super().get_response("index.html", scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


if os.path.exists(dashboard_path):
    app.mount(
        "/dashboard",
        RevalidatedStaticFiles(directory=dashboard_path, html=True),
        name="dashboard",
    )
    logger.info("Dashboard montado em: %s", dashboard_path)
else:
    logger.error("ERRO: Pasta Dashboard não encontrada em: %s", dashboard_path)

if os.path.exists(lib_path):
    app.mount("/lib", StaticFiles(directory=lib_path), name="lib")


@app.get("/")
def read_root() -> dict[str, Any]:
    return {
        "status": "online",
        "version": ORCHESTRATOR_VERSION,
        "scheduler_running": scheduler.running,
        "dashboard_url": "/dashboard/",
        "docs_url": "/docs",
    }
