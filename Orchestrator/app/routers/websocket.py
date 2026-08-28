"""
Router: WebSocket - Gerenciador de conexoes e Event Bus para logs e eventos.
Implementa Log Replay (v4.0.1) para garantir continuidade de visualizacao.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from .. import schemas
from ..database import SessionLocal, session_scope
from ..middleware import get_api_key
from ..schemas import format_dt_br
from ..services import execution_repository as exec_repo, ws_auth
from ..services.log_broadcast import LogBroadcaster
from ..timezone import get_now_local

logger = logging.getLogger("orchestrator")

router = APIRouter(tags=["WebSocket"])

# Pilar E: teto por mensagem WS, para não estourar memória do cliente com logs
# massivos. Aplicado tanto no broadcast ao vivo quanto no replay histórico (#40).
WS_MAX_MESSAGE_CHARS = 50_000
_WS_TRUNCATION_SUFFIX = "\n... [TRUNCATED FOR WS PERFORMANCE]"


def truncate_ws_message(message: str) -> str:
    """Trunca uma mensagem que exceda o teto de transmissão do WebSocket."""
    if len(message) <= WS_MAX_MESSAGE_CHARS:
        return message
    return message[:WS_MAX_MESSAGE_CHARS] + _WS_TRUNCATION_SUFFIX


# ---------------------------------------------------------------------------
# Connection Manager (Event Bus)
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Gerencia conexoes WebSocket para broadcast de logs e eventos."""

    def __init__(self) -> None:
        self.exec_connections: dict[str, list[WebSocket]] = {}
        self.global_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        # Um lock de escrita por conexão serializa send_text: o contrato ASGI
        # exige escritor único, e dois broadcasts concorrentes para o mesmo
        # exec_id escreveriam no mesmo socket simultaneamente (achado #28).
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}

    async def register_exec(self, websocket: WebSocket, exec_id: str) -> None:
        """Registra (sem accept) uma conexão para logs de uma execução.

        Separado de connect_exec para que o endpoint envie o replay histórico
        ANTES de registrar a conexão para broadcast ao vivo, evitando que uma
        linha ao vivo chegue antes do histórico (inversão cronológica, #27).
        """
        async with self._lock:
            if exec_id not in self.exec_connections:
                self.exec_connections[exec_id] = []
            self.exec_connections[exec_id].append(websocket)
            self._send_locks[websocket] = asyncio.Lock()
        logger.info("WebSocket conectado para exec_id: %s", exec_id)

    async def connect_exec(self, websocket: WebSocket, exec_id: str) -> None:
        """Aceita e registra um cliente para receber logs de uma execucao."""
        await websocket.accept()
        await self.register_exec(websocket, exec_id)

    async def connect_global(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.global_connections.append(websocket)
            self._send_locks[websocket] = asyncio.Lock()
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
            self._send_locks.pop(websocket, None)

    async def disconnect_global(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.global_connections:
                self.global_connections.remove(websocket)
            self._send_locks.pop(websocket, None)

    async def _safe_send(self, websocket: WebSocket, message: str) -> None:
        """Envia serializando por conexão (escritor único do contrato ASGI)."""
        lock = self._send_locks.get(websocket)
        if lock is None:
            # Conexão já desregistrada: envia sem lock (best-effort).
            await websocket.send_text(message)
            return
        async with lock:
            await websocket.send_text(message)

    async def broadcast_log(self, message: str, exec_id: str) -> None:
        # Pilar E: Limitar tamanho da mensagem individual para evitar OOM em logs massivos
        message = truncate_ws_message(message)

        async with self._lock:
            targets = list(self.exec_connections.get(exec_id, []))

        dead = []
        for ws in targets:
            try:
                await self._safe_send(ws, message)
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
                await self._safe_send(ws, payload)
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
    """Valida o handshake WebSocket por token efêmero de uso único (#41).

    Antes a API Key mestra viajava no ``?key=`` — o browser não permite header no
    handshake WS, então a credencial fica exposta na URL (logs de acesso de
    proxy/servidor). Agora o cliente troca a API Key por um token de uso único e
    vida curta em ``POST /api/system/ws-token`` e apresenta só ele aqui.

    Fail-closed: sem token válido, nenhuma conexão é aceita.
    """
    token = websocket.query_params.get("token")
    if not token:
        return False
    return ws_auth.consume_ws_token(token)


def _fetch_execution_logs(exec_id: str) -> str | None:
    with session_scope(SessionLocal) as db:
        db_exec = exec_repo.get_by_id(db, exec_id)
        return str(db_exec.logs) if db_exec and db_exec.logs else None


async def _send_log_replay(websocket: WebSocket, exec_id: str) -> None:
    """LOG REPLAY: envia o historico de logs persistido ao cliente recem-conectado."""
    try:
        # Handlers WebSocket são sempre async (exigência do Starlette, sem o
        # despacho automático ao threadpool que rotas HTTP `def` ganham) — a
        # consulta síncrona ao SQLite roda em thread separada para não travar
        # o event loop único do Uvicorn a cada nova conexão de log.
        logs = await run_in_threadpool(_fetch_execution_logs, exec_id)
        if logs:
            # Mesmo teto do broadcast ao vivo: o histórico acumulado pode ser
            # muito maior que uma linha individual (#40).
            await websocket.send_text(truncate_ws_message(logs))
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

    await websocket.accept()
    try:
        # #27: envia o histórico ANTES de registrar para broadcast ao vivo, para
        # não intercalar uma linha ao vivo antes do replay (inversão cronológica).
        await _send_log_replay(websocket, exec_id)
        await manager.register_exec(websocket, exec_id)
        while True:
            # Manter conexao aberta e lidar com pings se necessario
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # finally garante remoção da conexao mesmo em frame binário/erro não
        # previsto (receive_text lança fora de WebSocketDisconnect), evitando
        # vazamento permanente de referência em exec_connections.
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
        pass
    finally:
        # Ver nota em websocket_exec_logs: disconnect sempre no finally.
        await manager.disconnect_global(websocket)


# ---------------------------------------------------------------------------
# ENDPOINT HTTP para broadcast interno (usado pelo Worker)
# ---------------------------------------------------------------------------


@router.post("/api/broadcast_log")
async def broadcast_log_endpoint(
    log_data: schemas.WsLogEntry, _api_key: str = Depends(get_api_key)
) -> dict[str, Any]:
    await log_broadcaster.emit_entries([log_data.model_dump()])
    return {"status": "ok"}


@router.post("/api/broadcast_logs")
async def broadcast_logs_endpoint(
    logs_data: schemas.WsLogBatch, _api_key: str = Depends(get_api_key)
) -> dict[str, Any]:
    processed = await log_broadcaster.emit_entries(
        entry.model_dump() for entry in logs_data.logs
    )
    return {"status": "ok", "processed": processed}


@router.post("/api/broadcast_event")
async def broadcast_event_endpoint(
    event_data: schemas.WsEventPayload, _api_key: str = Depends(get_api_key)
) -> dict[str, Any]:
    await manager.broadcast_event(event_data.type, event_data.data)
    return {"status": "ok"}
