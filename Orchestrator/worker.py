# pylint: disable=all
# mypy: ignore-errors
"""
Worker Central de Automacoes v5.3 - Motor de Execucao Concorrente com Tipagem Estrita e Log Batching.
"""

import base64
import glob
import json
import logging
import os
import signal
import socket
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
    from app.constants import (EXECUTION_DELIVERED_STATUSES,
                               EXECUTION_STATUS_ERROR,
                               EXECUTION_STATUS_PENDING,
                               EXECUTION_STATUS_RUNNING,
                               EXECUTION_STATUS_TERMINATED,
                               EXECUTION_STATUS_TIMEOUT, WORKER_VERSION)
    from app.database import SessionLocal, session_scope
    from app.runtime import get_project_root
    from app.services.execution_runtime import (apply_internal_worker_error,
                                                apply_timeout_result,
                                                claim_next_task,
                                                classify_process_result,
                                                complete_process_execution,
                                                finalize_terminated_task,
                                                mark_task_as_failed,
                                                resolve_script_path)
    from app.timezone import get_now_local
except ImportError as e:
    print(f"CRITICAL: Falha ao importar componentes do app: {e}")
    sys.exit(1)

# Compatibilidade de testes e chamadas legadas durante a refatoração.
_finalize_terminated_task = finalize_terminated_task
_mark_task_as_failed = mark_task_as_failed

# ---------------------------------------------------------------------------
# Configuracao de Ambiente
# ---------------------------------------------------------------------------

project_root: str = get_project_root()
load_dotenv(os.path.join(project_root, ".env"))

