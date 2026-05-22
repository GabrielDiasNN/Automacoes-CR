# pylint: disable=all
# mypy: ignore-errors
"""
Testes focados nas operações de CRUD de Automações.
"""

import pytest
from app.constants import ORCHESTRATOR_VERSION
from conftest import AUTH_HEADERS


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
    assert data["schedule_summary"] == "Manual"
    assert data["operational_state"] == "idle"
    assert data["active_execution_count"] == 0


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
    assert "last_execution_id" in res.json()


def test_update_automation_reloads_scheduler(client, monkeypatch):
    import app.routers.automations as auto_router

    client.post(
        "/api/automations",
        json={
            "name": "Reload Scheduler",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    calls = []
    monkeypatch.setattr(
        auto_router, "_reload_scheduler_safe", lambda: calls.append("reload")
    )

    res = client.put(
        "/api/automations/1",
        json={
            "enabled": False,
        },
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 200
    assert calls == ["reload"]


def test_update_automation_rejects_path_escape(client):
    client.post(
        "/api/automations",
        json={
            "name": "Path Guard",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.put(
        "/api/automations/1",
        json={
            "script_path": "C:\\Windows\\win.ini",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


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


def test_reject_schedule_with_invalid_time(client):
    res = client.post(
        "/api/automations",
        json={
            "name": "Bad Time",
            "script_path": "./test/run.ps1",
            "schedule": '{"times":[{"h":25,"m":0}]}',
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422
