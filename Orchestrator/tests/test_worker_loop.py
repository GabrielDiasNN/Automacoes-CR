"""
Testes unitários focados no loop principal e comportamento de backoff do Worker (worker.py).
"""

from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest
import worker


@pytest.fixture
def reset_worker_state() -> Iterator[None]:
    """Garante que o estado de shutdown e wakeup do worker seja limpo."""
    worker.shutdown_event.clear()
    worker.wakeup_event.clear()
    yield
    worker.shutdown_event.clear()
    worker.wakeup_event.clear()


@patch("worker.SessionLocal")
@patch("worker.claim_next_task")
@patch("worker.heartbeat_loop")
@patch("worker.log_flusher_loop")
@patch("worker.wakeup_listener_loop")
@patch("worker.POLL_INTERVAL", 2.0)
@patch("worker.MAX_POLL_INTERVAL", 15.0)
def test_worker_backoff_exponential(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mock_wakeup_listener: Any,  # pylint: disable=unused-argument
    mock_flusher: Any,  # pylint: disable=unused-argument
    mock_heartbeat: Any,  # pylint: disable=unused-argument
    mock_claim: Any,
    mock_session_local: Any,
    reset_worker_state: None,  # pylint: disable=unused-argument,redefined-outer-name
) -> None:
    """Garante que o intervalo de polling do worker cresce exponencialmente (backoff) quando não há tarefas."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    # Mock do claim_next_task retornando sempre None (sem tarefas pendentes)
    mock_claim.return_value = None

    # Queremos rodar o loop exatamente 3 vezes e depois parar para auditar o backoff.
    call_count = 0

    def side_effect_wait(timeout: float) -> bool:
        nonlocal call_count
        call_count += 1

        # Na primeira iteração: interval = 2.0 * 1.5 = 3.0
        if call_count == 1:
            assert timeout == 3.0
        # Na segunda iteração: interval = 3.0 * 1.5 = 4.5
        elif call_count == 2:
            assert timeout == 4.5
        # Na terceira iteração: interval = 4.5 * 1.5 = 6.75
        elif call_count == 3:
            assert timeout == 6.75
            worker.shutdown_event.set()  # Solicita encerramento para sair do loop

        return False

    with patch.object(worker.wakeup_event, "wait", side_effect_wait):
        worker.main_loop()

    assert call_count == 3
    assert mock_claim.call_count == 3


@patch("worker.SessionLocal")
@patch("worker.claim_next_task")
@patch("worker.run_task")
@patch("worker.resolve_script_path")
@patch("worker.heartbeat_loop")
@patch("worker.log_flusher_loop")
@patch("worker.wakeup_listener_loop")
@patch("worker.POLL_INTERVAL", 2.0)
def test_worker_consumes_task_and_resets_backoff(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    mock_wakeup_listener: Any,  # pylint: disable=unused-argument
    mock_flusher: Any,  # pylint: disable=unused-argument
    mock_heartbeat: Any,  # pylint: disable=unused-argument
    mock_resolve_path: Any,
    mock_run_task: Any,  # pylint: disable=unused-argument
    mock_claim: Any,
    mock_session_local: Any,
    reset_worker_state: None,  # pylint: disable=unused-argument,redefined-outer-name
) -> None:
    """Garante que quando uma tarefa é encontrada, o backoff de polling é resetado para o valor inicial."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db

    # Mock das entidades no banco
    class MockAutomation:  # pylint: disable=too-few-public-methods
        name = "Robo Teste"
        script_path = "./run.ps1"
        max_runtime_minutes = 10

    class MockExecution:  # pylint: disable=too-few-public-methods
        automation_id = 1

    mock_automation = MockAutomation()
    mock_exec = MockExecution()

    # Simula o banco retornando a execução e a automação
    mock_db.query().filter().first.side_effect = [mock_exec, mock_automation]
    mock_resolve_path.return_value = "C:\\Automacoes\\test\\run.ps1"

    # Primeiro claim retorna None (backoff inicializado), depois retorna uma task
    mock_claim.side_effect = [None, "EXEC-101"]

    call_count = 0

    def side_effect_wait(timeout: float) -> bool:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # Primeiro claim retornou None. backoff = 2.0 * 1.5 = 3.0
            assert timeout == 3.0
        elif call_count == 2:
            # Segundo claim retornou EXEC-101. backoff deve ter sido resetado para POLL_INTERVAL = 2.0
            assert timeout == 2.0
            worker.shutdown_event.set()

        return False

    with patch.object(worker.wakeup_event, "wait", side_effect_wait):
        with patch("worker.ThreadPoolExecutor"):
            # Mock do executor para rodar de forma síncrona/mockada
            worker.main_loop()

    assert call_count == 2
    assert mock_claim.call_count == 2
