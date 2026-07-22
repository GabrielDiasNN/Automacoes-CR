"""Testes unitarios do ConnectionManager, _validate_ws_key e _send_log_replay.

Complementam tests/test_websocket_broadcast_auth.py (que cobre apenas os
endpoints HTTP de broadcast). Aqui o foco e a logica interna de
app/routers/websocket.py: gerenciamento de conexoes WebSocket (Event Bus),
validacao timing-safe da API Key e o replay de logs historicos.

Estrategia async: corrotinas sao executadas via _run_async(...) dentro de
uma thread isolada (ThreadPoolExecutor), o mesmo padrao ja usado em
tests/test_log_broadcast.py. O projeto tem pytest-asyncio instalado mas nao
configura asyncio_mode=auto; usar @pytest.mark.asyncio expos um
"RuntimeError: asyncio.run() cannot be called from a running event loop"
quando a suite completa roda com os testes Playwright (test_e2e_dashboard.py),
que deixam um event loop vivo na thread principal do processo de teste.
Rodar em thread propria isola cada teste desse loop vazado.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app import models
from app.routers import websocket as websocket_router
from app.routers.websocket import ConnectionManager, _send_log_replay, _validate_ws_key
from app.services import ws_auth
from fastapi import WebSocketDisconnect
from tests.conftest import AUTH_HEADERS, TEST_AUTH_VALUE

# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------


def _make_ws() -> Any:
    """Cria um mock de WebSocket com os metodos assincronos usados pelo manager."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    ws.receive_text = AsyncMock()
    return ws


