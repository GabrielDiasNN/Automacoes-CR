# pylint: disable=all
# mypy: ignore-errors
"""
Router: WebSocket - Gerenciador de conexoes e Event Bus para logs e eventos.
Implementa Log Replay (v4.0.1) para garantir continuidade de visualizacao.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..models import Execution
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

    async def connect_exec(self, websocket: WebSocket, exec_id: str):
        """Conecta um cliente para receber logs de uma execucao."""
        await websocket.accept()

        # --- LOG REPLAY (Fase 2) ---
        db = SessionLocal()
        try:
            db_exec = db.query(Execution).filter(Execution.id == exec_id).first()
            if db_exec and db_exec.logs:
                # Enviar logs existentes imediatamente apos conexao
                await websocket.send_text(db_exec.logs)
                await websocket.send_text("\n--- Historico recuperado ---\n")
        except Exception as e:
            logger.warning(f"Falha ao recuperar replay de logs para {exec_id}: {e}")
        finally:
            db.close()

        if exec_id not in self.exec_connections:
            self.exec_connections[exec_id] = []
        self.exec_connections[exec_id].append(websocket)
        logger.info(f"WebSocket conectado para exec_id: {exec_id} (Replay OK)")

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        self.global_connections.append(websocket)
        logger.info(
            f"WebSocket global conectado. Total: {len(self.global_connections)}"
        )

    def disconnect_exec(self, websocket: WebSocket, exec_id: str):
        if exec_id in self.exec_connections:
            if websocket in self.exec_connections[exec_id]:
                self.exec_connections[exec_id].remove(websocket)
            if not self.exec_connections[exec_id]:
                del self.exec_connections[exec_id]

    def disconnect_global(self, websocket: WebSocket):
        if websocket in self.global_connections:
            self.global_connections.remove(websocket)

    async def broadcast_log(self, message: str, exec_id: str):
        if exec_id in self.exec_connections:
            # Pilar E: Limitar tamanho da mensagem individual para evitar OOM em logs massivos
            if len(message) > 50000:
                message = message[:50000] + "\n... [TRUNCATED FOR WS PERFORMANCE]"

            dead = []
            for ws in self.exec_connections[exec_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect_exec(ws, exec_id)

    async def broadcast_event(self, event_type: str, data: dict):
        payload = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": get_now_local().isoformat(),
            }
        )
        dead = []
        for ws in self.global_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_global(ws)

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# ENDPOINTS WEBSOCKET
# ---------------------------------------------------------------------------

@router.websocket("/ws/logs/{exec_id}")
async def websocket_exec_logs(websocket: WebSocket, exec_id: str):
    await manager.connect_exec(websocket, exec_id)
    try:
        while True:
            # Manter conexao aberta e lidar com pings se necessario
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_exec(websocket, exec_id)

@router.websocket("/ws/events")
async def websocket_global_events(websocket: WebSocket):
    await manager.connect_global(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_global(websocket)

# ---------------------------------------------------------------------------
# ENDPOINT HTTP para broadcast interno (usado pelo Worker)
# ---------------------------------------------------------------------------

@router.post("/api/broadcast_log")
async def broadcast_log_endpoint(log_data: dict):
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

@router.post("/api/broadcast_event")
async def broadcast_event_endpoint(event_data: dict):
    await manager.broadcast_event(
        event_data.get("type", "UNKNOWN"), event_data.get("data", {})
    )
    return {"status": "ok"}
