# pylint: disable=all
# mypy: ignore-errors
"""
Testes focados nas operações de CRUD de Automações.
"""

from datetime import timedelta

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
    assert data["validated"] is True
    assert data["audit_id"] is not None


def test_preflight_automation_normalizes_channels(client):
    res = client.post(
        "/api/automations/preflight",
        json={
            "name": "Preflight Task",
            "script_path": "./test/run.ps1",
            "notification_channels": " whatsapp , email,whatsapp ",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["normalized_notification_channels"] == "email,whatsapp"
    assert data["resolved_script_path"].endswith("test\\run.ps1")
    assert data["schedule_summary"] == "Manual"


def test_preflight_rejects_reserved_cleanup_script():
    from app.services.automation_preflight import build_automation_preflight

    with pytest.raises(ValueError, match="rotina reservada do sistema"):
        build_automation_preflight(
            {
                "name": "Cleanup Legacy",
                "script_path": "./Tools/AplicarPoliticaRetencao.ps1",
                "enabled": True,
            },
            "C:\\Automacoes",
        )


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
    assert res.json()["validated"] is True
    assert res.json()["audit_id"] is not None


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


def test_reload_scheduler_neutralizes_reserved_cleanup_automation(db_session, monkeypatch):
    from app import models
    from app.runtime import scheduler
    from app.services import scheduler_runtime
    from sqlalchemy.orm import sessionmaker

    for job in list(scheduler.get_jobs()):
        scheduler.remove_job(job.id)

    test_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )
    monkeypatch.setattr(scheduler_runtime, "SessionLocal", test_session_local)

    cleanup_auto = models.Automation(
        name="Retenção de Arquivos",
        script_path="./Tools/AplicarPoliticaRetencao.ps1",
        schedule='{"schedule_version":2,"schedule_type":"weekly","timezone":"America/Sao_Paulo","times":[{"h":2,"m":20}],"days_of_week":[0,1,2,3,4,5,6]}',
        enabled=True,
    )
    db_session.add(cleanup_auto)
    db_session.commit()

    try:
        scheduler_runtime.reload_scheduled_tasks()

        db_session.refresh(cleanup_auto)
        assert cleanup_auto.enabled is False
        assert cleanup_auto.schedule is None
        assert not any(job.id.startswith("job_") for job in scheduler.get_jobs())
    finally:
        for job in list(scheduler.get_jobs()):
            scheduler.remove_job(job.id)


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


def test_list_all_automations_includes_operational_snapshot(client, db_session):
    from app import models, schemas
    from app.timezone import get_now_local

    auto = models.Automation(
        name="Snapshot Auto",
        script_path="./test/run.ps1",
        cooldown_minutes=5,
        max_retries=2,
        queue_group="core",
    )
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_SNAPSHOT_OLD",
                automation_id=auto.id,
                status="ERROR",
                requested_by="SYSTEM",
                started_at=now - timedelta(hours=2),
                finished_at=now - timedelta(hours=2) + timedelta(minutes=1),
                duration_seconds=60,
                failure_reason="Falha antiga",
                recovery_action="Reexecutar",
            ),
            models.Execution(
                id="EXEC_SNAPSHOT_LATEST",
                automation_id=auto.id,
                status="TIMEOUT",
                requested_by="CRON",
                started_at=now - timedelta(minutes=15),
                finished_at=now - timedelta(minutes=5),
                duration_seconds=600,
                failure_reason="Timeout operacional",
                recovery_action="Investigar worker",
            ),
        ]
    )
    db_session.commit()

    res = client.get("/api/automations/all", headers=AUTH_HEADERS)
    assert res.status_code == 200
    payload = next(item for item in res.json() if item["name"] == "Snapshot Auto")

    assert payload["last_execution_id"] == "EXEC_SNAPSHOT_LATEST"
    assert payload["last_status"] == "TIMEOUT"
    assert payload["last_execution_started_at"] == schemas.format_dt_br(
        now - timedelta(minutes=15)
    )
    assert payload["last_execution_finished_at"] == schemas.format_dt_br(
        now - timedelta(minutes=5)
    )
    assert payload["last_execution_duration_seconds"] == 600.0
    assert payload["last_failure_reason"] == "Timeout operacional"
    assert payload["last_recovery_action"] == "Investigar worker"
    assert payload["last_requested_by"] == "CRON"
    assert payload["success_24h"] == 0
    assert payload["failures_24h"] == 2
    assert payload["timeouts_24h"] == 1
    assert payload["error_24h"] == 2
    assert payload["active_execution_count"] == 0
    assert payload["pending_count"] == 0
    assert payload["operational_state"] == "attention"


def test_get_automation_returns_latest_execution_context_for_modal(client, db_session):
    from app import models, schemas
    from app.timezone import get_now_local

    auto = models.Automation(
        name="Modal Auto",
        script_path="./test/run.ps1",
        enabled=True,
    )
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_MODAL_OLD",
                automation_id=auto.id,
                status="SUCCESS",
                requested_by="SYSTEM",
                started_at=now - timedelta(hours=1),
                finished_at=now - timedelta(hours=1) + timedelta(minutes=3),
                duration_seconds=180,
            ),
            models.Execution(
                id="EXEC_MODAL_LATEST",
                automation_id=auto.id,
                status="RUNNING",
                requested_by="TERMINAL",
                started_at=now - timedelta(minutes=4),
                failure_reason=None,
            ),
        ]
    )
    db_session.commit()

    res = client.get(f"/api/automations/{auto.id}", headers=AUTH_HEADERS)
    assert res.status_code == 200
    payload = res.json()

    assert payload["last_execution_id"] == "EXEC_MODAL_LATEST"
    assert payload["last_status"] == "RUNNING"
    assert payload["last_execution_started_at"] == schemas.format_dt_br(
        now - timedelta(minutes=4)
    )
    assert payload["last_execution_finished_at"] is None
    assert payload["last_requested_by"] == "TERMINAL"
    assert payload["success_24h"] == 1
    assert payload["failures_24h"] == 0
    assert payload["timeouts_24h"] == 0
    assert payload["active_execution_count"] == 1
    assert payload["pending_count"] == 1
    assert payload["operational_state"] == "in_progress"
