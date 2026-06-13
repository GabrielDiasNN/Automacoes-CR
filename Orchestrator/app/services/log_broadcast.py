"""Serviço único de normalização e emissão de logs para WebSocket."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Protocol


class BroadcastManager(Protocol):
    """Contrato mínimo do gerenciador WebSocket consumido pelo serviço."""

    async def broadcast_log(self, message: str, exec_id: str) -> None: ...

    async def broadcast_event(self, event_type: str, data: dict[str, Any]) -> None: ...


class LogBroadcaster:  # pylint: disable=too-few-public-methods
    """Agrupa entradas e emite log mais evento de preview de forma consistente."""

    def __init__(self, manager: BroadcastManager) -> None:
        self._manager = manager

    async def emit_entries(self, entries: Iterable[dict[str, Any]]) -> int:
        """Emite entradas válidas agrupadas por execução e retorna as processadas."""
        grouped: dict[str, list[str]] = defaultdict(list)
        processed = 0
        for entry in entries:
            exec_id = entry.get("exec_id")
            message = entry.get("message")
            if exec_id and message:
                grouped[str(exec_id)].append(str(message))
                processed += 1

        for exec_id, messages in grouped.items():
            await self._manager.broadcast_log("\n".join(messages), exec_id)
            preview = messages[-1]
            await self._manager.broadcast_event(
                "LOG_UPDATE",
                {
                    "exec_id": exec_id,
                    "preview": (
                        preview[:100] + "..." if len(preview) > 100 else preview
                    ),
                },
            )
        return processed
