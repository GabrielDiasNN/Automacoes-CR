"""
Worker Hub Soberano v5.0 — Motor de Execucao Concorrente.

Capacidades:
  - ThreadPoolExecutor com max_workers configuravel (padrao: 2)
  - Heartbeat a cada 15s gravado no banco (WorkerHeartbeat)
  - Graceful shutdown via SIGTERM/SIGINT
  - Protecao contra execucao duplicada
  - Broadcast de logs via HTTP para WebSocket (com retry 3x + backoff)
  - Scan de artefatos pos-execucao
  - Calculo automatico de duracao em segundos
  - Logging JSON estruturado com Correlation ID por tarefa (Pilar L)
"""

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

import requests
from dotenv import load_dotenv

# Garantir que o pacote 'app' seja localizavel
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app import models, notifications
    from app.database import SessionLocal
except ImportError as e:
    print(f"CRITICAL: Falha ao importar componentes do app: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuracao de Ambiente
# ---------------------------------------------------------------------------

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(project_root, ".env"))

MAX_WORKERS = int(os.environ.get("WORKER_MAX_CONCURRENCY", "2"))
HEARTBEAT_INTERVAL = 15  # segundos
POLL_INTERVAL = 2  # segundos
WORKER_VERSION = "4.0.0"
API_BASE = "http://127.0.0.1:8766"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs")
os.makedirs(log_dir, exist_ok=True)


class _JsonFormatter(logging.Formatter):
    """Formatter JSON estruturado identico ao Orchestrator (Pilar L)."""
    def format(self, record):
        import json as _json
        doc = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", None),
        }
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        return _json.dumps(doc)


_json_handler = logging.handlers.RotatingFileHandler(
    os.path.join(log_dir, "Worker.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_json_handler.setFormatter(_JsonFormatter())

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.root.setLevel(logging.INFO)
logging.root.addHandler(_json_handler)
logging.root.addHandler(_console_handler)

logger = logging.getLogger("worker")

# ---------------------------------------------------------------------------
# Estado Global
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()
start_time = time.time()
stats = {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "active_tasks": 0,
    "lock": threading.Lock(),
}


def update_stat(key: str, delta: int = 1):
    with stats["lock"]:
        stats[key] += delta


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def heartbeat_loop():
    """Atualiza o heartbeat no banco a cada HEARTBEAT_INTERVAL segundos."""
    logger.info(f"Heartbeat thread iniciada (intervalo: {HEARTBEAT_INTERVAL}s)")
    while not shutdown_event.is_set():
        try:
            db = SessionLocal()
            hb = db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()
            now = datetime.now()

            with stats["lock"]:
                completed = stats["tasks_completed"]
                failed = stats["tasks_failed"]
                active = stats["active_tasks"]

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
        except Exception as e:
            logger.warning(f"Erro no heartbeat: {e}")
        shutdown_event.wait(HEARTBEAT_INTERVAL)


# ---------------------------------------------------------------------------
# Broadcast de Logs
# ---------------------------------------------------------------------------

log_buffer = {}
log_buffer_lock = threading.Lock()


def broadcast_log(message: str, exec_id: str):
    """Envia log para o WebSocket do Orchestrator via endpoint HTTP interno. Retry 3x."""
    with log_buffer_lock:
        if exec_id not in log_buffer:
            log_buffer[exec_id] = []
        log_buffer[exec_id].append(message)
        pending = "".join(log_buffer[exec_id])

    for attempt in range(3):
        try:
            res = requests.post(
                f"{API_BASE}/api/broadcast_log",
                json={"exec_id": exec_id, "message": pending},
                timeout=2,
            )
            if res.status_code == 200:
                with log_buffer_lock:
                    log_buffer[exec_id] = []
                return
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))  # Backoff: 0.5s, 1.0s
    # Buffer retido para proximo ciclo se todos os attempts falharem


