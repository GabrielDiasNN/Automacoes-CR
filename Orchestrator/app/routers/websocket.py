# pylint: disable=all
# mypy: ignore-errors
"""
Router: WebSocket - Gerenciador de conexoes e Event Bus para logs e eventos.
Implementa Log Replay (v4.0.1) para garantir continuidade de visualizacao.
"""

import asyncio
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..middleware import get_api_key
from ..models import Execution
from ..schemas import format_dt_br
from ..timezone import get_now_local

logger = logging.getLogger("orchestrator")

router = APIRouter(tags=["WebSocket"])

# ---------------------------------------------------------------------------
# Connection Manager (Event Bus)
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Gerencia conexoes WebSocket para broadcast de logs e eventos."""

    def __init__(self):
        self.exec_connections: Dict[str, List[WebSocket]] = {}
        self.global_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect_exec(self, websocket: WebSocket, exec_id: str):
        """Conecta um cliente para receber logs de uma execucao."""
        await websocket.accept()
        async with self._lock:
            if exec_id not in self.exec_connections:
                self.exec_connections[exec_id] = []
            self.exec_connections[exec_id].append(websocket)
        logger.info(f"WebSocket conectado para exec_id: {exec_id}")

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.global_connections.append(websocket)
        logger.info(
            f"WebSocket global conectado. Total: {len(self.global_connections)}"
        )

    async def disconnect_exec(self, websocket: WebSocket, exec_id: str):
        async with self._lock:
            if exec_id in self.exec_connections:
                if websocket in self.exec_connections[exec_id]:
                    self.exec_connections[exec_id].remove(websocket)
                if not self.exec_connections[exec_id]:
                    del self.exec_connections[exec_id]

    async def disconnect_global(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.global_connections:
                self.global_connections.remove(websocket)

    async def broadcast_log(self, message: str, exec_id: str):
        # Pilar E: Limitar tamanho da mensagem individual para evitar OOM em logs massivos
        if len(message) > 50000:
            message = message[:50000] + "\n... [TRUNCATED FOR WS PERFORMANCE]"

        async with self._lock:
            targets = list(self.exec_connections.get(exec_id, []))

        dead = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            for ws in dead:
                await self.disconnect_exec(ws, exec_id)

    async def broadcast_event(self, event_type: str, data: dict):
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
            except Exception:
                dead.append(ws)
        if dead:
            for ws in dead:
                await self.disconnect_global(ws)


manager = ConnectionManager()

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
    return bool(api_key) and hmac.compare_digest(api_key, expected_key)


async def _send_log_replay(websocket: WebSocket, exec_id: str) -> None:
    """LOG REPLAY: envia o historico de logs persistido ao cliente recem-conectado."""
    db = SessionLocal()
    try:
        db_exec = db.query(Execution).filter(Execution.id == exec_id).first()
        if db_exec and db_exec.logs:
            await websocket.send_text(db_exec.logs)
            await websocket.send_text("\n--- Historico recuperado ---\n")
    except Exception as e:
        logger.warning(f"Falha ao recuperar replay de logs para {exec_id}: {e}")
    finally:
        db.close()


@router.websocket("/ws/logs/{exec_id}")
async def websocket_exec_logs(websocket: WebSocket, exec_id: str):
    if not _validate_ws_key(websocket):
        await websocket.close(code=4003)
        logger.warning(f"WebSocket recusado por API Key inválida para exec_id: {exec_id}")
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
async def websocket_global_events(websocket: WebSocket):
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
async def broadcast_log_endpoint(log_data: dict, api_key: str = Depends(get_api_key)):
    exec_id = log_data.get("exec_id")
    message = log_data.get("message")
    if exec_id and message:
        await manager.broadcast_log(message, exec_id)
        # Evento global simplificado
        await manager.broadcast_event(
            "LOG_UPDATE",
            {
                "exec_id": exec_id,
                "preview": message[:100] + "..." if len(message) > 100 else message,
            },
        )
    return {"status": "ok"}


@router.post("/api/broadcast_logs")
async def broadcast_logs_endpoint(logs_data: dict, api_key: str = Depends(get_api_key)):
    logs = logs_data.get("logs", [])
    grouped = {}
    for log_data in logs:
        exec_id = log_data.get("exec_id")
        message = log_data.get("message")
        if exec_id and message:
            if exec_id not in grouped:
                grouped[exec_id] = []
            grouped[exec_id].append(message)

    for exec_id, messages in grouped.items():
        combined_message = "\n".join(messages)
        await manager.broadcast_log(combined_message, exec_id)
        preview_msg = messages[-1]
        await manager.broadcast_event(
            "LOG_UPDATE",
            {
                "exec_id": exec_id,
                "preview": (
                    preview_msg[:100] + "..." if len(preview_msg) > 100 else preview_msg
                ),
            },
        )
    return {"status": "ok", "processed": len(logs)}


@router.post("/api/broadcast_event")
async def broadcast_event_endpoint(
    event_data: dict, api_key: str = Depends(get_api_key)
):
    await manager.broadcast_event(
        event_data.get("type", "UNKNOWN"), event_data.get("data", {})
    )
    return {"status": "ok"}