def _run_async(coro: Coroutine[Any, Any, None]) -> None:
    """Executa uma corrotina em thread isolada, imune a event loop vazado."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, coro).result()


def test_connect_exec_aceita_conexao_e_registra_por_exec_id() -> None:
    manager = ConnectionManager()
    ws = _make_ws()

    _run_async(manager.connect_exec(ws, "EXEC_1"))

    ws.accept.assert_awaited_once()
    assert manager.exec_connections["EXEC_1"] == [ws]


def test_connect_exec_agrupa_multiplas_conexoes_na_mesma_execucao() -> None:
    manager = ConnectionManager()
    ws1, ws2 = _make_ws(), _make_ws()

    async def _run() -> None:
        await manager.connect_exec(ws1, "EXEC_1")
        await manager.connect_exec(ws2, "EXEC_1")

    _run_async(_run())

    assert manager.exec_connections["EXEC_1"] == [ws1, ws2]


def test_connect_global_aceita_conexao_e_acumula_lista() -> None:
    manager = ConnectionManager()
    ws1, ws2 = _make_ws(), _make_ws()

    async def _run() -> None:
        await manager.connect_global(ws1)
        await manager.connect_global(ws2)

    _run_async(_run())

    ws1.accept.assert_awaited_once()
    assert manager.global_connections == [ws1, ws2]


def test_disconnect_exec_remove_conexao_e_limpa_chave_vazia() -> None:
    manager = ConnectionManager()
    ws = _make_ws()

    async def _run() -> None:
        await manager.connect_exec(ws, "EXEC_1")
        await manager.disconnect_exec(ws, "EXEC_1")

    _run_async(_run())

    assert "EXEC_1" not in manager.exec_connections


def test_disconnect_exec_mantem_outras_conexoes_da_mesma_chave() -> None:
    manager = ConnectionManager()
    ws1, ws2 = _make_ws(), _make_ws()

    async def _run() -> None:
        await manager.connect_exec(ws1, "EXEC_1")
        await manager.connect_exec(ws2, "EXEC_1")
        await manager.disconnect_exec(ws1, "EXEC_1")

    _run_async(_run())

    assert manager.exec_connections["EXEC_1"] == [ws2]


def test_disconnect_exec_e_idempotente_para_exec_id_desconhecido() -> None:
    manager = ConnectionManager()
    ws = _make_ws()

    _run_async(manager.disconnect_exec(ws, "EXEC_INEXISTENTE"))

    assert "EXEC_INEXISTENTE" not in manager.exec_connections


def test_disconnect_global_remove_conexao() -> None:
    manager = ConnectionManager()
    ws = _make_ws()

    async def _run() -> None:
        await manager.connect_global(ws)
        await manager.disconnect_global(ws)

    _run_async(_run())

    assert ws not in manager.global_connections


def test_disconnect_global_e_idempotente() -> None:
    manager = ConnectionManager()
    ws = _make_ws()

    _run_async(manager.disconnect_global(ws))

    assert not manager.global_connections


def test_broadcast_log_envia_para_conexoes_da_execucao() -> None:
    manager = ConnectionManager()
    ws = _make_ws()

    async def _run() -> None:
        await manager.connect_exec(ws, "EXEC_1")
        await manager.broadcast_log("mensagem de log", "EXEC_1")

    _run_async(_run())

    ws.send_text.assert_awaited_once_with("mensagem de log")


def test_broadcast_log_trunca_mensagens_muito_grandes() -> None:
    manager = ConnectionManager()
    ws = _make_ws()
    mensagem_grande = "x" * 60000

    async def _run() -> None:
        await manager.connect_exec(ws, "EXEC_1")
        await manager.broadcast_log(mensagem_grande, "EXEC_1")

    _run_async(_run())

    enviado = ws.send_text.await_args.args[0]
    assert len(enviado) < len(mensagem_grande)
    assert enviado.endswith("[TRUNCATED FOR WS PERFORMANCE]")
    assert enviado.startswith("x" * 50000)


def test_broadcast_log_sem_conexoes_nao_levanta_excecao() -> None:
    manager = ConnectionManager()

    _run_async(manager.broadcast_log("mensagem", "EXEC_SEM_CONEXAO"))


def test_broadcast_log_remove_conexoes_mortas_apos_falha_no_envio() -> None:
    manager = ConnectionManager()
    ws_ok, ws_morto = _make_ws(), _make_ws()
    ws_morto.send_text = AsyncMock(side_effect=RuntimeError("conexao fechada"))

    async def _run() -> None:
        await manager.connect_exec(ws_ok, "EXEC_1")
        await manager.connect_exec(ws_morto, "EXEC_1")
        await manager.broadcast_log("mensagem", "EXEC_1")

    _run_async(_run())

    assert manager.exec_connections["EXEC_1"] == [ws_ok]


def test_broadcast_event_envia_payload_json_para_conexoes_globais() -> None:
    manager = ConnectionManager()
    ws = _make_ws()

    async def _run() -> None:
        await manager.connect_global(ws)
        await manager.broadcast_event("STATUS_CHANGE", {"foo": "bar"})

    _run_async(_run())

    enviado = ws.send_text.await_args.args[0]
    payload = json.loads(enviado)
    assert payload["type"] == "STATUS_CHANGE"
    assert payload["data"] == {"foo": "bar"}
    assert "timestamp" in payload


def test_broadcast_event_remove_conexoes_mortas_apos_falha_no_envio() -> None:
    manager = ConnectionManager()
    ws_ok, ws_morto = _make_ws(), _make_ws()
    ws_morto.send_text = AsyncMock(side_effect=RuntimeError("conexao fechada"))

    async def _run() -> None:
        await manager.connect_global(ws_ok)
        await manager.connect_global(ws_morto)
        await manager.broadcast_event("STATUS_CHANGE", {})

    _run_async(_run())

    assert manager.global_connections == [ws_ok]


def test_broadcast_event_sem_conexoes_nao_levanta_excecao() -> None:
    manager = ConnectionManager()

    _run_async(manager.broadcast_event("STATUS_CHANGE", {"foo": "bar"}))


# ---------------------------------------------------------------------------
# _validate_ws_key
# ---------------------------------------------------------------------------


def _make_ws_with_token(token: str | None) -> Any:
    ws = MagicMock()
    ws.query_params = {"token": token} if token is not None else {}
    return ws


def test_validate_ws_aceita_token_emitido() -> None:
    # Achado #41: o handshake passou a exigir token efêmero em vez da API Key
    # mestra, que ficava exposta na URL.
    ws_auth.reset_ws_tokens()
    token, _ttl = ws_auth.issue_ws_token()

    assert _validate_ws_key(_make_ws_with_token(token)) is True


def test_validate_ws_token_e_de_uso_unico() -> None:
    ws_auth.reset_ws_tokens()
    token, _ttl = ws_auth.issue_ws_token()

    assert _validate_ws_key(_make_ws_with_token(token)) is True
    # Segunda tentativa com o mesmo token deve falhar (já consumido).
    assert _validate_ws_key(_make_ws_with_token(token)) is False


def test_validate_ws_rejeita_token_desconhecido() -> None:
    ws_auth.reset_ws_tokens()
    assert _validate_ws_key(_make_ws_with_token("token-inventado")) is False


def test_validate_ws_rejeita_token_ausente() -> None:
    ws_auth.reset_ws_tokens()
    assert _validate_ws_key(_make_ws_with_token(None)) is False


def test_validate_ws_rejeita_api_key_mestra_na_query() -> None:
    # Regressão: a API Key não pode mais autenticar o handshake.
    ws_auth.reset_ws_tokens()
    ws = MagicMock()
    ws.query_params = {"key": TEST_AUTH_VALUE}

    assert _validate_ws_key(ws) is False


def test_validate_ws_rejeita_token_expirado(monkeypatch: Any) -> None:
    ws_auth.reset_ws_tokens()
    monkeypatch.setattr(ws_auth, "WS_TOKEN_TTL_SECONDS", 0)
    token, _ttl = ws_auth.issue_ws_token()

    assert _validate_ws_key(_make_ws_with_token(token)) is False


def test_ws_token_endpoint_exige_api_key(client: Any) -> None:
    assert client.post("/api/system/ws-token").status_code == 403


def test_ws_token_endpoint_emite_token_utilizavel(client: Any) -> None:
    ws_auth.reset_ws_tokens()
    res = client.post("/api/system/ws-token", headers=AUTH_HEADERS)

    assert res.status_code == 200
    body = res.json()
    assert body["expires_in_seconds"] > 0
    assert _validate_ws_key(_make_ws_with_token(body["token"])) is True


# ---------------------------------------------------------------------------
# _send_log_replay
# ---------------------------------------------------------------------------


def test_send_log_replay_envia_historico_quando_execucao_tem_logs(
    client: Any, db_session: Any
) -> None:
    del client  # garante que websocket_router.SessionLocal aponta pro engine de teste

    automacao = models.Automation(name="Replay Teste 1", script_path="./test/run.ps1")
    db_session.add(automacao)
    db_session.flush()

    execucao = models.Execution(
        id="EXEC_REPLAY_1",
        automation_id=automacao.id,
        status="RUNNING",
        logs="linha 1\nlinha 2",
    )
    db_session.add(execucao)
    db_session.commit()

    ws = _make_ws()

    _run_async(_send_log_replay(ws, "EXEC_REPLAY_1"))

    assert ws.send_text.await_count == 2
    primeira_chamada = ws.send_text.await_args_list[0].args[0]
    assert primeira_chamada == "linha 1\nlinha 2"


def test_send_log_replay_trunca_historico_muito_grande(
    client: Any, db_session: Any
) -> None:
    # Achado #40: o replay enviava db_exec.logs inteiro, sem o teto de 50k que o
    # broadcast ao vivo já aplicava para o mesmo objetivo.
    del client

    automacao = models.Automation(name="Replay Grande", script_path="./test/run.ps1")
    db_session.add(automacao)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_REPLAY_GRANDE",
            automation_id=automacao.id,
            status="RUNNING",
            logs="y" * 60000,
        )
    )
    db_session.commit()

    ws = _make_ws()
    _run_async(_send_log_replay(ws, "EXEC_REPLAY_GRANDE"))

    enviado = ws.send_text.await_args_list[0].args[0]
    assert len(enviado) < 60000
    assert enviado.endswith("[TRUNCATED FOR WS PERFORMANCE]")


def test_send_log_replay_nao_envia_nada_quando_execucao_sem_logs(
    client: Any, db_session: Any
) -> None:
    del client

    automacao = models.Automation(name="Replay Teste 2", script_path="./test/run.ps1")
    db_session.add(automacao)
    db_session.flush()

    execucao = models.Execution(
        id="EXEC_REPLAY_2",
        automation_id=automacao.id,
        status="RUNNING",
        logs=None,
    )
    db_session.add(execucao)
    db_session.commit()

    ws = _make_ws()

    _run_async(_send_log_replay(ws, "EXEC_REPLAY_2"))

    ws.send_text.assert_not_awaited()


def test_send_log_replay_nao_envia_nada_quando_execucao_nao_existe(
    client: Any,
) -> None:
    del client
    ws = _make_ws()

    _run_async(_send_log_replay(ws, "EXEC_INEXISTENTE"))

    ws.send_text.assert_not_awaited()


def test_send_log_replay_suprime_excecao_de_sessao(client: Any) -> None:
    del client
    ws = _make_ws()

    with patch.object(
        websocket_router,
        "session_scope",
        side_effect=RuntimeError("falha de conexao com o banco"),
    ):
        # Nao deve propagar a excecao: o replay e best-effort.
        _run_async(_send_log_replay(ws, "EXEC_1"))

    ws.send_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# Endpoints websocket (via manager real, sem servidor/TestClient real)
# ---------------------------------------------------------------------------


def test_websocket_exec_logs_fecha_conexao_com_4003_quando_key_invalida() -> None:
    ws = _make_ws()
    ws.query_params = {}

    with patch("app.routers.websocket._validate_ws_key", return_value=False):
        _run_async(websocket_router.websocket_exec_logs(ws, "EXEC_KEY_INVALIDA"))

    ws.close.assert_awaited_once_with(code=4003)
    ws.accept.assert_not_awaited()


def test_websocket_exec_logs_conecta_faz_replay_e_desconecta_no_disconnect() -> None:
    ws = _make_ws()
    ws.query_params = {"key": TEST_AUTH_VALUE}
    ws.receive_text.side_effect = WebSocketDisconnect()

    with (
        patch("app.routers.websocket._validate_ws_key", return_value=True),
        patch(
            "app.routers.websocket._send_log_replay", new_callable=AsyncMock
        ) as mock_replay,
    ):
        _run_async(websocket_router.websocket_exec_logs(ws, "EXEC_LOOP"))

    ws.accept.assert_awaited_once()
    mock_replay.assert_awaited_once_with(ws, "EXEC_LOOP")
    assert "EXEC_LOOP" not in websocket_router.manager.exec_connections


def test_websocket_global_events_fecha_conexao_com_4003_quando_key_invalida() -> None:
    ws = _make_ws()
    ws.query_params = {}

    with patch("app.routers.websocket._validate_ws_key", return_value=False):
        _run_async(websocket_router.websocket_global_events(ws))

    ws.close.assert_awaited_once_with(code=4003)
    ws.accept.assert_not_awaited()


def test_websocket_global_events_conecta_e_desconecta_no_disconnect() -> None:
    ws = _make_ws()
    ws.query_params = {"key": TEST_AUTH_VALUE}
    ws.receive_text.side_effect = WebSocketDisconnect()

    with patch("app.routers.websocket._validate_ws_key", return_value=True):
        _run_async(websocket_router.websocket_global_events(ws))

    ws.accept.assert_awaited_once()
    assert ws not in websocket_router.manager.global_connections


# ---------------------------------------------------------------------------
# Endpoints HTTP (integracao via TestClient) — complementam
# test_websocket_broadcast_auth.py cobrindo o corpo de resposta.
# ---------------------------------------------------------------------------


def test_broadcast_log_endpoint_retorna_status_ok(client: Any) -> None:
    response = client.post(
        "/api/broadcast_log",
        json={"exec_id": "EXEC_HTTP_1", "message": "linha de log"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_broadcast_logs_endpoint_retorna_quantidade_processada(client: Any) -> None:
    response = client.post(
        "/api/broadcast_logs",
        json={
            "logs": [
                {"exec_id": "EXEC_HTTP_1", "message": "linha 1"},
                {"exec_id": "EXEC_HTTP_1", "message": "linha 2"},
                {"exec_id": "", "message": "ignorada"},
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["processed"] == 2


def test_broadcast_logs_endpoint_sem_logs_processa_zero(client: Any) -> None:
    response = client.post(
        "/api/broadcast_logs",
        json={},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "processed": 0}


def test_broadcast_logs_endpoint_rejeita_lote_acima_do_teto(client: Any) -> None:
    # Achado #42: os endpoints aceitavam dict livre, sem schema nem limite de
    # itens. O flusher do Worker manda 1 entrada por execução ativa, então o
    # teto é folgado — serve contra payload não-limitado de chamador arbitrário.
    from app.schemas.system import (  # pylint: disable=import-outside-toplevel
        WS_MAX_LOG_ENTRIES,
    )

    excedente = [
        {"exec_id": f"EXEC_{i}", "message": "linha"}
        for i in range(WS_MAX_LOG_ENTRIES + 1)
    ]
    response = client.post(
        "/api/broadcast_logs", json={"logs": excedente}, headers=AUTH_HEADERS
    )
    assert response.status_code == 422


def test_broadcast_log_endpoint_rejeita_tipo_invalido(client: Any) -> None:
    # message precisa ser string; antes qualquer estrutura passava.
    response = client.post(
        "/api/broadcast_log",
        json={"exec_id": "EXEC_X", "message": {"nested": "objeto"}},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


def test_broadcast_event_endpoint_retorna_status_ok(client: Any) -> None:
    response = client.post(
        "/api/broadcast_event",
        json={"type": "QA_EVENT", "data": {"foo": "bar"}},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_broadcast_event_endpoint_usa_defaults_quando_payload_vazio(
    client: Any,
) -> None:
    response = client.post(
        "/api/broadcast_event",
        json={},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
