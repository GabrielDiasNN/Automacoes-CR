"""
Worker Central de Automacoes v1.0.0 - Motor de Execucao Concorrente com Tipagem Estrita e Log Batching.
"""

import contextlib
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
from concurrent.futures import Future, ThreadPoolExecutor, wait as futures_wait
from datetime import datetime, timedelta
from queue import Empty, Queue
from types import FrameType
from typing import Any, cast

import requests
from dotenv import load_dotenv

# Garantir que o pacote 'app' seja localizavel
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app import models, notifications
    from app.constants import (
        EXECUTION_DELIVERED_STATUSES,
        EXECUTION_STATUS_ERROR,
        EXECUTION_STATUS_PENDING,
        EXECUTION_STATUS_RUNNING,
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
        WORKER_VERSION,
    )
    from app.database import SessionLocal, session_scope
    from app.logger_setup import setup_json_logger as _setup_json_logger
    from app.runtime import get_project_root
    from app.security import sanitize_log_payload
    from app.subprocess_env import ALLOWED_ENV_KEYS, build_subprocess_env

    # isort: off
    from app.services.execution_runtime import (
        apply_internal_worker_error,
        apply_timeout_result,
        complete_process_execution,
        finalize_reboot_interrupted_task,
        finalize_terminated_task,
        mark_task_as_failed,
        resolve_script_path,
    )
    from app.services.execution_runtime import (  # pylint: disable=useless-import-alias
        claim_next_task as claim_next_task,
    )
    from app.services.execution_runtime import (  # pylint: disable=useless-import-alias,unused-import
        classify_process_result as classify_process_result,
    )

    # isort: on
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
SHUTDOWN_GRACE_SECONDS: float = 30.0  # espera máxima por tarefas ativas no shutdown
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
LOG_FILENAME = "Worker_test.jsonl" if is_pytest else "Worker.jsonl"


logger: logging.Logger = _setup_json_logger(
    "worker",
    os.path.join(log_dir, LOG_FILENAME),
    component="worker",
    use_context_vars=False,
    configure_root=True,
)

# ---------------------------------------------------------------------------
# Estado Global
# ---------------------------------------------------------------------------

# Sentinela de parada gracioso. No Windows, `Stop-Process -Force` é
# `TerminateProcess`: NÃO entrega sinal, então todo o caminho de encerramento
# controlado do worker (handler de SIGINT/SIGTERM, `shutdown_event`,
# `_terminate_active_processes`, `SHUTDOWN_GRACE_SECONDS`,
# `finalize_reboot_interrupted_task`) era inalcançável pelo caminho canônico de
# restart/recover. Na prática: os `powershell.exe` filhos ficavam órfãos
# rodando contra Oracle/WhatsApp sem supervisor, e a execução permanecia RUNNING
# até o `_cleanup_zombie_tasks` do boot seguinte. O arquivo dá aos scripts de
# Infrastructure um jeito de PEDIR a parada antes de forçá-la.
SHUTDOWN_SENTINEL_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "worker.shutdown"
)


def _graceful_stop_requested() -> bool:
    return os.path.exists(SHUTDOWN_SENTINEL_PATH)


def _clear_shutdown_sentinel() -> None:
    with contextlib.suppress(OSError):
        if os.path.exists(SHUTDOWN_SENTINEL_PATH):
            os.remove(SHUTDOWN_SENTINEL_PATH)


shutdown_event: threading.Event = threading.Event()
wakeup_event: threading.Event = threading.Event()  # Novo: Evento de Wakeup (v6.2.0)
start_time: float = time.time()
stats: dict[str, Any] = {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "active_tasks": 0,
    "pool_saturated_seconds": 0.0,
    "lock": threading.Lock(),
    "active_processes": {},  # {exec_id: Popen_object}
}


def update_stat(key: str, delta: int = 1) -> None:
    """Atualiza estatistica global de forma thread-safe."""
    with cast(threading.Lock, stats["lock"]):
        stats[key] += delta


