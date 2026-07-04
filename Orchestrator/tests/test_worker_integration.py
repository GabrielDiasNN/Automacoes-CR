# pylint: disable=protected-access
"""Testes de integração de worker.run_task e worker.main_loop (fluxo mockado)."""

import os
from typing import Any
from unittest.mock import MagicMock, patch

import worker
from app import models
from app.constants import (
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
)
from app.timezone import get_now_local


def _seed_execution(db_session: Any, exec_id: str, status: str) -> tuple[Any, Any]:
    auto = models.Automation(name=f"Auto {exec_id}", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    execucao = models.Execution(
        id=exec_id,
        automation_id=auto.id,
        status=status,
        requested_by="TEST",
        started_at=get_now_local(),
    )
    db_session.add(execucao)
    db_session.commit()
    return auto, execucao


# ---------------------------------------------------------------------------
# run_task
# ---------------------------------------------------------------------------


def test_run_task_execucao_nao_encontrada_nao_inicia_processo(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)

    with patch("worker._start_process") as mock_start:
        worker.run_task("EXEC_INEXISTENTE", "C:\\script.ps1")

    mock_start.assert_not_called()


def test_run_task_status_terminal_nao_inicia_processo(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_execution(db_session, "EXEC_ERROR_STATE", EXECUTION_STATUS_ERROR)

    with patch("worker._start_process") as mock_start:
        worker.run_task("EXEC_ERROR_STATE", "C:\\script.ps1")

    mock_start.assert_not_called()


def test_run_task_pending_transiciona_para_running_e_inicia_processo(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_execution(db_session, "EXEC_PENDING", EXECUTION_STATUS_PENDING)

    fake_process = MagicMock()
    fake_process.stdout.readline.return_value = ""
    with (
        patch("worker._start_process", return_value=fake_process) as mock_start,
        patch("worker._monitor_process", return_value=False),
        patch("worker.broadcast_event"),
    ):
        worker.run_task("EXEC_PENDING", "C:\\script.ps1", max_runtime=10)

    mock_start.assert_called_once()
    execucao = db_session.query(models.Execution).filter_by(id="EXEC_PENDING").first()
    assert execucao.status == EXECUTION_STATUS_RUNNING
    assert execucao.worker_pid == os.getpid()


def test_run_task_chamada_duas_vezes_para_mesmo_exec_id_inicia_dois_processos(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    """Documenta o comportamento atual: o guard de status só bloqueia execuções
    fora de PENDING/RUNNING. Se run_task for reinvocado para um exec_id que já
    está RUNNING (reentrada), ele NÃO é bloqueado e inicia um novo processo.
    Em operação normal isso não ocorre porque claim_next_task usa um UPDATE
    atômico (WHERE status=PENDING), mas run_task por si só não tem esse guard."""
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_execution(db_session, "EXEC_DUPLA", EXECUTION_STATUS_PENDING)

    fake_process = MagicMock()
    fake_process.stdout.readline.return_value = ""
    with (
        patch("worker._start_process", return_value=fake_process) as mock_start,
        patch("worker._monitor_process", return_value=False),
        patch("worker.broadcast_event"),
    ):
        worker.run_task("EXEC_DUPLA", "C:\\script.ps1")
        worker.run_task("EXEC_DUPLA", "C:\\script.ps1")

    assert mock_start.call_count == 2


def test_run_task_excecao_aplica_internal_worker_error(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_execution(db_session, "EXEC_BOOM", EXECUTION_STATUS_PENDING)

    with (
        patch("worker._start_process", side_effect=RuntimeError("boom")),
        patch("worker.broadcast_event"),
    ):
        worker.run_task("EXEC_BOOM", "C:\\script.ps1")

    execucao = db_session.query(models.Execution).filter_by(id="EXEC_BOOM").first()
    assert execucao.status == EXECUTION_STATUS_ERROR
    assert "Internal Worker Error" in execucao.logs
    assert worker.stats["tasks_failed"] == 1


def test_run_task_decrementa_active_tasks_no_finally(
    db_session: Any, monkeypatch: Any, reset_worker_globals: None
) -> None:
    del reset_worker_globals
    monkeypatch.setattr(worker, "SessionLocal", lambda: db_session)
    _seed_execution(db_session, "EXEC_FINALLY", EXECUTION_STATUS_PENDING)

    with (
        patch("worker._start_process", side_effect=RuntimeError("boom")),
        patch("worker.broadcast_event"),
    ):
        worker.run_task("EXEC_FINALLY", "C:\\script.ps1")

    assert worker.stats["active_tasks"] == 0
    assert "EXEC_FINALLY" not in worker.stats["active_processes"]


# ---------------------------------------------------------------------------
# main_loop
# ---------------------------------------------------------------------------


@patch("worker.SessionLocal")
@patch("worker.claim_next_task")
@patch("worker.mark_task_as_failed")
@patch("worker.heartbeat_loop")
@patch("worker.log_flusher_loop")
@patch("worker.wakeup_listener_loop")
def test_main_loop_automacao_nao_encontrada_marca_falha(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mock_wakeup_listener: Any,
    mock_flusher: Any,
    mock_heartbeat: Any,
    mock_mark_failed: Any,
    mock_claim: Any,
    mock_session_local: Any,
    reset_worker_globals: None,
) -> None:
    del reset_worker_globals, mock_wakeup_listener, mock_flusher, mock_heartbeat
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_claim.return_value = "EXEC_ORFAO"

    class MockExecution:  # pylint: disable=too-few-public-methods
        automation_id = 999

    mock_db.query().filter().first.side_effect = [MockExecution(), None]

    def side_effect_wait(_timeout: float) -> bool:
        worker.shutdown_event.set()
        return False

    with patch.object(worker.wakeup_event, "wait", side_effect=side_effect_wait):
        worker.main_loop()

    mock_mark_failed.assert_called_once()


@patch("worker.MAX_WORKERS", 1)
@patch("worker.SessionLocal")
@patch("worker.claim_next_task")
@patch("worker.resolve_script_path")
@patch("worker.heartbeat_loop")
@patch("worker.log_flusher_loop")
@patch("worker.wakeup_listener_loop")
def test_main_loop_max_workers_atingido_nao_consulta_banco_de_novo(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mock_wakeup_listener: Any,
    mock_flusher: Any,
    mock_heartbeat: Any,
    mock_resolve_path: Any,
    mock_claim: Any,
    mock_session_local: Any,
    reset_worker_globals: None,
) -> None:
    del reset_worker_globals, mock_wakeup_listener, mock_flusher, mock_heartbeat
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    class MockAutomation:  # pylint: disable=too-few-public-methods
        name = "Robo Cheio"
        script_path = "./run.ps1"
        max_runtime_minutes = 10

    class MockExecution:  # pylint: disable=too-few-public-methods
        automation_id = 1

    mock_db.query().filter().first.side_effect = [MockExecution(), MockAutomation()]
    mock_resolve_path.return_value = "C:\\run.ps1"
    mock_claim.return_value = "EXEC_PRIMEIRA"

    fake_future = MagicMock()
    fake_future.done.return_value = False

    call_count = 0

    def side_effect_wait(_timeout: float) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            worker.shutdown_event.set()
        return False

    with patch("worker.ThreadPoolExecutor") as mock_executor_cls:
        mock_executor = MagicMock()
        mock_executor.submit.return_value = fake_future
        mock_executor_cls.return_value = mock_executor

        with patch.object(worker.wakeup_event, "wait", side_effect=side_effect_wait):
            worker.main_loop()

    # 1a iteracao despacha EXEC_PRIMEIRA (claim chamado 1x); com MAX_WORKERS=1
    # e o future ainda nao concluido, a 2a iteracao nao deve consultar o banco.
    assert mock_claim.call_count == 1
