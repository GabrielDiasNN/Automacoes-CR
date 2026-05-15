# pylint: disable=all
# mypy: ignore-errors
"""
Worker Central de Automacoes v5.3 - Motor de Execucao Concorrente com Tipagem Estrita e Log Batching.
"""

import base64
import glob
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Empty, Queue
from types import FrameType
from typing import Any, Dict, List, Optional, cast

import requests
from dotenv import load_dotenv

# Garantir que o pacote 'app' seja localizavel
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app import models, notifications
    from app.database import SessionLocal
    from app.timezone import get_now_local
except ImportError as e:
    print(f"CRITICAL: Falha ao importar componentes do app: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuracao de Ambiente
# ---------------------------------------------------------------------------

project_root: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(project_root, ".env"))

MAX_WORKERS: int = int(os.environ.get("WORKER_MAX_CONCURRENCY", "4"))
HEARTBEAT_INTERVAL: int = 15  # segundos
POLL_INTERVAL: int = 2  # segundos
WORKER_VERSION: str = "5.3.0"
_port = os.environ.get("HUB_API_PORT", "8000")
API_BASE: str = f"http://127.0.0.1:{_port}"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs")
os.makedirs(log_dir, exist_ok=True)

class _JsonFormatter(logging.Formatter):
    """Formatter JSON estruturado identico ao Orchestrator (Pilar L)."""

    def format(self, record: logging.LogRecord) -> str:
        doc: Dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", None),
        }
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        return json.dumps(doc)

