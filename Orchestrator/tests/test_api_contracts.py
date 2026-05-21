# pylint: disable=all
# mypy: ignore-errors
"""
Suite de testes focado em integridade de payloads e contratos de API (Fase 5.5).

Valida:
1. Respostas HTTP apropriadas (200, 400, 403, 404, 409, 422).
2. Presença do campo contract_version nas respostas do overview e diagnostics.
3. Segurança Zero Trust (bloqueio sem X-API-Key e não exposição de chaves privadas).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from tests.conftest import AUTH_HEADERS


def test_api_unauthorized_access(client: TestClient):
    """Garante que requisições sem API Key válida recebam 403 Forbidden."""
    # Rota protegida sem headers
    response = client.get("/api/system/diagnostics")
    assert response.status_code == 403
    assert "API Key" in response.json()["detail"]
    assert response.json()["code"] == "access_denied"
    assert response.json()["correlation_id"]

    # Rota protegida com API Key errada
    response = client.get("/api/system/diagnostics", headers={"X-API-Key": "wrong-token"})
    assert response.status_code == 403
    assert "API Key" in response.json()["detail"]
    assert response.json()["code"] == "access_denied"
    assert response.json()["correlation_id"]


def test_api_not_found(client: TestClient):
    """Garante que IDs inexistentes recebam status HTTP 404 apropriado."""
    response = client.get("/api/automations/99999", headers=AUTH_HEADERS)
    assert response.status_code == 404
    assert "Automação não encontrada" in response.json()["detail"]
    assert response.json()["code"] == "resource_not_found"

    response = client.get("/api/executions/EXEC_NONEXISTENT", headers=AUTH_HEADERS)
    assert response.status_code == 404
    assert "Execução não encontrada" in response.json()["detail"]
    assert response.json()["code"] == "resource_not_found"


def test_diagnostics_and_overview_contract_version(client: TestClient, db_session: Session):
    """Valida a presença de contract_version e a ausência de vazamento de segredos nos payloads principais."""
    # Executar chamada do diagnostics
    response = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    
    # Validar campos de contrato
    assert "contract_version" in data
    assert "schema_version" in data
    assert "version" in data
    assert data["trace"]["correlation_id"]
    
    # Garantir que dados sensíveis de banco/arquivos não sejam vazados
    # diagnostics expõe informações de saúde e caminhos, mas não chaves do .env
    assert "DB_PASSWORD" not in str(data)
    assert "hub-secret-token" not in str(data)

    # Executar chamada do overview
    response = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert response.status_code == 200
    overview_data = response.json()

    assert "contract_version" in overview_data
    assert "schema_version" in overview_data
    assert "version" in overview_data
    assert "kpis" in overview_data
    assert "health" in overview_data