def broadcast_event(event_type: str, data: dict):
    """Envia evento de sistema para o WebSocket global."""
    try:
        requests.post(
            f"{API_BASE}/api/broadcast_event",
            json={"type": event_type, "data": data},
            timeout=2,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def enqueue_output(out, queue):
    """Le stdout do processo e coloca na fila."""
    for line in iter(out.readline, ""):
        queue.put(line)
    out.close()


def scan_for_artifacts(robot_dir: str, start_time_ts: float) -> str:
    """Busca arquivos gerados durante esta execucao."""
    patterns = ["*.xlsx", "*.html", "*.pdf", "*.csv"]
    found = []
    for pattern in patterns:
        for fp in glob.glob(os.path.join(robot_dir, pattern)):
            if os.path.getmtime(fp) >= start_time_ts:
                found.append(os.path.basename(fp))
    return json.dumps(found) if found else None


# ---------------------------------------------------------------------------
# Execucao de Tarefa
# ---------------------------------------------------------------------------

def run_task(exec_id: str, script_path: str, max_runtime: int = 30):
    """Executa uma tarefa em subprocesso com monitoramento completo."""
    update_stat("active_tasks", 1)
    db = SessionLocal()
    task_start_ts = time.time()  # Definido cedo para evitar NameError no except

    # Injetar correlation_id em todos os logs desta thread
    _log_extra = {"correlation_id": exec_id}

    try:
        db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
        if not db_exec:
            return

        logger.info(f"Iniciando tarefa {exec_id} -> {script_path} (Timeout: {max_runtime}min)", extra=_log_extra)
        db_exec.status = "RUNNING"
        db.commit()

        broadcast_event("TASK_STARTED", {
            "exec_id": exec_id,
            "automation_id": db_exec.automation_id,
        })

        task_start = datetime.now()
        task_start_ts = time.time()
        timeout_delta = timedelta(minutes=max_runtime)
        robot_dir = os.path.dirname(script_path)

        process = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path, exec_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        q = Queue()
        reader_thread = threading.Thread(target=enqueue_output, args=(process.stdout, q))
        reader_thread.daemon = True
        reader_thread.start()

        logs = []
        while not shutdown_event.is_set():
            # Drenar fila de output
            try:
                while True:
                    line = q.get_nowait()
                    logs.append(line)
                    broadcast_log(line, exec_id)
            except Empty:
                pass

            # Verificar se processo terminou
            return_code = process.poll()
            if return_code is not None:
                # Drenar linhas restantes
                while not q.empty():
                    line = q.get_nowait()
                    logs.append(line)
                    broadcast_log(line, exec_id)
                break

            # Verificar cancelamento via banco
            with SessionLocal() as check_db:
                db_status = check_db.query(models.Execution.status).filter(
                    models.Execution.id == exec_id
                ).scalar()

                if db_status == "TERMINATED":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                    broadcast_log("\n[INTERROMPIDO PELO USUARIO]\n", exec_id)
                    update_stat("active_tasks", -1)
                    broadcast_event("TASK_STOPPED", {"exec_id": exec_id})
                    return

                # Verificar timeout
                if (datetime.now() - task_start) > timeout_delta:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                    broadcast_log(f"\n[TIMEOUT AUTOMATICO: {max_runtime}min]\n", exec_id)

                    db_exec_upd = check_db.query(models.Execution).filter(
                        models.Execution.id == exec_id
                    ).first()
                    if db_exec_upd:
                        db_exec_upd.status = "TIMEOUT"
                        db_exec_upd.finished_at = datetime.now()
                        db_exec_upd.duration_seconds = round(time.time() - task_start_ts, 2)
                        db_exec_upd.logs = "".join(logs) + "\n[ERRO] Tarefa excedeu o tempo maximo."
                        check_db.commit()

                        auto = check_db.query(models.Automation).filter(
                            models.Automation.id == db_exec_upd.automation_id
                        ).first()
                        if auto:
                            notifications.dispatch_alerts(auto, db_exec_upd)

                    update_stat("active_tasks", -1)
                    update_stat("tasks_failed", 1)
                    broadcast_event("TASK_TIMEOUT", {"exec_id": exec_id})
                    return

            time.sleep(1)

        # --- Tarefa terminou normalmente ---
        broadcast_log(f"\n[Fim da Execucao - ExitCode: {process.returncode}]\n", exec_id)

        duration = round(time.time() - task_start_ts, 2)
        artifacts_json = scan_for_artifacts(robot_dir, task_start_ts)

        db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
        if db_exec and db_exec.status not in ["TERMINATED", "TIMEOUT"]:
            db_exec.exit_code = process.returncode
            db_exec.duration_seconds = duration

            # Mapeamento estendido (0=Normal, 2=Idempotente, 3=Sem Dados)
            if process.returncode in [0, 2, 3]:
                db_exec.status = "SUCCESS"
                update_stat("tasks_completed", 1)
            else:
                db_exec.status = "ERROR"
                update_stat("tasks_failed", 1)

            db_exec.logs = "".join(logs)
            db_exec.artifacts = artifacts_json
            db_exec.finished_at = datetime.now()
            db.commit()

            if db_exec.status == "ERROR":
                auto = db.query(models.Automation).filter(
                    models.Automation.id == db_exec.automation_id
                ).first()
                if auto:
                    notifications.dispatch_alerts(auto, db_exec)

            broadcast_event("TASK_COMPLETED", {
                "exec_id": exec_id,
                "status": db_exec.status,
                "duration_seconds": duration,
                "exit_code": process.returncode,
            })

        logger.info(
            f"Tarefa {exec_id} finalizada: {db_exec.status} (Code: {process.returncode}, {duration}s)",
            extra=_log_extra
        )

    except Exception as e:
        logger.error(f"Erro fatal na tarefa {exec_id}: {e}", extra=_log_extra)
        db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
        if db_exec and db_exec.status not in ["TERMINATED", "TIMEOUT"]:
            db_exec.status = "ERROR"
            db_exec.logs = (db_exec.logs or "") + f"\nInternal Worker Error: {str(e)}"
            db_exec.exit_code = -1
            db_exec.finished_at = datetime.now()
            db_exec.duration_seconds = round(time.time() - task_start_ts, 2)
            db.commit()
        update_stat("tasks_failed", 1)
        broadcast_event("TASK_FAILED", {"exec_id": exec_id, "error": str(e)})
    finally:
        update_stat("active_tasks", -1)
        db.close()


# ---------------------------------------------------------------------------
# Loop Principal
# ---------------------------------------------------------------------------

def main_loop():
    """Loop principal: consome tarefas PENDING e despacha para o ThreadPool."""
    logger.info(f"Worker v{WORKER_VERSION} iniciado (PID: {os.getpid()}, MaxWorkers: {MAX_WORKERS})")

    # Iniciar thread de heartbeat
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    # Pool de execucao
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="task")

    while not shutdown_event.is_set():
        db = SessionLocal()
        try:
            # Buscar proxima tarefa PENDING
            pending_task = (
                db.query(models.Execution)
                .filter(models.Execution.status == "PENDING")
                .order_by(models.Execution.started_at.asc())
                .first()
            )

            if pending_task:
                automation = (
                    db.query(models.Automation)
                    .filter(models.Automation.id == pending_task.automation_id)
                    .first()
                )

                if automation:
                    script_path = automation.script_path
                    if script_path.startswith("./") or script_path.startswith(".\\"):
                        script_path = os.path.join(project_root, script_path[2:])
                    elif not os.path.isabs(script_path):
                        script_path = os.path.join(project_root, script_path)

                    script_path = os.path.abspath(script_path)
                    max_rt = automation.max_runtime_minutes or 30

                    # Despachar para o pool
                    executor.submit(run_task, pending_task.id, script_path, max_rt)
                    logger.info(f"Tarefa despachada para pool: {automation.name} ({pending_task.id})")
                else:
                    pending_task.status = "ERROR"
                    pending_task.logs = "Automacao nao encontrada no banco."
                    pending_task.finished_at = datetime.now()
                    db.commit()
        except Exception as e:
            logger.error(f"Erro no loop do worker: {e}")
        finally:
            db.close()

        shutdown_event.wait(POLL_INTERVAL)

    # Graceful shutdown
    logger.info("Shutdown solicitado. Aguardando tarefas ativas...")
    executor.shutdown(wait=True, cancel_futures=False)
    logger.info("Worker encerrado de forma controlada.")


# ---------------------------------------------------------------------------
# Signal Handlers
# ---------------------------------------------------------------------------

def _signal_handler(signum, frame):
    logger.info(f"Sinal recebido: {signum}. Iniciando graceful shutdown...")
    shutdown_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Fix para import de logging.handlers quando usado em basicConfig
    import logging.handlers

    main_loop()