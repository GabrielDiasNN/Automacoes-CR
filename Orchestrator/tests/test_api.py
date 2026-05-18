# pylint: disable=all
# mypy: ignore-errors
"""
Testes de API do Orchestrator Central de Automacoes v5.0.

15+ cenarios cobrindo: CRUD, validacao, seguranca, execucoes, sistema.
"""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import AUTH_HEADERS
from app.constants import ORCHESTRATOR_VERSION

# ============================================================
# ROOT
# ============================================================

def test_read_root(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == ORCHESTRATOR_VERSION
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
    monkeypatch.setattr(auto_router, "_reload_scheduler_safe", lambda: calls.append("reload"))

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
    assert "[STOP] Interrupcao solicitada via API" in check.json()["logs"]
    assert check.json()["duration_seconds"] is not None

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
    assert data["version"] == ORCHESTRATOR_VERSION
    assert "python_version" in data
    assert "uptime_seconds" in data
    assert "max_workers" in data

def test_diagnostics_endpoint(client):
    res = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == ORCHESTRATOR_VERSION
    assert data["overall_status"] in ["healthy", "degraded", "unhealthy"]
    assert "findings" in data
    assert "database" in data
    assert data["database"]["schema"]["valid"] is True
    assert "wal_risk" in data["database"]
    assert "scheduler" in data
    assert "next_runs" in data["scheduler"]
    assert "worker" in data
    assert "queue" in data
    assert "oldest_pending" in data["queue"]
    assert "oldest_running" in data["queue"]
    assert "active_by_priority" in data["queue"]
    assert "active_by_group" in data["queue"]
    assert "heartbeat" in data
    assert "operator_actions" in data
    assert "failure_hotspots" in data

def test_diagnostics_reports_actionable_queue_and_wal_findings(client, db_session, monkeypatch):
    import app.routers.system as system_router
    from app import models
    from app.timezone import get_now_local

    auto = models.Automation(name="Diag Queue", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_OLD_PENDING",
            automation_id=auto.id,
            status="PENDING",
            requested_by="TEST",
            started_at=get_now_local() - timedelta(minutes=20),
        )
    )
    db_session.commit()
    monkeypatch.setattr(system_router, "get_wal_size_mb", lambda: 128.0)

    res = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    assert data["overall_status"] in ["degraded", "unhealthy"]
    assert data["database"]["wal_risk"] == "elevated"
    assert data["queue"]["oldest_pending"]["exec_id"] == "EXEC_OLD_PENDING"
    assert data["queue"]["oldest_pending"]["age_seconds"] >= 1200
    components = {item["component"] for item in data["findings"]}
    assert {"database", "queue"}.issubset(components)
    assert any(item["action_code"] == "checkpoint" for item in data["findings"])
    assert any(item["action_code"] == "worker_wakeup" for item in data["findings"])
    assert any(item["action_code"] == "checkpoint" for item in data["operator_actions"])

def test_diagnostics_offline_worker_prefers_recovery_action(client, db_session, monkeypatch):
    import app.routers.system as system_router
    from app import models
    from app.schemas import WorkerStatus
    from app.timezone import get_now_local

    auto = models.Automation(name="Recover Worker", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_OFFLINE_PENDING",
            automation_id=auto.id,
            status="PENDING",
            requested_by="TEST",
            started_at=get_now_local() - timedelta(minutes=20),
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        system_router,
        "_get_worker_status",
        lambda db: WorkerStatus(
            is_alive=False,
            pid=5092,
            last_ping=None,
            tasks_completed=0,
            tasks_failed=0,
            active_tasks=0,
            version="6.4.0",
        ),
    )
    monkeypatch.setattr(system_router, "_launch_orchestrator_recovery", lambda: "Recover-Orchestrator.ps1")

    res = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    worker_findings = [item for item in data["findings"] if item["component"] == "worker"]
    assert worker_findings
    assert any("Recuperar" in item["action_hint"] for item in worker_findings)
    assert any(item["action_code"] == "worker_recover" for item in worker_findings)

    recover = client.post("/api/system/worker/recover", headers=AUTH_HEADERS)
    assert recover.status_code == 200
    recover_payload = recover.json()
    assert recover_payload["script"] == "Recover-Orchestrator.ps1"
    assert recover_payload["queue_active_count"] == 1

def test_system_overview_includes_diagnostics_summary(client):
    res = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "diagnostics" in data
    assert data["diagnostics"]["overall_status"] in ["healthy", "degraded", "unhealthy"]
    assert "findings" in data["diagnostics"]

