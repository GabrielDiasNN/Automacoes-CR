"""Estado de runtime compartilhado do Orchestrator."""

import asyncio
import logging
import os
import sys

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

logger = logging.getLogger("orchestrator")

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

task_queued_event = asyncio.Event()
scheduler = BackgroundScheduler(timezone=pytz.timezone("America/Sao_Paulo"))

# Loop do servidor, registrado no lifespan. Necessário porque endpoints sync
# rodam em threadpool e asyncio.Event.set() não é thread-safe.
_event_loop: asyncio.AbstractEventLoop | None = None  # pylint: disable=invalid-name


def register_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop  # pylint: disable=global-statement
    _event_loop = loop


def get_project_root() -> str:
    return PROJECT_ROOT


def get_dashboard_path() -> str:
    """Retorna Dashboard/dist/ se o build React existir, senão Dashboard/ (vanilla fallback)."""
    dist = os.path.join(PROJECT_ROOT, "Dashboard", "dist")
    if os.path.isdir(dist):
        return dist
    return os.path.join(PROJECT_ROOT, "Dashboard")


def get_lib_path() -> str:
    return os.path.join(PROJECT_ROOT, "lib")


def ensure_beneficiamento_on_path() -> bool:
    """Registra `Produção Beneficimento/src` no `sys.path` do runtime FastAPI.

    Ponto único de acoplamento entre o Orchestrator e o domínio Beneficiamento
    (achado A3 da revisão arquitetural): antes o `sys.path.insert` ficava inline
    no router, escondendo a dependência na camada HTTP. Retorna `True` se o
    diretório existe e está registrado.
    """
    src_dir = os.path.join(PROJECT_ROOT, "Produção Beneficimento", "src")
    if not os.path.isdir(src_dir):
        return False
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    return True


def get_allowed_origins() -> list[str]:
    raw_origins = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost,http://127.0.0.1,http://localhost:8000,http://127.0.0.1:8000",
    )
    return [item.strip() for item in raw_origins.split(",") if item.strip()]


def trigger_worker_wakeup() -> None:
    if _event_loop is not None and not _event_loop.is_closed():
        _event_loop.call_soon_threadsafe(task_queued_event.set)
        return
    # Sem loop registrado não há forma thread-safe de sinalizar: chamar
    # task_queued_event.set() aqui violaria a premissa documentada acima (o
    # chamador pode estar na threadpool de endpoints sync). No-op consciente —
    # o worker ainda assim busca a tarefa no próximo ciclo de polling (#34).
    logger.warning(
        "Wake-up do worker ignorado: event loop não registrado. "
        "A tarefa será consumida no próximo ciclo de polling."
    )


async def wait_for_task_signal(timeout_seconds: int = 30) -> str:
    try:
        await asyncio.wait_for(task_queued_event.wait(), timeout=timeout_seconds)
        task_queued_event.clear()
        return "wakeup"
    except TimeoutError:
        return "timeout"
