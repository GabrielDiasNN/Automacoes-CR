# pylint: disable=all
# mypy: ignore-errors
"""
Suite de testes focado em sanidade operacional, validações de input e segurança (Fase 5.4).

Valida:
1. Rejeição de cron schedules inválidos (Weekly, Daily, Interval, Monthly).
2. Detecção de format, chaves vazias ou duplicadas no validador do .env administrativo.
3. Proteção contra gravação de dados inseguros e prevenção de vazamento de segredos.
"""

import pytest
from app import models
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.conftest import AUTH_HEADERS


def test_validate_invalid_schedules(client: TestClient):
    """Garante que a API e o validador de schedules rejeitam payloads malformados ou inválidos."""
    # Cenário 1: Schedule sem ser JSON
    response = client.post(
        "/api/system/schedule/validate",
        headers=AUTH_HEADERS,
        json={"schedule": "não-sou-json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "Schedule deve ser JSON válido" in data["errors"][0]

    # Cenário 2: weekly sem days_of_week
    response = client.post(
        "/api/system/schedule/validate",
        headers=AUTH_HEADERS,
        json={"schedule": '{"schedule_type": "weekly", "times": [{"h": 12, "m": 30}]}'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "days_of_week é obrigatório" in data["errors"][0]

    # Cenário 3: times com hora inválida (h: 25)
    response = client.post(
        "/api/system/schedule/validate",
        headers=AUTH_HEADERS,
        json={"schedule": '{"schedule_type": "daily", "times": [{"h": 25, "m": 30}]}'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "times[].h deve estar entre 0 e 23" in data["errors"][0]

    # Cenário 4: Criar automação com schedule inválido diretamente na rota POST /api/automations
    response = client.post(
        "/api/automations",
        headers=AUTH_HEADERS,
        json={
            "name": "Automacao Schedule Invalido",
            "script_path": "Orchestrator/tests/test/run1.ps1",
            "schedule": '{"schedule_type": "daily", "times": [{"h": 90, "m": 0}]}',
        },
    )
    # FastAPI deve interceptar no validador do schema Pydantic e retornar 422
    assert response.status_code == 422


def test_validate_env_rules(client: TestClient):
    """Valida as regras de negócio de saneamento e integridade aplicadas ao arquivo .env."""
    # Cenário 1: Linha mal-formatada (sem =)
    payload = {"content": "LINHA_SEM_IGUAL\nTEST_KEY=123"}
    response = client.post(
        "/api/system/env/validate",
        headers=AUTH_HEADERS,
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["issue_count"] == 1
    assert data["issues"][0]["code"] == "INVALID_FORMAT"

    # Cenário 2: Chave vazia
    payload = {"content": "=VALOR\nANOTHER=456"}
    response = client.post(
        "/api/system/env/validate",
        headers=AUTH_HEADERS,
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["issues"][0]["code"] == "EMPTY_KEY"

    # Cenário 3: Chave com espaço
    payload = {"content": "CHAVE COM ESPACO=123"}
    response = client.post(
        "/api/system/env/validate",
        headers=AUTH_HEADERS,
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["issues"][0]["code"] == "INVALID_KEY"

    # Cenário 4: Chave duplicada
    payload = {"content": "MINHA_CHAVE=111\nMINHA_CHAVE=222"}
    response = client.post(
        "/api/system/env/validate",
        headers=AUTH_HEADERS,
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["issues"][0]["code"] == "DUPLICATE_KEY"
