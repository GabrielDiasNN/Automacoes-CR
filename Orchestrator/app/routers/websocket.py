"""
Router: WebSocket - Gerenciador de conexoes e Event Bus para logs e eventos.
Implementa Log Replay (v4.0.1) para garantir continuidade de visualizacao.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..database import SessionLocal, session_scope
from ..middleware import get_api_key
from ..models import Execution
from ..schemas import format_dt_br
from ..services.log_broadcast import LogBroadcaster
from ..timezone import get_now_local

logger = logging.getLogger("orchestrator")

router = APIRouter(tags=["WebSocket"])

# ---------------------------------------------------------------------------
# Connection Manager (Event Bus)
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Gerencia conexoes WebSocket para broadcast de logs e eventos."""

    def __init__(self) -> None:
        self.exec_connections: dict[str, list[WebSocket]] = {}
        self.global_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect_exec(self, websocket: WebSocket, exec_id: str) -> None:
        """Conecta um cliente para receber logs de uma execucao."""
        await websocket.accept()
        async with self._lock:
            if exec_id not in self.exec_connections:
                self.exec_connections[exec_id] = []
            self.exec_connections[exec_id].append(websocket)
        logger.info("WebSocket conectado para exec_id: %s", exec_id)

    async def connect_global(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.global_connections.append(websocket)
        logger.info(
            "WebSocket global conectado. Total: %s", len(self.global_connections)
        )

    async def disconnect_exec(self, websocket: WebSocket, exec_id: str) -> None:
        async with self._lock:
            if exec_id in self.exec_connections:
                if websocket in self.exec_connections[exec_id]:
                    self.exec_connections[exec_id].remove(websocket)
                if not self.exec_connections[exec_id]:
                    del self.exec_connections[exec_id]

    async def disconnect_global(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.global_connections:
                self.global_connections.remove(websocket)

    async def broadcast_log(self, message: str, exec_id: str) -> None:
        # Pilar E: Limitar tamanho da mensagem individual para evitar OOM em logs massivos
        if len(message) > 50000:
            message = message[:50000] + "\n... [TRUNCATED FOR WS PERFORMANCE]"

        async with self._lock:
            targets = list(self.exec_connections.get(exec_id, []))

        dead = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:  # pylint: disable=broad-exception-caught
                dead.append(ws)
        if dead:
            for ws in dead:
                await self.disconnect_exec(ws, exec_id)

    async def broadcast_event(self, event_type: str, data: dict[str, Any]) -> None:
        payload = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": format_dt_br(get_now_local()),
            }
        )
        async with self._lock:
            targets = list(self.global_connections)

        dead = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:  # pylint: disable=broad-exception-caught
                dead.append(ws)
        if dead:
            for ws in dead:
                await self.disconnect_global(ws)


manager = ConnectionManager()
log_broadcaster = LogBroadcaster(manager)

# ---------------------------------------------------------------------------
# ENDPOINTS WEBSOCKET
# ---------------------------------------------------------------------------


def _validate_ws_key(websocket: WebSocket) -> bool:
    """Valida a API Key do WebSocket (query param) com comparacao timing-safe."""
    api_key = websocket.query_params.get("key")
    expected_key = os.environ.get("ORCHESTRATOR_API_KEY")
    if not expected_key:
        # Fail-closed: sem key configurada, nenhuma conexao e aceita.
        logger.error(
            "ORCHESTRATOR_API_KEY ausente no ambiente — conexoes WebSocket recusadas."
        )
        return False
    if not api_key:
        return False
    return hmac.compare_digest(api_key, expected_key)


async def _send_log_replay(websocket: WebSocket, exec_id: str) -> None:
    """LOG REPLAY: envia o historico de logs persistido ao cliente recem-conectado."""
    try:
        with session_scope(SessionLocal) as db:
            db_exec = db.query(Execution).filter(Execution.id == exec_id).first()
            if db_exec and db_exec.logs:
                await websocket.send_text(str(db_exec.logs))
                await websocket.send_text("\n--- Historico recuperado ---\n")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Falha ao recuperar replay de logs para %s: %s", exec_id, e)


@router.websocket("/ws/logs/{exec_id}")
async def websocket_exec_logs(websocket: WebSocket, exec_id: str) -> None:
    if not _validate_ws_key(websocket):
        await websocket.close(code=4003)
        logger.warning(
            "WebSocket recusado por API Key inválida para exec_id: %s", exec_id
        )
        return

    await manager.connect_exec(websocket, exec_id)
    await _send_log_replay(websocket, exec_id)
    try:
        while True:
            # Manter conexao aberta e lidar com pings se necessario
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_exec(websocket, exec_id)


@router.websocket("/ws/events")
async def websocket_global_events(websocket: WebSocket) -> None:
    if not _validate_ws_key(websocket):
        await websocket.close(code=4003)
        logger.warning("WebSocket global recusado por API Key inválida.")
        return

    await manager.connect_global(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_global(websocket)


# ---------------------------------------------------------------------------
# ENDPOINT HTTP para broadcast interno (usado pelo Worker)
# ---------------------------------------------------------------------------


@router.post("/api/broadcast_log")
async def broadcast_log_endpoint(log_data: dict[str, Any], _api_key: str = Depends(get_api_key)) -> dict[str, Any]:
    await log_broadcaster.emit_entries([log_data])
    return {"status": "ok"}


@router.post("/api/broadcast_logs")
async def broadcast_logs_endpoint(logs_data: dict[str, Any], _api_key: str = Depends(get_api_key)) -> dict[str, Any]:
    logs = logs_data.get("logs", [])
    processed = await log_broadcaster.emit_entries(logs)
    return {"status": "ok", "processed": processed}


@router.post("/api/broadcast_event")
async def broadcast_event_endpoint(
    event_data: dict[str, Any], _api_key: str = Depends(get_api_key)
) -> dict[str, Any]:
    await manager.broadcast_event(
        event_data.get("type", "UNKNOWN"), event_data.get("data", {})
    )
    return {"status": "ok"}
