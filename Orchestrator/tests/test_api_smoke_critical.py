# pylint: disable=all
# mypy: ignore-errors
"""
Smoke critico de API (fluxo E2E): automacoes, execucoes e sistema.
"""

import re
from pathlib import Path

from conftest import AUTH_HEADERS


def _create_default_automation(client, name="Smoke Auto"):
    return client.post(
        "/api/automations",
        json={
            "name": name,
            "description": "Fluxo smoke",
            "script_path": "./test/run.ps1",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )


def test_smoke_automations_flow_and_controls(client):
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

    overview = client.get(f"/api/automations/{auto_id}/overview", headers=AUTH_HEADERS)
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["automation"]["id"] == auto_id
    assert "metrics_24h" in payload
    assert payload["recent_executions"][0]["id"] == exec_id


def test_smoke_executions_filters_and_errors(client):
    created = _create_default_automation(client, name="Exec Filter Auto")
    auto_id = created.json()["id"]
    started = client.post(f"/api/automations/{auto_id}/start", headers=AUTH_HEADERS)
    exec_id = started.json()["exec_id"]

    filtered = client.get(
        f"/api/executions?page=1&per_page=10&status=PENDING&automation_id={auto_id}&requested_by=test",
        headers=AUTH_HEADERS,
    )
    assert filtered.status_code == 200
    data = filtered.json()
    assert data["total"] >= 1
    assert any(item["id"] == exec_id for item in data["items"])

    invalid_status = client.get(
        "/api/executions?status=NOT_A_STATUS",
        headers=AUTH_HEADERS,
    )
    assert invalid_status.status_code == 422

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

    missing_exec = client.get("/api/executions/EXEC_INEXISTENTE", headers=AUTH_HEADERS)
    assert missing_exec.status_code == 404


def test_smoke_system_endpoints_success_and_operational_errors(client, monkeypatch, tmp_path):
    import app.routers.system as system_router

    env_path = tmp_path / ".env"
    env_path.write_text("ORCHESTRATOR_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(system_router, "PROJECT_ROOT", str(tmp_path))

    from sqlalchemy.orm.session import Session as SqlAlchemySession
    original_execute = SqlAlchemySession.execute

    def fake_execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        match = re.search(r"VACUUM INTO '(.+)'", sql)
        if match:
            Path(match.group(1)).write_bytes(b"test-backup")
            return None
        return original_execute(self, stmt, *args, **kwargs)

    monkeypatch.setattr("sqlalchemy.orm.session.Session.execute", fake_execute, raising=False)

    health = client.get("/api/system/health")
    assert health.status_code == 200

    overview = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert overview.status_code == 200
    assert "kpis" in overview.json()

    jobs = client.get("/api/system/scheduler/jobs", headers=AUTH_HEADERS)
    assert jobs.status_code == 200

    audit = client.get("/api/system/audit?limit=10", headers=AUTH_HEADERS)
    assert audit.status_code == 200

    env_get = client.get("/api/system/env", headers=AUTH_HEADERS)
    assert env_get.status_code == 200

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

    purge_ok = client.post("/api/system/purge?retention_days=7", headers=AUTH_HEADERS)
    assert purge_ok.status_code == 200

    purge_bad = client.post("/api/system/purge?retention_days=6", headers=AUTH_HEADERS)
    assert purge_bad.status_code == 400
