# pylint: disable=protected-access
"""Testes unitários de worker._monitor_process (timeout, término, shutdown, intervalo de DB)."""

import time
from datetime import datetime, timedelta
from queue import Queue
from typing import Any
from unittest.mock import MagicMock, patch

import time_machine
import worker
from app import models
from app.constants import (
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_TERMINATED,
    EXECUTION_STATUS_TIMEOUT,
)
from app.timezone import get_now_local


def _seed_running_execution(db_session: Any, exec_id: str) -> Any:
    auto = models.Automation(name=f"Monitor {exec_id}", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    execucao = models.Execution(
        id=exec_id,
        automation_id=auto.id,
        status=EXECUTION_STATUS_RUNNING,
        requested_by="TEST",
        started_at=get_now_local(),
        logs="",
    )
    db_session.add(execucao)
    db_session.commit()
    return execucao


def _task_ctx(exec_id: str, task_start: Any, max_runtime: int = 30) -> dict[str, Any]:
    """Contexto de tarefa com os DOIS relógios coerentes entre si.

    Desde 31/07/2026 o corte por `max_runtime` usa `time.monotonic()`, não o
    relógio de parede (um acerto de NTP para trás adiava o timeout
    indefinidamente). Os testes expressam "a tarefa começou há N minutos"
    recuando `task_start`; o monotônico precisa acompanhar o mesmo offset, senão
    o timeout nunca dispara e `_monitor_process` roda para sempre.
    """
    decorrido = (get_now_local() - task_start).total_seconds() if task_start else 0.0
    return {
        "exec_id": exec_id,
        "task_start": task_start,
        "task_start_ts": time.time() - decorrido,
        "task_start_monotonic": time.monotonic() - decorrido,
        "max_runtime": max_runtime,
        "robot_dir": "C:\\robot",
    }


@time_machine.travel(datetime(2026, 7, 3, 10, 0, 0), tick=False)
def test_monitor_detecta_timeout_via_mock_de_tempo(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_running_execution(db_session, "EXEC_TIMEOUT_MON")
    process = MagicMock()
    process.pid = 4321
    process.poll.return_value = None
    task_ctx = _task_ctx(
        "EXEC_TIMEOUT_MON", get_now_local() - timedelta(minutes=31), max_runtime=30
    )

    with (
        patch("worker._force_kill") as mock_force_kill,
        patch("worker.broadcast_log"),
        patch("worker.broadcast_event"),
        patch("worker.notifications.dispatch_alerts_async"),
    ):
        resultado = worker._monitor_process(process, Queue(), [], task_ctx)

    assert resultado is False
    mock_force_kill.assert_called_once_with(4321)


@time_machine.travel(datetime(2026, 7, 3, 10, 0, 0), tick=False)
def test_monitor_seta_status_timeout_no_banco(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_running_execution(db_session, "EXEC_TIMEOUT_DB")
    process = MagicMock()
    process.pid = 1
    process.poll.return_value = None
    task_ctx = _task_ctx(
        "EXEC_TIMEOUT_DB", get_now_local() - timedelta(minutes=31), max_runtime=30
    )

    with (
        patch("worker._force_kill"),
        patch("worker.broadcast_log"),
        patch("worker.broadcast_event"),
        patch("worker.notifications.dispatch_alerts_async"),
    ):
        worker._monitor_process(process, Queue(), [], task_ctx)

    execucao = (
        db_session.query(models.Execution).filter_by(id="EXEC_TIMEOUT_DB").first()
    )
    assert execucao.status == EXECUTION_STATUS_TIMEOUT
    assert execucao.failure_reason == "MAX_RUNTIME_EXCEEDED"


def test_monitor_detecta_terminacao_pelo_usuario(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    execucao = _seed_running_execution(db_session, "EXEC_USER_STOP")
    execucao.status = EXECUTION_STATUS_TERMINATED
    db_session.commit()

    process = MagicMock()
    process.pid = 55
    process.poll.return_value = None
    task_ctx = _task_ctx("EXEC_USER_STOP", get_now_local(), max_runtime=30)

    with (
        patch("worker._force_kill") as mock_force_kill,
        patch("worker.broadcast_log"),
        patch("worker.broadcast_event") as mock_broadcast_event,
    ):
        resultado = worker._monitor_process(process, Queue(), [], task_ctx)

    assert resultado is False
    mock_force_kill.assert_called_once_with(55)
    mock_broadcast_event.assert_called_once_with(
        "TASK_STOPPED", {"exec_id": "EXEC_USER_STOP"}
    )


def test_monitor_chama_finalize_terminated_task(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    execucao = _seed_running_execution(db_session, "EXEC_FINALIZE_TERM")
    execucao.status = EXECUTION_STATUS_TERMINATED
    db_session.commit()

    process = MagicMock()
    process.pid = 77
    process.poll.return_value = None
    task_ctx = _task_ctx("EXEC_FINALIZE_TERM", get_now_local(), max_runtime=30)

    with (
        patch("worker._force_kill"),
        patch("worker.broadcast_log"),
        patch("worker.broadcast_event"),
    ):
        worker._monitor_process(process, Queue(), ["log runtime"], task_ctx)

    persistido = (
        db_session.query(models.Execution).filter_by(id="EXEC_FINALIZE_TERM").first()
    )
    assert persistido.exit_code == -15
    assert "log runtime" in persistido.logs


def test_monitor_finaliza_reboot_em_shutdown_com_processo_vivo(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    # Achado #3: shutdown com processo ainda vivo deve finalizar a execução como
    # FAILED_BY_REBOOT (em vez de deixá-la presa em RUNNING) e retornar False.
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_running_execution(db_session, "EXEC_SHUTDOWN_LIVE")
    process = MagicMock()
    process.pid = 4242
    process.poll.return_value = None  # processo ainda vivo no momento do shutdown

    worker.shutdown_event.set()
    try:
        with (
            patch("worker._force_kill") as mock_force_kill,
            patch("worker.broadcast_log"),
            patch("worker.broadcast_event"),
        ):
            resultado = worker._monitor_process(
                process,
                Queue(),
                [],
                _task_ctx("EXEC_SHUTDOWN_LIVE", get_now_local()),
            )
    finally:
        worker.shutdown_event.clear()

    assert resultado is False
    mock_force_kill.assert_called_once_with(4242)
    execucao = (
        db_session.query(models.Execution).filter_by(id="EXEC_SHUTDOWN_LIVE").first()
    )
    assert execucao.status == "FAILED_BY_REBOOT"
    assert execucao.failure_reason == "ORCHESTRATOR_REBOOT"


def test_monitor_retorna_true_quando_processo_finaliza_no_shutdown(
    reset_worker_globals: None,
) -> None:
    # Se o processo concluiu na janela do shutdown, o monitor pede finalização
    # normal (return True) para não descartar o resultado real.
    del reset_worker_globals
    process = MagicMock()
    process.poll.return_value = 0

    worker.shutdown_event.set()
    try:
        with patch("worker.broadcast_log"):
            resultado = worker._monitor_process(
                process, Queue(), [], _task_ctx("EXEC_SHUTDOWN_DONE", get_now_local())
            )
    finally:
        worker.shutdown_event.clear()

    assert resultado is True


def test_monitor_db_check_interval_respeita_5s(monkeypatch: Any) -> None:
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.scalar.return_value = (
        EXECUTION_STATUS_RUNNING
    )
    monkeypatch.setattr(worker, "SessionLocal", lambda: mock_db)

    process = MagicMock()
    process.poll.side_effect = [None, None, 0]
    task_ctx = _task_ctx("EXEC_INTERVAL", get_now_local(), max_runtime=30)

    with patch("worker.broadcast_log"), patch("worker.time.sleep"):
        resultado = worker._monitor_process(process, Queue(), [], task_ctx)

    assert resultado is True
    assert mock_db.query.call_count == 1


def test_monitor_retorna_true_quando_processo_finaliza_normalmente() -> None:
    process = MagicMock()
    process.poll.return_value = 0
    task_ctx = _task_ctx("EXEC_NORMAL_END", get_now_local())

    with patch("worker.broadcast_log"):
        resultado = worker._monitor_process(process, Queue(), [], task_ctx)

    assert resultado is True
