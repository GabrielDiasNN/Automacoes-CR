# pylint: disable=all
# mypy: ignore-errors
"""Estado de runtime compartilhado do Orchestrator."""

import asyncio
import os

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

task_queued_event = asyncio.Event()
scheduler = BackgroundScheduler(timezone=pytz.timezone("America/Sao_Paulo"))


def get_project_root() -> str:
    return PROJECT_ROOT


def get_dashboard_path() -> str:
    return os.path.join(PROJECT_ROOT, "Dashboard")


def get_lib_path() -> str:
    return os.path.join(PROJECT_ROOT, "lib")


def get_allowed_origins() -> list[str]:
    raw_origins = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost,http://127.0.0.1,http://localhost:8000,http://127.0.0.1:8000",
    )
    return [item.strip() for item in raw_origins.split(",") if item.strip()]


def trigger_worker_wakeup() -> None:
    task_queued_event.set()


async def wait_for_task_signal(timeout_seconds: int = 30) -> str:
    try:
        await asyncio.wait_for(task_queued_event.wait(), timeout=timeout_seconds)
        task_queued_event.clear()
        return "wakeup"
    except asyncio.TimeoutError:
        return "timeout"