def set_pool_saturation(seconds: float) -> None:
    """Atualiza o tempo continuo (streak atual) em que o pool ficou 100% ocupado."""
    with cast(threading.Lock, stats["lock"]):
        stats["pool_saturated_seconds"] = seconds


def _track_pool_saturation(
    saturated: bool, saturation_started_at: float | None
) -> float | None:
    """Atualiza o streak de saturacao do pool e reporta o valor atual ao heartbeat."""
    if saturated:
        started_at = (
            saturation_started_at if saturation_started_at is not None else time.time()
        )
        set_pool_saturation(time.time() - started_at)
        return started_at
    if saturation_started_at is not None:
        set_pool_saturation(0.0)
    return None


# ---------------------------------------------------------------------------
# Wakeup Listener (Instant Wakeup)
# ---------------------------------------------------------------------------


def _api_headers() -> dict[str, str]:
    """Headers de autenticacao para chamadas internas a API do Orchestrator."""
    api_key = os.environ.get("ORCHESTRATOR_API_KEY")
    return {"X-API-Key": api_key} if api_key else {}


def wakeup_listener_loop() -> None:
    """Escuta o sinal de wakeup do Orchestrator via Long-Polling com backoff exponencial (A5/2.2)."""
    logger.info("Wakeup listener iniciado (Zero-Latency Mode).")
    headers = _api_headers()
    backoff = 5
    max_backoff = 60

    while not shutdown_event.is_set():
        try:
            res = requests.get(
                f"{API_BASE}/api/system/wait-for-task",
                headers=headers,
                timeout=35,
            )
            if res.status_code != 200:
                # Sem espera aqui o loop vira hot-loop: 403 (API Key ausente/errada)
                # e 429 (rate limit) respondem de imediato, ao contrário do 200 que
                # só volta após o long-poll de 30s. O flood resultante ainda esgota
                # o bucket de rate limit do IP de loopback, derrubando junto o
                # Dashboard servido no mesmo host.
                logger.warning(
                    "wait-for-task respondeu HTTP %d; aguardando %ds antes de reenviar.",
                    res.status_code,
                    backoff,
                )
                shutdown_event.wait(backoff)
                backoff = min(backoff * 2, max_backoff)
                continue
            if res.json().get("status") == "wakeup":
                logger.info("Sinal de wakeup recebido!")
                wakeup_event.set()
            backoff = 5  # reset em sucesso
        except requests.RequestException:
            # Falha de rede esperada (API offline/reiniciando)
            shutdown_event.wait(backoff)
            backoff = min(backoff * 2, max_backoff)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Erro inesperado no wakeup listener: %s", exc)
            shutdown_event.wait(backoff)
            backoff = min(backoff * 2, max_backoff)


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
        pool_saturated_seconds: float = stats["pool_saturated_seconds"]

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
            pool_saturated_seconds=pool_saturated_seconds,
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
        hb.pool_saturated_seconds = round(pool_saturated_seconds, 2)

    db.commit()


# ---------------------------------------------------------------------------
# Broadcast de Logs
# ---------------------------------------------------------------------------

log_buffer: dict[str, list[str]] = {}
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
            # Sanitiza ANTES de sair do worker. O efeito era assimétrico e
            # contraintuitivo: uma senha ou DSN impressa por um script aparecia
            # mascarada no banco e no replay histórico (que lê `db_exec.logs`,
            # já higienizado em `complete_process_execution`) mas EM CLARO na
            # tela do operador em tempo real — e trafegava assim no `LOG_UPDATE`
            # de preview enviado a TODAS as conexões globais, não só a quem
            # assiste àquela execução. Aplicado uma vez por lote, e não por
            # linha, para não pagar as regex a cada uma das até 10.000 linhas.
            payload.append(
                {
                    "exec_id": exec_id,
                    "message": sanitize_log_payload("".join(messages)),
                }
            )

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


