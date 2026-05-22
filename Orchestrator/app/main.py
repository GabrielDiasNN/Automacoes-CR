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

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder

from . import models
from .constants import ORCHESTRATOR_SCHEMA_VERSION, ORCHESTRATOR_VERSION
from .database import SessionLocal, engine
from .middleware import RateLimitMiddleware, RequestIdMiddleware, TimingMiddleware
from .routers import automations, executions, system, websocket, automation_config, automation_ide
from .runtime import get_allowed_origins, get_dashboard_path, get_lib_path, scheduler
from .services.execution_runtime import mark_running_tasks_as_failed_by_reboot
from .services.scheduler_runtime import register_enterprise_jobs, reload_scheduled_tasks

# ---------------------------------------------------------------------------
# Configuracao de Logs Estruturados (JSON)
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Formatter customizado para emitir logs em JSON estruturado (Pilar L)."""

    def format(self, record):
        from .security import sanitize_log_payload
        from .middleware import request_id_var, exec_id_var, automation_name_var
        
        req_id = request_id_var.get("SYSTEM")
        
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "component": "orchestrator",
            "environment": os.environ.get("ENVIRONMENT", "PRD"),
            "automation_name": automation_name_var.get(""),
            "exec_id": exec_id_var.get(""),
            "request_id": getattr(record, "request_id", req_id),
            "message": sanitize_log_payload(record.getMessage()),
        }
        
        if hasattr(record, "context"):
            log_record["context"] = sanitize_log_payload(record.context)
            
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)


log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Logs"
)
os.makedirs(log_dir, exist_ok=True)

import sys
is_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
log_filename = "orchestrator_test.jsonl" if is_pytest else "orchestrator.jsonl"
LOG_FILE = os.path.join(log_dir, log_filename)

handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%SZ"))

# Console em formato legivel
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console_handler.setFormatter(console_formatter)

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.addHandler(console_handler)


def _get_correlation_id(request: Request) -> str:
    return getattr(request.state, "request_id", "SYSTEM")


def _build_error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    action_hint: str,
    detail: object | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "message": message,
        "action_hint": action_hint,
        "correlation_id": _get_correlation_id(request),
    }
    if detail is not None:
        payload["detail"] = detail
    return payload


def _cleanup_zombie_tasks():
    db = SessionLocal()
    try:
        zombie_count = mark_running_tasks_as_failed_by_reboot(db)
        if zombie_count:
            logger.info("Limpeza: %d tarefas recuperadas.", zombie_count)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pilar E - Escala: Garantir integridade do banco no startup
    from .timezone import get_now_local
    app.state.startup_time = get_now_local()
    from .database import (
        run_schema_migrations,
        run_wal_checkpoint,
        validate_database_schema,
    )

    run_wal_checkpoint("TRUNCATE")

    migration_result = run_schema_migrations()
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


# --- GLOBAL EXCEPTION HANDLERS (v9.2.0) ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if exc.detail is not None else "Falha de requisição."
    message = detail if isinstance(detail, str) else "Falha de requisição."
    action_hint = "Revisar os dados da requisição e tentar novamente."
    code = "bad_request"
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "access_denied"
        action_hint = "Validar a API Key e repetir a chamada."
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "resource_not_found"
        action_hint = "Verificar identificador e existência do recurso solicitado."
    elif exc.status_code == status.HTTP_409_CONFLICT:
        code = "conflict"
        action_hint = "Resolver conflito operacional e tentar novamente."
    elif exc.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
        code = "validation_error"
        action_hint = "Corrigir os campos inválidos enviados na requisição."

    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_payload(
            request,
            code=code,
            message=message,
            action_hint=action_hint,
            detail=detail,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for item in exc.errors():
        ctx = item.get("ctx")
        if isinstance(ctx, dict) and "error" in ctx:
            ctx = {**ctx, "error": str(ctx["error"])}
            item = {**item, "ctx": ctx}
        errors.append(item)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_build_error_payload(
            request,
            code="validation_error",
            message="Payload inválido para este endpoint.",
            action_hint="Corrigir os campos obrigatórios e formatos antes de reenviar.",
            detail=jsonable_encoder(errors),
        ),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Captura qualquer erro não tratado e devolve JSON padronizado (Pilar R)."""
    error_id = str(int(time.time()))
    correlation_id = _get_correlation_id(request)
    logger.error(
        "Unhandled Error [%s] correlation_id=%s: %s",
        error_id,
        correlation_id,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content=_build_error_payload(
            request,
            code="internal_error",
            message="Ocorreu um erro interno no servidor.",
            action_hint="Consultar logs da API com o correlation_id antes de nova tentativa.",
            detail={
                "error_id": error_id,
                "type": type(exc).__name__,
            },
        ),
    )


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

if os.path.exists(dashboard_path):
    app.mount(
        "/dashboard", StaticFiles(directory=dashboard_path, html=True), name="dashboard"
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
