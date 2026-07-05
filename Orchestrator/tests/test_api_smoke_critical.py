"""
Smoke critico de API (fluxo E2E): automacoes, execucoes e sistema.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.orm.session import Session as SqlAlchemySession

import app.routers.system as system_router
from app.constants import ORCHESTRATOR_CONTRACT_VERSION


def _create_default_automation(client: TestClient, name: str = "Smoke Auto") -> Any:
    return client.post(
        "/api/automations",
        json={
            "name": name,
            "description": "Fluxo smoke",
            "script_path": "./test/run.ps1",
            "max_retries": 2,
            "cooldown_minutes": 0,
            "queue_group": "smoke-group",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )


def test_smoke_automations_flow_and_controls(client: TestClient) -> None:
    created = _create_default_automation(client)
    assert created.status_code == 201
    auto_id = created.json()["id"]

    updated = client.put(
        f"/api/automations/{auto_id}",
        json={
            "description": "Atualizado no smoke",
            "schedule": '{"daysOfWeek":[1,2,3,4,5],"times":[{"h":9,"m":0}]}',
            "notification_channels": "email,whatsapp",
        },
        headers=AUTH_HEADERS,
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Atualizado no smoke"

    started = client.post(f"/api/automations/{auto_id}/start", headers=AUTH_HEADERS)
    assert started.status_code == 200
    exec_id = started.json()["exec_id"]

    duplicated = client.post(f"/api/automations/{auto_id}/start", headers=AUTH_HEADERS)
    assert duplicated.status_code == 409

    toggled = client.post(
        f"/api/automations/{auto_id}/test-mode?enabled=true",
        headers=AUTH_HEADERS,
    )
    assert toggled.status_code == 200

    paused = client.post("/api/automations/control/pause-all", headers=AUTH_HEADERS)
    assert paused.status_code == 200
    assert "pausadas" in paused.json()["message"].lower()

    resumed = client.post("/api/automations/control/resume-all", headers=AUTH_HEADERS)
    assert resumed.status_code == 200
    assert "retomadas" in resumed.json()["message"].lower()

    paused_single = client.post(
        f"/api/automations/{auto_id}/pause", headers=AUTH_HEADERS
    )
    assert paused_single.status_code == 200
    resumed_single = client.post(
        f"/api/automations/{auto_id}/resume", headers=AUTH_HEADERS
    )
    assert resumed_single.status_code == 200

    cloned = client.post(f"/api/automations/{auto_id}/clone", headers=AUTH_HEADERS)
    assert cloned.status_code == 201
    assert cloned.json()["enabled"] is False

    overview = client.get(f"/api/automations/{auto_id}/overview", headers=AUTH_HEADERS)
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["automation"]["id"] == auto_id
    assert "schedule_summary" in payload["automation"]
    assert "operational_state" in payload["automation"]
    assert "metrics_24h" in payload
    assert payload["recent_executions"][0]["id"] == exec_id


def _assert_execution_filters(client: TestClient, auto_id: str, exec_id: str) -> None:
    filtered = client.get(
        f"/api/executions?page=1&per_page=10&status=PENDING&automation_id={auto_id}&requested_by=test",
        headers=AUTH_HEADERS,
    )
    assert filtered.status_code == 200
    data = filtered.json()
    assert data["total"] >= 1
    assert any(item["id"] == exec_id for item in data["items"])
    assert all("operator_action_label" in item for item in data["items"])
    assert all("operator_attention_required" in item for item in data["items"])

    filtered_by_group = client.get(
        "/api/executions?queue_group=smoke-group",
        headers=AUTH_HEADERS,
    )
    assert filtered_by_group.status_code == 200
    assert any(
        item["related_queue_group"] == "smoke-group"
        for item in filtered_by_group.json()["items"]
    )

    filtered_by_priority = client.get(
        "/api/executions?priority=NORMAL",
        headers=AUTH_HEADERS,
    )
    assert filtered_by_priority.status_code == 200
    assert any(
        item["priority"] == "NORMAL" for item in filtered_by_priority.json()["items"]
    )


def _assert_execution_filter_errors(client: TestClient) -> None:
    invalid_status = client.get(
        "/api/executions?status=NOT_A_STATUS",
        headers=AUTH_HEADERS,
    )
    assert invalid_status.status_code == 422

    invalid_priority = client.get(
        "/api/executions?priority=URGENT",
        headers=AUTH_HEADERS,
    )
    assert invalid_priority.status_code == 422

    invalid_date = client.get(
        "/api/executions?date_from=17-05-2026",
        headers=AUTH_HEADERS,
    )
    assert invalid_date.status_code == 422

    inverted_range = client.get(
        "/api/executions?date_from=2026-05-18T00:00:00&date_to=2026-05-17T00:00:00",
        headers=AUTH_HEADERS,
    )
    assert inverted_range.status_code == 422


def test_smoke_executions_filters_and_errors(client: TestClient) -> None:
    created = _create_default_automation(client, name="Exec Filter Auto")
    auto_id = created.json()["id"]
    started = client.post(f"/api/automations/{auto_id}/start", headers=AUTH_HEADERS)
    exec_id = started.json()["exec_id"]

    _assert_execution_filters(client, auto_id, exec_id)
    _assert_execution_filter_errors(client)

    logs = client.get(f"/api/executions/{exec_id}/logs", headers=AUTH_HEADERS)
    assert logs.status_code == 200
    assert "lines" in logs.json()

    artifacts = client.get(f"/api/executions/{exec_id}/artifacts", headers=AUTH_HEADERS)
    assert artifacts.status_code == 200
    assert "artifacts" in artifacts.json()

    stop = client.post(f"/api/executions/{exec_id}/stop", headers=AUTH_HEADERS)
    assert stop.status_code == 200

    stop_again = client.post(f"/api/executions/{exec_id}/stop", headers=AUTH_HEADERS)
    assert stop_again.status_code == 400

    requeue = client.post(
        f"/api/executions/{exec_id}/requeue",
        json={"reason": "retry operacional", "priority": "HIGH"},
        headers=AUTH_HEADERS,
    )
    assert requeue.status_code == 200
    requeue_payload = requeue.json()
    assert requeue_payload["source_exec_id"] == exec_id
    assert requeue_payload["retry_count"] == 1

    missing_exec = client.get("/api/executions/EXEC_INEXISTENTE", headers=AUTH_HEADERS)
    assert missing_exec.status_code == 404


def _patch_vacuum_into(monkeypatch: pytest.MonkeyPatch) -> None:
    original_execute = SqlAlchemySession.execute

    def fake_execute(self: Any, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(stmt)
        match = re.search(r"VACUUM INTO '(.+)'", sql)
        if match:
            Path(match.group(1)).write_bytes(b"test-backup")
            return None
        return original_execute(self, stmt, *args, **kwargs)

    monkeypatch.setattr(
        "sqlalchemy.orm.session.Session.execute", fake_execute, raising=False
    )


def _assert_system_overview_and_diagnostics(client: TestClient) -> None:
    health = client.get("/api/system/health")
    assert health.status_code == 200

    overview = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert overview.status_code == 200
    assert "kpis" in overview.json()
    assert "schema_version" in overview.json()
    assert overview.json()["contract_version"] == ORCHESTRATOR_CONTRACT_VERSION

    jobs = client.get("/api/system/scheduler/jobs", headers=AUTH_HEADERS)
    assert jobs.status_code == 200

    audit = client.get("/api/system/audit?limit=10", headers=AUTH_HEADERS)
    assert audit.status_code == 200

    diagnostics = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert diagnostics.status_code == 200
    assert "schema_version" in diagnostics.json()
    assert diagnostics.json()["contract_version"] == ORCHESTRATOR_CONTRACT_VERSION


def _assert_system_schedule_validate_and_preview(client: TestClient) -> None:
    schedule_validate = client.post(
        "/api/system/schedule/validate",
        json={
            "schedule": '{"schedule_type":"weekly","days_of_week":[1,2,3],"times":[{"h":9,"m":0}]}'
        },
        headers=AUTH_HEADERS,
    )
    assert schedule_validate.status_code == 200
    assert schedule_validate.json()["valid"] is True
    assert "Semanal" in schedule_validate.json()["summary"]

    schedule_preview = client.post(
        "/api/system/schedule/preview",
        json={
            "schedule": '{"schedule_type":"interval","interval_minutes":15}',
            "limit": 3,
        },
        headers=AUTH_HEADERS,
    )
    assert schedule_preview.status_code == 200
    preview_payload = schedule_preview.json()
    assert preview_payload["valid"] is True
    assert preview_payload["schedule_type"] == "interval"
    assert len(preview_payload["next_runs_preview"]) == 3


def _assert_system_env_and_backup(client: TestClient) -> None:
    env_get = client.get("/api/system/env", headers=AUTH_HEADERS)
    assert env_get.status_code == 200

    env_validate = client.post(
        "/api/system/env/validate",
        json={"content": "ORCHESTRATOR_API_KEY=new\nRATE_LIMIT_RPM=120\n"},
        headers=AUTH_HEADERS,
    )
    assert env_validate.status_code == 200
    assert env_validate.json()["valid"] is True

    env_put = client.put(
        "/api/system/env",
        json={"content": "ORCHESTRATOR_API_KEY=new\n"},
        headers=AUTH_HEADERS,
    )
    assert env_put.status_code == 200
    assert "backup" in env_put.json()

    backup = client.post("/api/system/backup", headers=AUTH_HEADERS)
    assert backup.status_code == 200
    assert backup.json()["size_mb"] >= 0


def _assert_system_scheduler_worker_and_purge(client: TestClient) -> None:
    scheduler_reload = client.post("/api/system/scheduler/reload", headers=AUTH_HEADERS)
    assert scheduler_reload.status_code == 200
    assert "jobs_loaded" in scheduler_reload.json()

    worker_wakeup = client.post("/api/system/worker/wakeup", headers=AUTH_HEADERS)
    assert worker_wakeup.status_code == 200

    purge_ok = client.post("/api/system/purge?retention_days=7", headers=AUTH_HEADERS)
    assert purge_ok.status_code == 200

    purge_bad = client.post("/api/system/purge?retention_days=6", headers=AUTH_HEADERS)
    assert purge_bad.status_code == 400


def test_smoke_system_endpoints_success_and_operational_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ORCHESTRATOR_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(system_router, "PROJECT_ROOT", str(tmp_path))
    _patch_vacuum_into(monkeypatch)

    _assert_system_overview_and_diagnostics(client)
    _assert_system_schedule_validate_and_preview(client)
    _assert_system_env_and_backup(client)
    _assert_system_scheduler_worker_and_purge(client)