def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Envia evento de sistema para o WebSocket global."""
    with contextlib.suppress(requests.RequestException):
        requests.post(
            f"{API_BASE}/api/broadcast_event",
            json={"type": event_type, "data": data},
            headers=_api_headers(),
            timeout=2,
        )


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


_ARTIFACT_PATTERNS: list[str] = ["*.xlsx", "*.html", "*.pdf", "*.csv"]


def snapshot_artifact_files(robot_dir: str) -> set[str]:
    """Nomes dos arquivos de artefato já presentes na pasta antes da execução."""
    return {
        os.path.basename(fp)
        for pattern in _ARTIFACT_PATTERNS
        for fp in glob.glob(os.path.join(robot_dir, pattern))
    }


def scan_for_artifacts(
    robot_dir: str, start_time_ts: float, pre_existing: set[str] | None = None
) -> str | None:
    """Arquivos gerados durante esta execução.

    Um arquivo conta como novo se (a) não existia na pasta no início — detecção
    por nome, robusta a ajuste de relógio (NTP) durante a execução — ou (b) tem
    `mtime` posterior ao início (arquivo pré-existente sobrescrito no run). Antes
    só a regra (b) valia, com `start_time_ts` no relógio de parede: um passo do
    relógio para trás durante o run fazia o artefato recém-criado ter `mtime`
    menor que o início, sumir da lista e ficar indisponível para download, com a
    execução marcada SUCCESS (achado de baixa severidade).
    """
    # Sem snapshot (chamada legada / teste): comportamento puro por mtime.
    use_snapshot = pre_existing is not None
    known = pre_existing or set()
    found: list[str] = []
    for pattern in _ARTIFACT_PATTERNS:
        for fp in glob.glob(os.path.join(robot_dir, pattern)):
            name = os.path.basename(fp)
            if name in found:
                continue
            is_new_by_name = use_snapshot and name not in known
            if is_new_by_name or os.path.getmtime(fp) >= start_time_ts:
                found.append(name)
    return json.dumps(found) if found else None


# ---------------------------------------------------------------------------
# Execucao de Tarefa
# ---------------------------------------------------------------------------


# A allowlist vive em app/subprocess_env.py desde 31/07/2026 — era local a este
# módulo e os demais criadores de subprocesso (alertas, limpeza, refresh do
# Beneficiamento) herdavam `os.environ` inteiro por não terem acesso a ela.
_ALLOWED_ENV_KEYS = ALLOWED_ENV_KEYS


def _build_subprocess_env(db_exec: Any, exec_id: str) -> dict[str, str]:
    """Ambiente mínimo para subprocesso — exclui secrets sensíveis (D3/1.5)."""
    return build_subprocess_env(
        {
            "ORCHESTRATOR_TEST_MODE": (
                "true" if db_exec.automation.test_mode else "false"
            ),
            "EXEC_ID": exec_id,
            "CORRELATION_ID": exec_id,  # propaga correlation_id (E1)
        }
    )


def _start_process(
    db_exec: Any, script_path: str, exec_id: str
) -> "subprocess.Popen[str]":
    """Inicia o PowerShell e registra o processo ativo para shutdown seguro."""
    env = _build_subprocess_env(db_exec, exec_id)
    process = subprocess.Popen(  # pylint: disable=consider-using-with
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


MAX_LOG_LINES = 10_000  # ~10 MB para linhas de 1KB
MAX_LOG_CHARS = 5_000_000  # 5 MB hard cap por execução (HF-3/A1)


def _drain_process_output(
    output_queue: Queue[str],
    logs: list[str],
    exec_id: str,
    total_chars: int | None = None,
) -> int:
    """Transfere saída disponível para memória com cap de tamanho (HF-3/A1).

    Retorna o total de caracteres acumulado em ``logs``. O chamador do loop de
    monitoramento repassa esse valor na chamada seguinte: recalcular o total com
    ``sum()`` a cada tick custa O(nº de linhas) uma vez por segundo, o que em
    execuções longas (até MAX_LOG_LINES) vira trabalho quadrático inútil.
    Omitir o argumento preserva o comportamento antigo (recalcula do zero).
    """
    if total_chars is None:
        total_chars = sum(len(line) for line in logs)
    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
        except Empty:
            break
        broadcast_log(line, exec_id)
        if len(logs) >= MAX_LOG_LINES or total_chars >= MAX_LOG_CHARS:
            # Cap atingido: continua transmitindo ao WS mas não acumula em memória
            continue
        logs.append(line)
        total_chars += len(line)
    return total_chars


_DB_CHECK_INTERVAL = 5.0  # verifica banco a cada 5s em vez de 1s (A4/2.1)
_READER_JOIN_TIMEOUT = 5.0  # espera máxima pelo reader thread drenar stdout (EOF)


def _drain_final_output(
    reader_thread: "threading.Thread | None",
    output_queue: Queue[str],
    logs: list[str],
    exec_id: str,
    total_chars: int | None = None,
) -> int:
    """Aguarda o reader thread esvaziar stdout (EOF) e captura a saída final.

    O join com timeout evita perder a última rajada de saída no fim do processo
    (o reader pode ter linhas em trânsito quando process.poll() já retornou), sem
    pendurar o worker caso um subprocesso-neto herde o handle e impeça o EOF —
    achado #20 (e mitigação defensiva do #37).
    """
    if reader_thread is not None:
        reader_thread.join(timeout=_READER_JOIN_TIMEOUT)
    return _drain_process_output(output_queue, logs, exec_id, total_chars)


def _monitor_process(  # pylint: disable=too-many-locals
    process: "subprocess.Popen[str]",
    output_queue: Queue[str],
    logs: list[str],
    task_ctx: dict[str, Any],
) -> bool:
    """Monitora saída, interrupção e timeout; retorna True para finalização normal."""
    exec_id: str = task_ctx["exec_id"]
    # `task_start` (wall-clock) permanece no task_ctx para exibição, mas o corte
    # por max_runtime usa exclusivamente o relógio monotônico — ver abaixo.
    task_start_monotonic: float = task_ctx["task_start_monotonic"]
    max_runtime: int = task_ctx["max_runtime"]
    timeout_delta = timedelta(minutes=max_runtime)
    last_db_check = 0.0

    reader_thread = task_ctx.get("reader_thread")
    # Acumulador de tamanho carregado entre os ticks (ver _drain_process_output).
    total_chars = 0
    while not shutdown_event.is_set():
        total_chars = _drain_process_output(output_queue, logs, exec_id, total_chars)
        if process.poll() is not None:
            _drain_final_output(reader_thread, output_queue, logs, exec_id, total_chars)
            return True

        now_ts = time.time()
        if (now_ts - last_db_check) >= _DB_CHECK_INTERVAL:
            last_db_check = now_ts
            with session_scope(SessionLocal) as check_db:
                db_status: Any = (
                    check_db.query(models.Execution.status)
                    .filter(models.Execution.id == exec_id)
                    .scalar()
                )
                if db_status == EXECUTION_STATUS_TERMINATED:
                    _force_kill(process.pid)
                    broadcast_log("\n[INTERROMPIDO PELO USUARIO]\n", exec_id)
                    finalize_terminated_task(
                        check_db, exec_id, logs, task_start_monotonic
                    )
                    broadcast_event("TASK_STOPPED", {"exec_id": exec_id})
                    return False

                # Relógio MONOTÔNICO, não wall-clock. Até 31/07/2026 a
                # comparação era `get_now_local() - task_start`, ambos datetimes
                # de relógio de parede: um acerto de NTP para trás adiava o
                # timeout pelo mesmo delta (processo travado seguia vivo,
                # segurando um slot e bloqueando o queue_group), e um acerto
                # para a frente derrubava execução saudável, gravando TIMEOUT
                # com `duration_seconds` MENOR que o max_runtime declarado — um
                # estado internamente contraditório. Todo o resto da medição
                # desta execução já usava `task_start_monotonic`.
                if (
                    time.monotonic() - task_start_monotonic
                ) > timeout_delta.total_seconds():
                    _force_kill(process.pid)
                    broadcast_log(
                        f"\n[TIMEOUT AUTOMÁTICO: {max_runtime}min]\n", exec_id
                    )
                    db_exec_upd = apply_timeout_result(
                        check_db, exec_id, logs, task_start_monotonic
                    )
                    if db_exec_upd:
                        auto = (
                            check_db.query(models.Automation)
                            .filter(models.Automation.id == db_exec_upd.automation_id)
                            .first()
                        )
                        if auto:
                            notifications.dispatch_alerts_async(auto, db_exec_upd)
                    update_stat("tasks_failed", 1)
                    broadcast_event("TASK_TIMEOUT", {"exec_id": exec_id})
                    return False

        time.sleep(1)

    # Loop encerrado por shutdown_event (graceful shutdown do worker).
    if process.poll() is not None:
        # Processo concluiu dentro da janela do shutdown: preserva o resultado
        # real via finalização normal em vez de descartá-lo.
        _drain_final_output(reader_thread, output_queue, logs, exec_id, total_chars)
        return True
    # Processo ainda vivo: encerra e finaliza como interrupção por reboot, para
    # não deixar a execução presa em RUNNING até o recovery do próximo boot.
    _force_kill(process.pid)
    _drain_final_output(reader_thread, output_queue, logs, exec_id, total_chars)
    broadcast_log("\n[INTERROMPIDO POR SHUTDOWN DO ORQUESTRADOR]\n", exec_id)
    with session_scope(SessionLocal) as shutdown_db:
        finalize_reboot_interrupted_task(
            shutdown_db, exec_id, logs, task_start_monotonic
        )
    broadcast_event("TASK_FAILED_BY_REBOOT", {"exec_id": exec_id})
    return False


def _finalize_execution(
    db: Any,
    process: "subprocess.Popen[str]",
    logs: list[str],
    task_ctx: dict[str, Any],
) -> None:
    """Persiste resultado, artefatos, alertas e evento final da execução."""
    exec_id: str = task_ctx["exec_id"]
    robot_dir: str = task_ctx["robot_dir"]
    task_start_ts: float = task_ctx["task_start_ts"]
    task_start_monotonic: float = task_ctx["task_start_monotonic"]
    pre_existing_artifacts: set[str] = task_ctx.get("pre_existing_artifacts", set())
    broadcast_log(f"\n[Fim da Execução - ExitCode: {process.returncode}]\n", exec_id)
    duration = round(time.monotonic() - task_start_monotonic, 2)
    artifacts_json = scan_for_artifacts(
        robot_dir, task_start_ts, pre_existing_artifacts
    )
    db_exec = db.query(models.Execution).filter(models.Execution.id == exec_id).first()
    if db_exec and db_exec.status not in [
        EXECUTION_STATUS_TERMINATED,
        EXECUTION_STATUS_TIMEOUT,
    ]:
        db_exec = complete_process_execution(
            db,
            exec_id,
            return_code=process.returncode,
            logs=logs,
            artifacts_json=artifacts_json,
            duration_seconds=duration,
        )
        if db_exec and db_exec.status in EXECUTION_DELIVERED_STATUSES:
            update_stat("tasks_completed", 1)
            # Zera o contador de falhas CONSECUTIVAS do throttle de alertas.
            # `reset_alert_state` existia com a docstring "chamar em execucao
            # bem-sucedida" e não tinha nenhum chamador em produção — só um
            # teste. `_mark_sent` incrementava monotonicamente durante toda a
            # vida do processo, então após 5 falhas acumuladas (podendo estar
            # meses separadas) a automação ficava permanentemente no tier de
            # 60 s, e a métrica "falhas consecutivas" do log de supressão era,
            # na verdade, "falhas desde o boot da API".
            notifications.reset_alert_state(int(db_exec.automation_id))
        else:
            update_stat("tasks_failed", 1)

        if db_exec and db_exec.status == EXECUTION_STATUS_ERROR:
            auto = (
                db.query(models.Automation)
                .filter(models.Automation.id == db_exec.automation_id)
                .first()
            )
            if auto:
                notifications.dispatch_alerts_async(auto, db_exec)

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


def run_task(  # pylint: disable=too-many-locals
    exec_id: str, script_path: str, max_runtime: int = 30
) -> None:
    """Orquestra as fases de início, monitoramento e finalização da tarefa.

    A sessão do banco é aberta em duas janelas curtas — início e finalização —
    e fica FECHADA durante o monitoramento. Antes uma única sessão cobria a
    execução inteira: até `max_runtime` minutos (30 por padrão) segurando uma
    conexão do pool à toa, com um identity map que envelhecia enquanto
    `_monitor_process` abria sessões próprias e alterava as mesmas linhas por
    fora — de onde vinha o risco de ler estado obsoleto na finalização.
    """
    update_stat("active_tasks", 1)
    task_start_ts = time.time()
    task_start_monotonic = time.monotonic()
    robot_dir = os.path.dirname(script_path)
    # Snapshot ANTES de spawnar o processo: qualquer arquivo de artefato que
    # apareça depois é novo, mesmo que o relógio ande para trás no meio do run.
    pre_existing_artifacts = snapshot_artifact_files(robot_dir)
    log_extra: dict[str, str] = {"correlation_id": exec_id}
    try:
        # Fase 1 — janela curta: valida o status, reivindica e inicia o processo.
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
                db_exec.status = EXECUTION_STATUS_RUNNING  # type: ignore[assignment]
                db_exec.started_at = get_now_local()  # type: ignore[assignment]
                db_exec.claimed_at = db_exec.started_at
                db_exec.worker_instance_id = WORKER_INSTANCE_ID  # type: ignore[assignment]
                db_exec.worker_pid = os.getpid()  # type: ignore[assignment]
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
            # Dentro da janela porque _build_subprocess_env lê
            # db_exec.automation.test_mode (carga lazy do relacionamento).
            process = _start_process(db_exec, script_path, exec_id)

        output_queue: Queue[str] = Queue()
        reader_thread = threading.Thread(
            target=enqueue_output, args=(process.stdout, output_queue), daemon=True
        )
        reader_thread.start()
        logs: list[str] = []
        task_ctx: dict[str, Any] = {
            "exec_id": exec_id,
            "task_start": get_now_local(),
            "task_start_ts": task_start_ts,
            "task_start_monotonic": task_start_monotonic,
            "max_runtime": max_runtime,
            "robot_dir": robot_dir,
            "pre_existing_artifacts": pre_existing_artifacts,
            "reader_thread": reader_thread,
        }
        # Fase 2 — monitoramento sem sessão aberta. _monitor_process abre as
        # suas próprias janelas curtas a cada _DB_CHECK_INTERVAL.
        should_finalize = _monitor_process(
            process,
            output_queue,
            logs,
            task_ctx,
        )
        # Fase 3 — janela curta para persistir o resultado.
        if should_finalize:
            with session_scope(SessionLocal) as final_db:
                _finalize_execution(
                    final_db,
                    process,
                    logs,
                    task_ctx,
                )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Erro fatal na tarefa %s: %s", exec_id, exc, extra=log_extra)
        with session_scope(SessionLocal) as error_db:
            apply_internal_worker_error(
                error_db, exec_id, str(exc), task_start_monotonic
            )
        update_stat("tasks_failed", 1)
        broadcast_event("TASK_FAILED", {"exec_id": exec_id, "error": str(exc)})
    finally:
        with cast(threading.Lock, stats["lock"]):
            stats["active_tasks"] = max(0, stats["active_tasks"] - 1)
            orfao = stats["active_processes"].pop(exec_id, None)
        # Se o processo ainda está vivo quando saímos daqui, ele ficou ÓRFÃO:
        # foi removido de `active_processes` (logo o `_terminate_active_processes`
        # do shutdown já não o enxerga) e nenhum monitor o supervisiona. Isso
        # acontecia quando uma exceção ocorria depois do `_start_process` — por
        # exemplo um `OperationalError` do SQLite dentro de `_monitor_process`,
        # que abre sessão a cada 5 s. O banco registrava INTERNAL_WORKER_ERROR
        # enquanto o PowerShell seguia rodando e podendo enviar e-mail/WhatsApp;
        # o operador via a falha, reenfileirava, e a entrega duplicava.
        if orfao is not None and orfao.poll() is None:
            logger.error(
                "Processo da tarefa %s continuava vivo apos o encerramento do "
                "monitor; encerrando para nao deixar orfao sem supervisao.",
                exec_id,
                extra=log_extra,
            )
            with contextlib.suppress(Exception):
                _force_kill(orfao.pid)


# ---------------------------------------------------------------------------
# Loop Principal
# ---------------------------------------------------------------------------


def _terminate_active_processes() -> None:
    """Encerra forçadamente todos os processos filhos registrados (Pillar G)."""
    # Copia a lista sob o lock e o libera antes de chamar _force_kill (bloqueante,
    # até 15s por processo via taskkill). Manter o lock global durante os kills
    # trava heartbeat/stats por até N×15s no shutdown (achado #19).
    with cast(threading.Lock, stats["lock"]):
        snapshot = list(stats["active_processes"].items())
    for eid, proc in snapshot:
        logger.warning("Terminando processo %s (Shutdown)", eid)
        try:
            _force_kill(proc.pid)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Falha ao encerrar processo %s: %s", eid, e)


def main_loop() -> None:  # pylint: disable=too-many-locals,too-many-statements
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
    active_futures: set[Future[None]] = set()
    saturation_started_at: float | None = None

    while not shutdown_event.is_set():
        if _graceful_stop_requested():
            logger.info(
                "Sentinela de parada encontrado (%s). Iniciando shutdown gracioso.",
                SHUTDOWN_SENTINEL_PATH,
            )
            shutdown_event.set()
            break

        active_futures = {future for future in active_futures if not future.done()}

        if len(active_futures) >= MAX_WORKERS:
            saturation_started_at = _track_pool_saturation(True, saturation_started_at)
            wakeup_event.wait(POLL_INTERVAL)
            wakeup_event.clear()
            continue

        saturation_started_at = _track_pool_saturation(False, saturation_started_at)

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
                            project_root, str(automation.script_path)
                        )
                        max_rt: int = int(automation.max_runtime_minutes or 30)

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
        if wakeup_event.wait(current_poll_interval):
            logger.info("Worker acordado por sinal de wakeup.")
            wakeup_event.clear()

    logger.info("Shutdown solicitado. Encerrando tarefas ativas...")
    _terminate_active_processes()
    # Deadline defensivo: aguarda as tarefas ativas encerrarem por até
    # SHUTDOWN_GRACE_SECONDS (após o force-kill, o run_task desenrola rápido).
    # Sem o timeout, uma thread presa em I/O que não reavalia shutdown_event
    # penduraria o worker indefinidamente em executor.shutdown(wait=True) (#21).
    if active_futures:
        _, not_done = futures_wait(active_futures, timeout=SHUTDOWN_GRACE_SECONDS)
        if not_done:
            logger.warning(
                "%d tarefa(s) não encerraram em %ss; abandonando no shutdown.",
                len(not_done),
                SHUTDOWN_GRACE_SECONDS,
            )
    executor.shutdown(wait=False, cancel_futures=True)
    # O pool de notificações também precisa ser encerrado explicitamente: suas
    # threads não são daemon e o `atexit` do concurrent.futures faria join delas
    # DEPOIS deste ponto, furando o deadline de SHUTDOWN_GRACE_SECONDS que todo
    # o bloco acima existe para garantir.
    notifications.shutdown_notification_executor()
    # Remove o sentinela para não bloquear o próximo start.
    _clear_shutdown_sentinel()
    logger.info("Worker encerrado de forma controlada.")


# ---------------------------------------------------------------------------
# Signal Handlers
# ---------------------------------------------------------------------------


def _signal_handler(
    signum: int, frame: FrameType | None  # pylint: disable=unused-argument
) -> None:
    logger.info("Sinal recebido: %d. Iniciando graceful shutdown...", signum)
    shutdown_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    main_loop()