_json_handler = logging.handlers.RotatingFileHandler(
    os.path.join(log_dir, "Worker.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_json_handler.setFormatter(_JsonFormatter())

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)

logging.root.setLevel(logging.INFO)
logging.root.addHandler(_json_handler)
logging.root.addHandler(_console_handler)

logger: logging.Logger = logging.getLogger("worker")

# ---------------------------------------------------------------------------
# Estado Global
# ---------------------------------------------------------------------------

shutdown_event: threading.Event = threading.Event()
start_time: float = time.time()
stats: Dict[str, Any] = {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "active_tasks": 0,
    "lock": threading.Lock(),
    "active_processes": {}, # {exec_id: Popen_object}
}

def update_stat(key: str, delta: int = 1) -> None:
    """Atualiza estatistica global de forma thread-safe."""
    with cast(threading.Lock, stats["lock"]):
        stats[key] += delta

# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def heartbeat_loop() -> None:
    """Atualiza o heartbeat no banco a cada HEARTBEAT_INTERVAL segundos."""
    logger.info("Heartbeat thread iniciada (intervalo: %ds)", HEARTBEAT_INTERVAL)
    while not shutdown_event.is_set():
        try:
            db = SessionLocal()
            hb = (
                db.query(models.WorkerHeartbeat)
                .filter(models.WorkerHeartbeat.id == 1)
                .first()
            )
            now: datetime = get_now_local()

            with cast(threading.Lock, stats["lock"]):
                completed: int = stats["tasks_completed"]
                failed: int = stats["tasks_failed"]
                active: int = stats["active_tasks"]

            if not hb:
                hb = models.WorkerHeartbeat(
                    id=1,
                    pid=os.getpid(),
                    last_ping=now,
                    uptime_seconds=time.time() - start_time,
                    tasks_completed=completed,
                    tasks_failed=failed,
                    active_tasks=active,
                    version=WORKER_VERSION,
                )
                db.add(hb)
            else:
                hb.pid = os.getpid()
                hb.last_ping = now
                hb.uptime_seconds = round(time.time() - start_time, 2)
                hb.tasks_completed = completed
                hb.tasks_failed = failed
                hb.active_tasks = active
                hb.version = WORKER_VERSION

            db.commit()
            db.close()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Erro no heartbeat: %s", e)
        shutdown_event.wait(HEARTBEAT_INTERVAL)

# ---------------------------------------------------------------------------
# Broadcast de Logs
# ---------------------------------------------------------------------------

log_buffer: Dict[str, List[str]] = {}
log_buffer_lock: threading.Lock = threading.Lock()

def broadcast_log(message: str, exec_id: str) -> None:
    """Apenas enfileira o log para envio em lote (Batched Broadcasting)."""
    with log_buffer_lock:
        if exec_id not in log_buffer:
            log_buffer[exec_id] = []
        log_buffer[exec_id].append(message)

def log_flusher_loop() -> None:
    """Thread em background que envia os logs em lote a cada 1 segundo para o WebSocket."""
    logger.info("Log flusher thread iniciada.")
    while not shutdown_event.is_set():
        shutdown_event.wait(1.0) # Intervalo do batch
        
        # Copiar o buffer rapidamente e limpar o original
        with log_buffer_lock:
            if not log_buffer:
                continue
            to_flush = log_buffer.copy()
            log_buffer.clear()
            
        for exec_id, messages in to_flush.items():
            if not messages:
                continue
            pending = "".join(messages)
            try:
                requests.post(
                    f"{API_BASE}/api/broadcast_log",
                    json={"exec_id": exec_id, "message": pending},
                    timeout=2,
                )
            except requests.RequestException:
                pass # Em caso de erro, os logs daquela janela sao perdidos no websocket, mas estarao salvos no banco.

def broadcast_event(event_type: str, data: Dict[str, Any]) -> None:
    """Envia evento de sistema para o WebSocket global."""
    try:
        requests.post(
            f"{API_BASE}/api/broadcast_event",
            json={"type": event_type, "data": data},
            timeout=2,
        )
    except requests.RequestException:
        pass

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def enqueue_output(out: Any, queue: Queue[str]) -> None:
    """Le stdout do processo e coloca na fila."""
    for line in iter(out.readline, ""):
        queue.put(cast(str, line))
    out.close()

def scan_for_artifacts(robot_dir: str, start_time_ts: float) -> Optional[str]:
    """Busca arquivos gerados durante esta execucao."""
    patterns: List[str] = ["*.xlsx", "*.html", "*.pdf", "*.csv"]
    found: List[str] = []
    for pattern in patterns:
        for fp in glob.glob(os.path.join(robot_dir, pattern)):
            if os.path.getmtime(fp) >= start_time_ts:
                found.append(os.path.basename(fp))
    return json.dumps(found) if found else None

# ---------------------------------------------------------------------------
# Execucao de Tarefa
# ---------------------------------------------------------------------------

def run_task(exec_id: str, script_path: str, max_runtime: int = 30) -> None:
    """Executa uma tarefa em subprocesso com monitoramento completo."""
    update_stat("active_tasks", 1)
    db = SessionLocal()
    task_start_ts: float = time.time()
    _log_extra: Dict[str, str] = {"correlation_id": exec_id}

    try:
        db_exec = (
            db.query(models.Execution).filter(models.Execution.id == exec_id).first()
        )
        if not db_exec:
            return

        logger.info(
            "Iniciando tarefa %s -> %s (Timeout: %dmin)",
            exec_id,
            script_path,
            max_runtime,
            extra=_log_extra,
        )
        db_exec.status = "RUNNING"
        db.commit()

        broadcast_event(
            "TASK_STARTED",
            {
                "exec_id": exec_id,
                "automation_id": db_exec.automation_id,
            },
        )

        task_start: datetime = get_now_local()
        timeout_delta: timedelta = timedelta(minutes=max_runtime)
        robot_dir: str = os.path.dirname(script_path)

        # Injeta status de modo teste para o processo filho
        env = os.environ.copy()
        env["ORCHESTRATOR_TEST_MODE"] = "true" if db_exec.automation.test_mode else "false"

        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
                exec_id,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env
        )

        # Registrar processo ativo para encerramento em caso de shutdown
        with cast(threading.Lock, stats["lock"]):
            stats["active_processes"][exec_id] = process

        q: Queue[str] = Queue()
        reader_thread: threading.Thread = threading.Thread(
            target=enqueue_output, args=(process.stdout, q)
        )
        reader_thread.daemon = True
        reader_thread.start()

        logs: List[str] = []
        while not shutdown_event.is_set():
            try:
                while True:
                    line: str = q.get_nowait()
                    logs.append(line)
                    broadcast_log(line, exec_id)
            except Empty:
                pass

            return_code: Optional[int] = process.poll()
            if return_code is not None:
                while not q.empty():
                    line = q.get_nowait()
                    logs.append(line)
                    broadcast_log(line, exec_id)
                break

            with SessionLocal() as check_db:
                db_status: Any = (
                    check_db.query(models.Execution.status)
                    .filter(models.Execution.id == exec_id)
                    .scalar()
                )

                if db_status == "TERMINATED":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                        capture_output=True,
                        check=False,
                    )
                    broadcast_log("\n[INTERROMPIDO PELO USUÁRIO]\n", exec_id)
                    update_stat("active_tasks", -1)
                    broadcast_event("TASK_STOPPED", {"exec_id": exec_id})
                    return

                if (get_now_local() - task_start) > timeout_delta:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                        capture_output=True,
                        check=False,
                    )
                    broadcast_log(
                        f"\n[TIMEOUT AUTOMÁTICO: {max_runtime}min]\n", exec_id
                    )

                    db_exec_upd = (
                        check_db.query(models.Execution)
                        .filter(models.Execution.id == exec_id)
                        .first()
                    )
                    if db_exec_upd:
                        db_exec_upd.status = "TIMEOUT"
                        db_exec_upd.finished_at = get_now_local()
                        db_exec_upd.duration_seconds = round(
                            time.time() - task_start_ts, 2
                        )
                        db_exec_upd.logs = (
                            "".join(logs) + "\n[ERRO] Tarefa excedeu o tempo máximo."
                        )
                        check_db.commit()

                        auto = (
                            check_db.query(models.Automation)
                            .filter(models.Automation.id == db_exec_upd.automation_id)
                            .first()
                        )
                        if auto:
                            notifications.dispatch_alerts(auto, db_exec_upd)

                    update_stat("active_tasks", -1)
                    update_stat("tasks_failed", 1)
                    broadcast_event("TASK_TIMEOUT", {"exec_id": exec_id})
                    return

            time.sleep(1)

        broadcast_log(
            f"\n[Fim da Execução - ExitCode: {process.returncode}]\n", exec_id
        )
        duration: float = round(time.time() - task_start_ts, 2)
        artifacts_json: Optional[str] = scan_for_artifacts(robot_dir, task_start_ts)

        db_exec = (
            db.query(models.Execution).filter(models.Execution.id == exec_id).first()
        )
        if db_exec and db_exec.status not in ["TERMINATED", "TIMEOUT"]:
            db_exec.exit_code = process.returncode
            db_exec.duration_seconds = duration

            if process.returncode in [0, 2, 3]:
                db_exec.status = "SUCCESS"
                update_stat("tasks_completed", 1)
            else:
                db_exec.status = "ERROR"
                update_stat("tasks_failed", 1)

            db_exec.logs = "".join(logs)
            db_exec.artifacts = artifacts_json
            db_exec.finished_at = get_now_local()
            db.commit()

            if db_exec.status == "ERROR":
                auto = (
                    db.query(models.Automation)
                    .filter(models.Automation.id == db_exec.automation_id)
                    .first()
                )
                if auto:
                    notifications.dispatch_alerts(auto, db_exec)

            broadcast_event(
                "TASK_COMPLETED",
                {
                    "exec_id": exec_id,
                    "status": db_exec.status,
                    "duration_seconds": duration,
                    "exit_code": process.returncode,
                },
            )

        logger.info(
            "Tarefa %s finalizada: %s (Code: %s, %.2fs)",
            exec_id,
            db_exec.status if db_exec else "UNK",
            process.returncode,
            duration,
            extra=_log_extra,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Erro fatal na tarefa %s: %s", exec_id, e, extra=_log_extra)
        db_exec = (
            db.query(models.Execution).filter(models.Execution.id == exec_id).first()
        )
        if db_exec and db_exec.status not in ["TERMINATED", "TIMEOUT"]:
            db_exec.status = "ERROR"
            db_exec.logs = (db_exec.logs or "") + f"\nInternal Worker Error: {str(e)}"
            db_exec.exit_code = -1
            db_exec.finished_at = get_now_local()
            db_exec.duration_seconds = round(time.time() - task_start_ts, 2)
            db.commit()
        update_stat("tasks_failed", 1)
        broadcast_event("TASK_FAILED", {"exec_id": exec_id, "error": str(e)})
    finally:
        with cast(threading.Lock, stats["lock"]):
            stats["active_tasks"] -= 1
            if exec_id in stats["active_processes"]:
                del stats["active_processes"][exec_id]
        db.close()

# ---------------------------------------------------------------------------
# Loop Principal
# ---------------------------------------------------------------------------

def main_loop() -> None:
    """Loop principal: consome tarefas PENDING e despacha para o ThreadPool."""
    logger.info(
        "Worker v%s iniciado (PID: %d, MaxWorkers: %d)",
        WORKER_VERSION,
        os.getpid(),
        MAX_WORKERS,
    )

    hb_thread: threading.Thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    flusher_thread: threading.Thread = threading.Thread(target=log_flusher_loop, daemon=True)
    flusher_thread.start()

    executor: ThreadPoolExecutor = ThreadPoolExecutor(
        max_workers=MAX_WORKERS, thread_name_prefix="task"
    )

    while not shutdown_event.is_set():
        db = SessionLocal()
        try:
            # Atomic Claim Logic (v5.2.1)
            pending_task = (
                db.query(models.Execution)
                .filter(models.Execution.status == "PENDING")
                .order_by(models.Execution.priority.asc(), models.Execution.started_at.asc())
                .with_for_update(skip_locked=True) # SQLite ignora with_for_update, mas mantemos para padrao
                .first()
            )

            if pending_task:
                # Marcar como RUNNING imediatamente no banco antes de despachar
                exec_id = pending_task.id
                pending_task.status = "RUNNING"
                pending_task.started_at = get_now_local()
                db.commit()

                # Re-buscar para garantir que temos os dados apos o commit
                automation = (
                    db.query(models.Automation)
                    .filter(models.Automation.id == pending_task.automation_id)
                    .first()
                )

                if automation:
                    path: str = automation.script_path
                    if path.startswith("./") or path.startswith(".\\"):
                        path = os.path.join(project_root, path[2:])
                    elif not os.path.isabs(path):
                        path = os.path.join(project_root, path)

                    script_path: str = os.path.abspath(path)
                    max_rt: int = automation.max_runtime_minutes or 30

                    executor.submit(run_task, exec_id, script_path, max_rt)
                    logger.info(
                        "Tarefa despachada para pool: %s (%s)",
                        automation.name,
                        exec_id,
                    )
                else:
                    pending_task.status = "ERROR"
                    pending_task.logs = "Automacao nao encontrada no banco."
                    pending_task.finished_at = get_now_local()
                    db.commit()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Erro no loop do worker: %s", e)
        finally:
            db.close()

        shutdown_event.wait(POLL_INTERVAL)

    logger.info("Shutdown solicitado. Encerrando tarefas ativas...")

    # Pillar G: Terminacao forcada de processos filhos para evitar orfaos
    with cast(threading.Lock, stats["lock"]):
        for eid, proc in stats["active_processes"].items():
            logger.warning("Terminando processo %s (Shutdown)", eid)
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
            except Exception as e:
                logger.warning("Falha ao encerrar processo %s: %s", eid, e)

    executor.shutdown(wait=True, cancel_futures=False)
    logger.info("Worker encerrado de forma controlada.")

# ---------------------------------------------------------------------------
# Signal Handlers
# ---------------------------------------------------------------------------

def _signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    logger.info("Sinal recebido: %d. Iniciando graceful shutdown...", signum)
    shutdown_event.set()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    main_loop()