MAX_WORKERS: int = int(os.environ.get("WORKER_MAX_CONCURRENCY", "4"))
HEARTBEAT_INTERVAL: int = 15  # segundos
POLL_INTERVAL: float = 2.0
MAX_POLL_INTERVAL: float = 15.0
_port = os.environ.get("HUB_API_PORT", "8000")
API_BASE: str = f"http://127.0.0.1:{_port}"
WORKER_HOST: str = socket.gethostname()
WORKER_INSTANCE_ID: str = os.environ.get("WORKER_INSTANCE_ID") or (
    f"{WORKER_HOST}-{os.getpid()}-{int(time.time())}"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logs")
os.makedirs(log_dir, exist_ok=True)

is_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
log_filename = "Worker_test.jsonl" if is_pytest else "Worker.jsonl"

from app.logger_setup import setup_json_logger as _setup_json_logger

logger: logging.Logger = _setup_json_logger(
    "worker",
    os.path.join(log_dir, log_filename),
    component="worker",
    use_context_vars=False,
    configure_root=True,
)

# ---------------------------------------------------------------------------
# Estado Global
# ---------------------------------------------------------------------------

shutdown_event: threading.Event = threading.Event()
wakeup_event: threading.Event = threading.Event()  # Novo: Evento de Wakeup (v6.2.0)
start_time: float = time.time()
stats: Dict[str, Any] = {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "active_tasks": 0,
    "lock": threading.Lock(),
    "active_processes": {},  # {exec_id: Popen_object}
}


def update_stat(key: str, delta: int = 1) -> None:
    """Atualiza estatistica global de forma thread-safe."""
    with cast(threading.Lock, stats["lock"]):
        stats[key] += delta


# ---------------------------------------------------------------------------
# Wakeup Listener (Instant Wakeup)
# ---------------------------------------------------------------------------


def _api_headers() -> Dict[str, str]:
    """Headers de autenticacao para chamadas internas a API do Orchestrator."""
    api_key = os.environ.get("ORCHESTRATOR_API_KEY")
    return {"X-API-Key": api_key} if api_key else {}


def wakeup_listener_loop() -> None:
    """Escuta o sinal de wakeup do Orchestrator via Long-Polling (v6.2.0)."""
    logger.info("Wakeup listener iniciado (Zero-Latency Mode).")
    headers = _api_headers()
    while not shutdown_event.is_set():
        try:
            # Long polling de 30s no Orchestrator
            res = requests.get(
                f"{API_BASE}/api/system/wait-for-task",
                headers=headers,
                timeout=35,
            )
            if res.status_code == 200 and res.json().get("status") == "wakeup":
                logger.info("Sinal de wakeup recebido!")
                wakeup_event.set()
        except requests.RequestException:
            # Falha de rede esperada (API offline/reiniciando): retenta sem poluir o log.
            shutdown_event.wait(5)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Erro inesperado: mantém a resiliência do loop, mas registra para diagnóstico.
            logger.warning("Erro inesperado no wakeup listener: %s", exc)
            shutdown_event.wait(5)


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


def heartbeat_loop() -> None:
    """Atualiza o heartbeat no banco a cada HEARTBEAT_INTERVAL segundos."""
    logger.info("Heartbeat thread iniciada (intervalo: %ds)", HEARTBEAT_INTERVAL)
    while not shutdown_event.is_set():
        try:
            with session_scope(SessionLocal) as db:
                _update_heartbeat(db)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Erro no heartbeat: %s", e)
        shutdown_event.wait(HEARTBEAT_INTERVAL)


def _update_heartbeat(db: Any) -> None:
    """Insere ou atualiza o registro de heartbeat do worker."""
    hb = db.query(models.WorkerHeartbeat).filter(models.WorkerHeartbeat.id == 1).first()
    now: datetime = get_now_local()

    with cast(threading.Lock, stats["lock"]):
        completed: int = stats["tasks_completed"]
        failed: int = stats["tasks_failed"]
        active: int = stats["active_tasks"]

    if not hb:
        hb = models.WorkerHeartbeat(
            id=1,
            pid=os.getpid(),
            instance_id=WORKER_INSTANCE_ID,
            host=WORKER_HOST,
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
        hb.instance_id = WORKER_INSTANCE_ID
        hb.host = WORKER_HOST
        hb.last_ping = now
        hb.uptime_seconds = round(time.time() - start_time, 2)
        hb.tasks_completed = completed
        hb.tasks_failed = failed
        hb.active_tasks = active
        hb.version = WORKER_VERSION

    db.commit()


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
        shutdown_event.wait(1.0)  # Intervalo do batch

        # Copiar o buffer rapidamente e limpar o original
        with log_buffer_lock:
            if not log_buffer:
                continue
            to_flush = log_buffer.copy()
            log_buffer.clear()

        payload = []
        for exec_id, messages in to_flush.items():
            if not messages:
                continue
            payload.append({"exec_id": exec_id, "message": "".join(messages)})

        if payload:
            # 1 retry com backoff curto; na falha final os logs daquela janela sao
            # perdidos no websocket, mas estarao salvos no banco (por isso WARN).
            for attempt in range(2):
                try:
                    requests.post(
                        f"{API_BASE}/api/broadcast_logs",
                        json={"logs": payload},
                        headers=_api_headers(),
                        timeout=2,
                    )
                    break
                except requests.RequestException as exc:
                    if attempt == 0:
                        shutdown_event.wait(0.5)
                        continue
                    logger.warning(
                        "Falha ao enviar lote de logs ao WebSocket (%d execucoes); "
                        "logs preservados no banco. Erro: %s",
                        len(payload),
                        exc,
                    )


def broadcast_event(event_type: str, data: Dict[str, Any]) -> None:
    """Envia evento de sistema para o WebSocket global."""
    try:
        requests.post(
            f"{API_BASE}/api/broadcast_event",
            json={"type": event_type, "data": data},
            headers=_api_headers(),
            timeout=2,
        )
    except requests.RequestException:
        pass


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _force_kill(pid: int) -> None:
    """Encerra a arvore de processos via taskkill, com timeout para nao travar a thread."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        logger.warning("taskkill excedeu o timeout para PID %s", pid)


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


def _start_process(db_exec: Any, script_path: str, exec_id: str) -> subprocess.Popen:
    """Inicia o PowerShell e registra o processo ativo para shutdown seguro."""
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
        env=env,
    )
    with cast(threading.Lock, stats["lock"]):
        stats["active_processes"][exec_id] = process
    return process


def _drain_process_output(
    output_queue: Queue[str], logs: List[str], exec_id: str
) -> None:
    """Transfere toda a saída disponível para memória e broadcast em lote."""
    while not output_queue.empty():
        line = output_queue.get_nowait()
        logs.append(line)
        broadcast_log(line, exec_id)


def _monitor_process(
    process: subprocess.Popen,
    output_queue: Queue[str],
    logs: List[str],
    exec_id: str,
    task_start: datetime,
    task_start_ts: float,
    max_runtime: int,
) -> bool:
    """Monitora saída, interrupção e timeout; retorna True para finalização normal."""
    timeout_delta = timedelta(minutes=max_runtime)
    while not shutdown_event.is_set():
        _drain_process_output(output_queue, logs, exec_id)
        if process.poll() is not None:
            _drain_process_output(output_queue, logs, exec_id)
            return True

        with session_scope(SessionLocal) as check_db:
            db_status: Any = (
                check_db.query(models.Execution.status)
                .filter(models.Execution.id == exec_id)
                .scalar()
            )
            if db_status == EXECUTION_STATUS_TERMINATED:
                _force_kill(process.pid)
                broadcast_log("\n[INTERROMPIDO PELO USUARIO]\n", exec_id)
                finalize_terminated_task(check_db, exec_id, logs, task_start_ts)
                broadcast_event("TASK_STOPPED", {"exec_id": exec_id})
                return False

            if (get_now_local() - task_start) > timeout_delta:
                _force_kill(process.pid)
                broadcast_log(f"\n[TIMEOUT AUTOMÁTICO: {max_runtime}min]\n", exec_id)
                db_exec_upd = apply_timeout_result(
                    check_db, exec_id, logs, task_start_ts
                )
                if db_exec_upd:
                    auto = (
                        check_db.query(models.Automation)
                        .filter(models.Automation.id == db_exec_upd.automation_id)
                        .first()
                    )
                    if auto:
                        notifications.dispatch_alerts(auto, db_exec_upd)
                update_stat("tasks_failed", 1)
                broadcast_event("TASK_TIMEOUT", {"exec_id": exec_id})
                return False
        time.sleep(1)
    return False


def _finalize_execution(
    db: Any,
    process: subprocess.Popen,
    exec_id: str,
    robot_dir: str,
    logs: List[str],
    task_start_ts: float,
) -> None:
    """Persiste resultado, artefatos, alertas e evento final da execução."""
    broadcast_log(f"\n[Fim da Execução - ExitCode: {process.returncode}]\n", exec_id)
    duration = round(time.time() - task_start_ts, 2)
    artifacts_json = scan_for_artifacts(robot_dir, task_start_ts)
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if db_exec and db_exec.status not in [
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
    ]:
        db_exec = complete_process_execution(
            db,
            exec_id,
            process.returncode,
            logs,
            artifacts_json,
            duration,
        )
        if db_exec and db_exec.status in EXECUTION_DELIVERED_STATUSES:
            update_stat("tasks_completed", 1)
        else:
            update_stat("tasks_failed", 1)

        if db_exec and db_exec.status == EXECUTION_STATUS_ERROR:
            auto = (
                db.query(models.Automation)
                .filter(models.Automation.id == db_exec.automation_id)
                .first()
            )
            if auto:
                notifications.dispatch_alerts(auto, db_exec)

        if db_exec:
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
        extra={"correlation_id": exec_id},
    )


def run_task(exec_id: str, script_path: str, max_runtime: int = 30) -> None:
    """Orquestra as fases de início, monitoramento e finalização da tarefa."""
    update_stat("active_tasks", 1)
    task_start_ts = time.time()
    log_extra: Dict[str, str] = {"correlation_id": exec_id}
    try:
        with session_scope(SessionLocal) as db:
            db_exec = (
                db.query(models.Execution)
                .filter(models.Execution.id == exec_id)
                .first()
            )
            if not db_exec:
                return
            logger.info(
                "Iniciando tarefa %s -> %s (Timeout: %dmin)",
                exec_id,
                script_path,
                max_runtime,
                extra=log_extra,
            )
            if db_exec.status == EXECUTION_STATUS_PENDING:
                db_exec.status = EXECUTION_STATUS_RUNNING
                db_exec.started_at = get_now_local()
                db_exec.claimed_at = db_exec.started_at
                db_exec.worker_instance_id = WORKER_INSTANCE_ID
                db_exec.worker_pid = os.getpid()
                db.commit()
            elif db_exec.status != EXECUTION_STATUS_RUNNING:
                logger.warning(
                    "Tarefa %s ignorada: status atual=%s",
                    exec_id,
                    db_exec.status,
                    extra=log_extra,
                )
                return

            broadcast_event(
                "TASK_STARTED",
                {"exec_id": exec_id, "automation_id": db_exec.automation_id},
            )
            process = _start_process(db_exec, script_path, exec_id)
            output_queue: Queue[str] = Queue()
            reader_thread = threading.Thread(
                target=enqueue_output, args=(process.stdout, output_queue), daemon=True
            )
            reader_thread.start()
            logs: List[str] = []
            should_finalize = _monitor_process(
                process,
                output_queue,
                logs,
                exec_id,
                get_now_local(),
                task_start_ts,
                max_runtime,
            )
            if should_finalize:
                _finalize_execution(
                    db,
                    process,
                    exec_id,
                    os.path.dirname(script_path),
                    logs,
                    task_start_ts,
                )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Erro fatal na tarefa %s: %s", exec_id, exc, extra=log_extra)
        with session_scope(SessionLocal) as error_db:
            apply_internal_worker_error(error_db, exec_id, str(exc), task_start_ts)
        update_stat("tasks_failed", 1)
        broadcast_event("TASK_FAILED", {"exec_id": exec_id, "error": str(exc)})
    finally:
        with cast(threading.Lock, stats["lock"]):
            stats["active_tasks"] = max(0, stats["active_tasks"] - 1)
            stats["active_processes"].pop(exec_id, None)


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

    flusher_thread: threading.Thread = threading.Thread(
        target=log_flusher_loop, daemon=True
    )
    flusher_thread.start()

    # Inicia listener de wakeup (v6.2.0)
    wk_thread: threading.Thread = threading.Thread(
        target=wakeup_listener_loop, daemon=True
    )
    wk_thread.start()

    executor: ThreadPoolExecutor = ThreadPoolExecutor(
        max_workers=MAX_WORKERS, thread_name_prefix="task"
    )

    current_poll_interval = POLL_INTERVAL
    active_futures: set[Any] = set()

    while not shutdown_event.is_set():
        active_futures = {future for future in active_futures if not future.done()}

        if len(active_futures) >= MAX_WORKERS:
            wakeup_event.wait(POLL_INTERVAL)
            wakeup_event.clear()
            continue

        try:
            with session_scope(SessionLocal) as db:
                exec_id = claim_next_task(
                    db,
                    worker_instance_id=WORKER_INSTANCE_ID,
                    worker_pid=os.getpid(),
                )

                if exec_id:
                    current_poll_interval = POLL_INTERVAL  # Reset do polling
                    wakeup_event.clear()  # Limpa sinal caso tenha sido wakeup

                    claimed_task = (
                        db.query(models.Execution)
                        .filter(models.Execution.id == exec_id)
                        .first()
                    )
                    if not claimed_task:
                        continue

                    automation = (
                        db.query(models.Automation)
                        .filter(models.Automation.id == claimed_task.automation_id)
                        .first()
                    )

                    if automation:
                        script_path: str = resolve_script_path(
                            project_root, automation.script_path
                        )
                        max_rt: int = automation.max_runtime_minutes or 30

                        future = executor.submit(run_task, exec_id, script_path, max_rt)
                        active_futures.add(future)
                        logger.info(
                            "Tarefa despachada para pool: %s (%s)",
                            automation.name,
                            exec_id,
                        )
                    else:
                        mark_task_as_failed(
                            db,
                            exec_id,
                            "\nAutomacao nao encontrada no banco.",
                        )
                else:
                    current_poll_interval = min(
                        current_poll_interval * 1.5, MAX_POLL_INTERVAL
                    )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Erro no loop do worker: %s", e)

        # Espera pelo intervalo OU pelo sinal de wakeup (v6.2.0)
        interrupted = wakeup_event.wait(current_poll_interval)
        if interrupted:
            logger.info("Worker acordado por sinal de wakeup.")
            wakeup_event.clear()

    logger.info("Shutdown solicitado. Encerrando tarefas ativas...")

    # Pillar G: Terminacao forcada de processos filhos para evitar orfaos
    with cast(threading.Lock, stats["lock"]):
        for eid, proc in stats["active_processes"].items():
            logger.warning("Terminando processo %s (Shutdown)", eid)
            try:
                _force_kill(proc.pid)
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
