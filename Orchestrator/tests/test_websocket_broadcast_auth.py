"""Testes de autenticacao dos endpoints internos de broadcast (worker -> API)."""

from typing import Any

from tests.conftest import AUTH_HEADERS

BROADCAST_CASES: list[tuple[str, dict[str, Any]]] = [
    ("/api/broadcast_log", {"exec_id": "EXEC_QA_1", "message": "linha de log"}),
    (
        "/api/broadcast_logs",
        {"logs": [{"exec_id": "EXEC_QA_1", "message": "linha de log"}]},
    ),
    ("/api/broadcast_event", {"type": "QA_EVENT", "data": {"foo": "bar"}}),
]


def test_broadcast_endpoints_rejeitam_sem_api_key(client: Any) -> None:
    for path, payload in BROADCAST_CASES:
        response = client.post(path, json=payload)
        assert response.status_code == 403, f"{path} deveria exigir API Key"


def test_broadcast_endpoints_rejeitam_api_key_invalida(client: Any) -> None:
    for path, payload in BROADCAST_CASES:
        response = client.post(
            path, json=payload, headers={"X-API-Key": "chave-invalida"}
        )
        assert response.status_code == 403, f"{path} aceitou key inválida"


def test_broadcast_endpoints_aceitam_api_key_valida(client: Any) -> None:
    for path, payload in BROADCAST_CASES:
        response = client.post(path, json=payload, headers=AUTH_HEADERS)
        assert response.status_code == 200, f"{path} falhou com key válida"
        assert response.json().get("status") == "ok"