def test_execution_requeue_creates_auditable_pending_retry(client, db_session):
    from app import models
    from app.timezone import get_now_local

    auto = models.Automation(
        name="Retry Source",
        script_path="./test/run.ps1",
        max_retries=2,
        queue_group="oracle",
    )
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_RETRY_SRC",
            automation_id=auto.id,
            status="ERROR",
            retry_count=0,
            max_retries=2,
            queue_group="oracle",
            failure_reason="EXIT_CODE_24",
            recovery_action="REVIEW_LOGS_AND_OPTIONALLY_REQUEUE",
            requested_by="TEST",
            started_at=get_now_local() - timedelta(minutes=5),
        )
    )
    db_session.commit()

    res = client.post(
        "/api/executions/EXEC_RETRY_SRC/requeue",
        json={"reason": "Reteste controlado", "requested_by": "QA", "priority": "HIGH"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["source_exec_id"] == "EXEC_RETRY_SRC"
    assert payload["retry_count"] == 1
    assert payload["max_retries"] == 2

    source = db_session.query(models.Execution).filter(models.Execution.id == "EXEC_RETRY_SRC").first()
    queued = db_session.query(models.Execution).filter(models.Execution.id == payload["queued_exec_id"]).first()
    assert source.status == "REQUEUED"
    assert source.recovery_action == "REQUEUED_TO_NEW_EXECUTION"
    assert queued.status == "PENDING"
    assert queued.priority == "HIGH"
    assert queued.queue_group == "oracle"
    assert queued.failure_reason == "EXIT_CODE_24"
    assert queued.recovery_action == "REQUEUE_MANUAL"

def test_execution_requeue_blocks_retry_limit(client, db_session):
    from app import models
    from app.timezone import get_now_local

    auto = models.Automation(name="Retry Limit", script_path="./test/run.ps1", max_retries=1)
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_RETRY_LIMIT",
            automation_id=auto.id,
            status="ERROR",
            retry_count=1,
            max_retries=1,
            requested_by="TEST",
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    res = client.post(
        "/api/executions/EXEC_RETRY_LIMIT/requeue",
        json={"reason": "limite"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 409

def test_execution_requeue_blocks_active_queue_group(client, db_session):
    from app import models
    from app.timezone import get_now_local

    source_auto = models.Automation(
        name="Retry Group Source",
        script_path="./test/run.ps1",
        max_retries=2,
        queue_group="oracle",
    )
    active_auto = models.Automation(
        name="Retry Group Active",
        script_path="./test/run2.ps1",
        max_retries=2,
        queue_group="oracle",
    )
    db_session.add_all([source_auto, active_auto])
    db_session.flush()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_GROUP_SOURCE",
                automation_id=source_auto.id,
                status="ERROR",
                retry_count=0,
                max_retries=2,
                queue_group="oracle",
                requested_by="TEST",
                started_at=get_now_local() - timedelta(minutes=5),
            ),
            models.Execution(
                id="EXEC_GROUP_ACTIVE",
                automation_id=active_auto.id,
                status="RUNNING",
                retry_count=0,
                max_retries=2,
                queue_group="oracle",
                requested_by="TEST",
                started_at=get_now_local(),
            ),
        ]
    )
    db_session.commit()

    res = client.post(
        "/api/executions/EXEC_GROUP_SOURCE/requeue",
        json={"reason": "grupo ocupado"},
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 409
    assert "mesmo grupo operacional" in res.json()["detail"]

def test_wait_for_task_requires_api_key(client):
    res = client.get("/api/system/wait-for-task")
    assert res.status_code == 403

def test_update_automation_config_creates_backup(client, monkeypatch, tmp_path):
    import app.routers.automations as auto_router

    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    script_path = bot_dir / "run.ps1"
    config_path = bot_dir / "config.json"
    script_path.write_text("Write-Host 'ok'", encoding="utf-8")
    config_path.write_text('{"old": true}', encoding="utf-8")

    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))
    client.post(
        "/api/automations",
        json={"name": "Config Backup", "script_path": "./Bot/run.ps1"},
        headers=AUTH_HEADERS,
    )

    res = client.put(
        "/api/automations/1/configs/config.json",
        json={"content": '{"new": true}'},
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 200
    backup_relpath = res.json()["backup"]
    backup_path = bot_dir / backup_relpath
    assert backup_path.exists()
    assert json.loads(backup_path.read_text(encoding="utf-8")) == {"old": True}
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"new": True}

def test_update_automation_script_creates_backup_and_preserves_ps_bom(
    client,
    monkeypatch,
    tmp_path,
):
    import app.routers.automations as auto_router

    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    script_path = bot_dir / "run.ps1"
    script_path.write_text("Write-Host 'old'", encoding="utf-8-sig")

    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))
    client.post(
        "/api/automations",
        json={"name": "Script Backup", "script_path": "./Bot/run.ps1"},
        headers=AUTH_HEADERS,
    )

    res = client.put(
        "/api/automations/1/scripts/run.ps1",
        json={"content": "Write-Host 'new'"},
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 200
    backup_path = bot_dir / res.json()["backup"]
    assert backup_path.exists()
    assert "old" in backup_path.read_text(encoding="utf-8-sig")
    assert script_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "new" in script_path.read_text(encoding="utf-8-sig")

def test_update_automation_script_rejects_path_escape(client, monkeypatch, tmp_path):
    import app.routers.automations as auto_router

    bot_dir = tmp_path / "Bot"
    bot_dir.mkdir()
    (bot_dir / "run.ps1").write_text("Write-Host 'ok'", encoding="utf-8")

    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))
    client.post(
        "/api/automations",
        json={"name": "Script Escape", "script_path": "./Bot/run.ps1"},
        headers=AUTH_HEADERS,
    )

    res = client.put(
        "/api/automations/1/scripts/..%2Frun.ps1",
        json={"content": "bad"},
        headers=AUTH_HEADERS,
    )

    assert res.status_code in (400, 404)

def test_update_env_creates_backup(client, monkeypatch, tmp_path):
    import app.routers.system as system_router

    env_path = tmp_path / ".env"
    env_path.write_text("ORCHESTRATOR_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(system_router, "PROJECT_ROOT", str(tmp_path))

    res = client.put(
        "/api/system/env",
        json={"content": "ORCHESTRATOR_API_KEY=new\n"},
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 200
    backup_relpath = res.json()["backup"]
    backup_path = tmp_path / backup_relpath
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "ORCHESTRATOR_API_KEY=old\n"
    assert env_path.read_text(encoding="utf-8") == "ORCHESTRATOR_API_KEY=new\n"

def test_system_router_project_root_points_to_repo_root():
    import app.routers.system as system_router

    expected_root = Path(__file__).resolve().parents[2]
    assert Path(system_router.PROJECT_ROOT).resolve() == expected_root.resolve()
