"""Testes do serviço único de broadcast de logs."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

from app.services.log_broadcast import LogBroadcaster


def test_log_broadcaster_groups_entries_and_emits_last_preview() -> None:
    """Executa em loop isolado para coexistir com a sessão Playwright completa."""
    manager = AsyncMock()
    broadcaster = LogBroadcaster(manager)

    entries = [
        {"exec_id": "E1", "message": "linha 1"},
        {"exec_id": "E1", "message": "linha 2"},
        {"exec_id": "E2", "message": "outra"},
        {"exec_id": "", "message": "ignorada"},
    ]
    with ThreadPoolExecutor(max_workers=1) as executor:
        processed = executor.submit(
            asyncio.run, broadcaster.emit_entries(entries)
        ).result()

    assert processed == 3
    manager.broadcast_log.assert_any_await("linha 1\nlinha 2", "E1")
    manager.broadcast_log.assert_any_await("outra", "E2")
    manager.broadcast_event.assert_any_await(
        "LOG_UPDATE", {"exec_id": "E1", "preview": "linha 2"}
    )
