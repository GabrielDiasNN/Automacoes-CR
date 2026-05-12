# pylint: disable=all
# mypy: ignore-errors
"""
Testes de API do Orchestrator Central de Automacoes v5.0.

15+ cenarios cobrindo: CRUD, validacao, seguranca, execucoes, sistema.
"""

import pytest
from conftest import AUTH_HEADERS

# ============================================================
# ROOT
# ============================================================


def test_read_root(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert "5.0.0" in data["version"]
    assert "dashboard_url" in data


# ============================================================
# SEGURANCA
# ============================================================


def test_reject_without_api_key(client):
    res = client.get("/api/automations/all")
    assert res.status_code == 403


def test_reject_wrong_api_key(client):
    res = client.get("/api/automations/all", headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 403


# ============================================================
# CRUD AUTOMATIONS
# ============================================================


def test_create_automation(client):
    res = client.post(
        "/api/automations",
        json={
            "name": "Test Task",
            "description": "Tarefa de teste",
            "script_path": "./test/run.ps1",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    if res.status_code != 201:
        print("DEBUG:", res.json())
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Test Task"
    assert data["id"] is not None


def test_create_duplicate_name_rejected(client):
    client.post(
        "/api/automations",
        json={
            "name": "Unique Task",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.post(
        "/api/automations",
        json={
            "name": "Unique Task",
            "script_path": "./test/run2.ps1",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 409


def test_list_automations_paginated(client):
    for i in range(5):
        client.post(
            "/api/automations",
            json={
                "name": f"Auto {i}",
                "script_path": f"./test/run{i}.ps1",
            },
            headers=AUTH_HEADERS,
        )

    res = client.get("/api/automations?page=1&per_page=3", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 3
    assert data["total"] == 5
    assert data["pages"] == 2


def test_update_automation(client):
    client.post(
        "/api/automations",
        json={
            "name": "To Update",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.put(
        "/api/automations/1",
        json={
            "description": "Atualizado",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["description"] == "Atualizado"


def test_delete_automation(client):
    client.post(
        "/api/automations",
        json={
            "name": "To Delete",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.delete("/api/automations/1", headers=AUTH_HEADERS)
    assert res.status_code == 200


# ============================================================
# VALIDACAO DE SCHEMAS
# ============================================================


def test_reject_path_traversal(client):
    res = client.post(
        "/api/automations",
        json={
            "name": "Evil Task",
            "script_path": "../../etc/passwd",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_reject_dangerous_name(client):
    res = client.post(
        "/api/automations",
        json={
            "name": "<script>alert(1)</script>",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_reject_invalid_schedule(client):
    res = client.post(
        "/api/automations",
        json={
            "name": "Bad Schedule",
            "script_path": "./test/run.ps1",
            "schedule": "not-a-json",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


# ============================================================
# EXECUCOES
# ============================================================


def test_start_automation_creates_pending(client):
    client.post(
        "/api/automations",
        json={
            "name": "Queue Test",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.post("/api/automations/1/start", headers=AUTH_HEADERS)
    assert res.status_code == 200
    exec_id = res.json()["exec_id"]

    res2 = client.get(f"/api/executions/{exec_id}", headers=AUTH_HEADERS)
    assert res2.json()["status"] == "PENDING"


def test_reject_duplicate_execution(client):
    client.post(
        "/api/automations",
        json={
            "name": "Dup Test",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    client.post("/api/automations/1/start", headers=AUTH_HEADERS)
    res = client.post("/api/automations/1/start", headers=AUTH_HEADERS)
    assert res.status_code == 409


def test_stop_execution(client):
    client.post(
        "/api/automations",
        json={
            "name": "Stop Test",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    start = client.post("/api/automations/1/start", headers=AUTH_HEADERS)
    exec_id = start.json()["exec_id"]

    res = client.post(f"/api/executions/{exec_id}/stop", headers=AUTH_HEADERS)
    assert res.status_code == 200

    check = client.get(f"/api/executions/{exec_id}", headers=AUTH_HEADERS)
    assert check.json()["status"] == "TERMINATED"


def test_list_recent_executions(client):
    client.post(
        "/api/automations",
        json={
            "name": "Recent Test",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    client.post("/api/automations/1/start", headers=AUTH_HEADERS)

    res = client.get("/api/executions/recent?limit=5", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert len(res.json()) >= 1


# ============================================================
# SISTEMA
# ============================================================


def test_health_check(client):
    res = client.get("/api/system/health")
    assert res.status_code == 200
    data = res.json()
    assert data["database"] == "online"
    assert data["status"] in ["healthy", "degraded", "unhealthy"]


def test_metrics(client):
    res = client.get("/api/system/metrics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert "summary" in res.json()
    assert "automations" in res.json()


def test_uptime(client):
    res = client.get("/api/system/uptime", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert "uptime_seconds" in res.json()


def test_health_includes_wal_size(client):
    """v5.0: health deve incluir wal_size_mb."""
    res = client.get("/api/system/health")
    assert res.status_code == 200
    assert "wal_size_mb" in res.json()


def test_version_endpoint(client):
    """v5.0: novo endpoint enterprise /api/system/version."""
    res = client.get("/api/system/version", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "5.0.0"
    assert "python_version" in data
    assert "uptime_seconds" in data
    assert "max_workers" in data
