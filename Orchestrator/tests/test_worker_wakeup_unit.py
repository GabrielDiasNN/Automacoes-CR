"""Testes unitários de worker.wakeup_listener_loop e worker.log_flusher_loop."""

from typing import Any
from unittest.mock import MagicMock, patch

import requests
import worker


def _stop_after_call(*_args: Any, **_kwargs: Any) -> bool:
    """Side effect universal para Event.wait: encerra o loop na próxima checagem."""
    worker.shutdown_event.set()
    return False


# ---------------------------------------------------------------------------
# wakeup_listener_loop
# ---------------------------------------------------------------------------


def test_wakeup_seta_event_ao_receber_status_wakeup(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals

    def _fake_get(*_args: Any, **_kwargs: Any) -> MagicMock:
        worker.shutdown_event.set()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "wakeup"}
        return resp

    mock_requests_worker["get"].side_effect = _fake_get

    worker.wakeup_listener_loop()

    assert worker.wakeup_event.is_set() is True


def test_wakeup_nao_seta_event_em_status_idle(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals

    def _fake_get(*_args: Any, **_kwargs: Any) -> MagicMock:
        worker.shutdown_event.set()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "idle"}
        return resp

    mock_requests_worker["get"].side_effect = _fake_get

    worker.wakeup_listener_loop()

    assert worker.wakeup_event.is_set() is False


def test_wakeup_backoff_aumenta_em_falha_de_rede(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals
    mock_requests_worker["get"].side_effect = requests.RequestException("offline")

    waits: list[float] = []

    def _record_wait(timeout: float) -> bool:
        waits.append(timeout)
        if len(waits) >= 3:
            worker.shutdown_event.set()
        return False

    with patch.object(worker.shutdown_event, "wait", side_effect=_record_wait):
        worker.wakeup_listener_loop()

    assert waits == [5, 10, 20]


def test_wakeup_backoff_reseta_apos_sucesso(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals
    call_count = 0

    def _fake_get(*_args: Any, **_kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count in (1, 2, 4):
            raise requests.RequestException("offline")
        # Terceira chamada: sucesso, reseta o backoff para 5.
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "idle"}
        return resp

    mock_requests_worker["get"].side_effect = _fake_get

    waits: list[float] = []

    def _record_wait(timeout: float) -> bool:
        waits.append(timeout)
        if len(waits) >= 3:
            worker.shutdown_event.set()
        return False

    with patch.object(worker.shutdown_event, "wait", side_effect=_record_wait):
        worker.wakeup_listener_loop()

    # 5 (1a falha), 10 (2a falha), 5 (falha apos sucesso: prova que resetou)
    assert waits == [5, 10, 5]


def test_wakeup_backoff_nao_excede_max_backoff(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals
    mock_requests_worker["get"].side_effect = requests.RequestException("offline")

    waits: list[float] = []

    def _record_wait(timeout: float) -> bool:
        waits.append(timeout)
        if len(waits) >= 5:
            worker.shutdown_event.set()
        return False

    with patch.object(worker.shutdown_event, "wait", side_effect=_record_wait):
        worker.wakeup_listener_loop()

    assert waits == [5, 10, 20, 40, 60]


def test_wakeup_para_ao_shutdown_event_set(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals
    worker.shutdown_event.set()

    worker.wakeup_listener_loop()

    mock_requests_worker["get"].assert_not_called()


# ---------------------------------------------------------------------------
# log_flusher_loop
# ---------------------------------------------------------------------------


def test_log_flusher_envia_lote_em_batch(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals
    worker.log_buffer["EXEC-BATCH"] = ["linha 1\n", "linha 2\n"]

    with patch.object(worker.shutdown_event, "wait", side_effect=_stop_after_call):
        worker.log_flusher_loop()

    mock_requests_worker["post"].assert_called_once()
    _, kwargs = mock_requests_worker["post"].call_args
    assert kwargs["json"]["logs"] == [
        {"exec_id": "EXEC-BATCH", "message": "linha 1\nlinha 2\n"}
    ]


def test_log_flusher_retry_unico_em_falha_de_rede(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals
    worker.log_buffer["EXEC-RETRY"] = ["linha\n"]
    mock_requests_worker["post"].side_effect = requests.RequestException("offline")

    with patch.object(worker.shutdown_event, "wait", side_effect=_stop_after_call):
        worker.log_flusher_loop()

    assert mock_requests_worker["post"].call_count == 2


def test_log_flusher_loga_warning_apos_2_falhas(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals
    worker.log_buffer["EXEC-WARN"] = ["linha\n"]
    mock_requests_worker["post"].side_effect = requests.RequestException("offline")

    with (
        patch.object(worker.shutdown_event, "wait", side_effect=_stop_after_call),
        patch("worker.logger.warning") as mock_warning,
    ):
        worker.log_flusher_loop()

    mock_warning.assert_called_once()


def test_log_flusher_nao_envia_buffer_vazio(
    mock_requests_worker: dict[str, MagicMock], reset_worker_globals: None
) -> None:
    del reset_worker_globals

    with patch.object(worker.shutdown_event, "wait", side_effect=_stop_after_call):
        worker.log_flusher_loop()

    mock_requests_worker["post"].assert_not_called()
