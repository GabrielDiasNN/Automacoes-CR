# pylint: disable=all
# mypy: ignore-errors
"""
Testes focados nas operações e endpoints de diagnóstico/informações do Sistema.
"""

from datetime import timedelta
from pathlib import Path
import pytest
from app.constants import ORCHESTRATOR_CONTRACT_VERSION, ORCHESTRATOR_VERSION
from conftest import AUTH_HEADERS


def test_read_root(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == ORCHESTRATOR_VERSION
    assert "dashboard_url" in data


def test_reject_without_api_key(client):
    res = client.get("/api/automations/all")
    assert res.status_code == 403


def test_reject_wrong_api_key(client):
    res = client.get("/api/automations/all", headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 403


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
    res = client.get("/api/system/health")
    assert res.status_code == 200
    assert "wal_size_mb" in res.json()


def test_version_endpoint(client):
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
    assert data["contract_version"] == ORCHESTRATOR_CONTRACT_VERSION
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
    assert "checks" in data
    assert "recovery" in data
    assert "operational_baseline" in data
    assert data["operational_baseline"]["status"] in ["healthy", "attention", "incident"]


def test_diagnostics_reports_actionable_queue_and_wal_findings(
    client, db_session, monkeypatch
):
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
    assert data["queue"]["oldest_pending"]["automation_name"] == "Diag Queue"
    assert data["queue"]["oldest_pending"]["age_seconds"] >= 1200
    components = {item["component"] for item in data["findings"]}
    assert {"database", "queue"}.issubset(components)
    assert any(item["action_code"] == "checkpoint" for item in data["findings"])
    assert data["operational_baseline"]["status"] in ["attention", "incident"]
    metrics = {item["code"]: item for item in data["operational_baseline"]["metrics"]}
    assert metrics["wal_size"]["status"] == "attention"
    assert metrics["pending_queue_age"]["status"] in ["attention", "incident"]


def test_system_overview_exposes_contract_version(client):
    res = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["contract_version"] == ORCHESTRATOR_CONTRACT_VERSION


def test_system_version_exposes_contract_version(client):
    res = client.get("/api/system/version", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["contract_version"] == ORCHESTRATOR_CONTRACT_VERSION


def test_system_history_endpoint_returns_snapshots(client, db_session):
    from app import models
    from app.timezone import get_now_local

    db_session.add(
        models.SystemHealthSnapshot(
            timestamp=get_now_local(),
            overall_status="degraded",
            pending_count=2,
            running_count=1,
            oldest_pending_age_seconds=120.0,
            oldest_running_age_seconds=30.0,
            wal_size_mb=12.5,
            worker_last_ping_age_seconds=20.0,
            running_over_runtime_count=0,
            orphaned_running_count=0,
            failure_hotspots='["Auto A"]',
            active_queue_groups='["financeiro"]',
            slo_breaches='{"pending_stalled": false}',
        )
    )
    db_session.commit()

    res = client.get("/api/system/history?hours=24", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["points"] >= 1
    assert data["trend_summary"]["points"] >= 1
    assert data["items"][0]["overall_status"] == "degraded"
    assert data["items"][0]["active_queue_groups"] == ["financeiro"]
    assert data["items"][0]["baseline_status"] in ["healthy", "attention", "incident"]
    assert "baseline_attention_points" in data["trend_summary"]
    assert "baseline_incident_points" in data["trend_summary"]


def test_operational_baseline_endpoint_returns_summary(client):
    res = client.get("/api/system/baseline", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["healthy", "attention", "incident"]
    assert "metrics" in data
    assert any(item["code"] == "wal_size" for item in data["metrics"])
    assert "recommended_action" in data


def test_diagnostics_offline_worker_prefers_recovery_action(
    client, db_session, monkeypatch
):
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
    monkeypatch.setattr(
        system_router,
        "_launch_orchestrator_recovery",
        lambda: "Recover-Orchestrator.ps1",
    )

    res = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    worker_findings = [
        item for item in data["findings"] if item["component"] == "worker"
    ]
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
    assert "portfolio" in data
    assert data["portfolio"]["status"] in ["healthy", "attention", "incident"]
    assert "diagnostics" in data
    assert data["diagnostics"]["overall_status"] in ["healthy", "degraded", "unhealthy"]
    assert "findings" in data["diagnostics"]


def test_system_overview_exposes_automation_operational_metrics(client, db_session):
    from app import models
    from app.timezone import get_now_local

    auto = models.Automation(name="Metrics Auto", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add(
        models.Execution(
            id="EXEC_METRIC_SUCCESS",
            automation_id=auto.id,
            status="SUCCESS",
            duration_seconds=120,
            requested_by="TEST",
            started_at=now - timedelta(minutes=30),
            finished_at=now - timedelta(minutes=28),
        )
    )
    db_session.add(
        models.Execution(
            id="EXEC_METRIC_TIMEOUT",
            automation_id=auto.id,
            status="TIMEOUT",
            duration_seconds=600,
            requested_by="TEST",
            started_at=now - timedelta(minutes=20),
            finished_at=now - timedelta(minutes=10),
        )
    )
    db_session.commit()

    res = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert res.status_code == 200
    autos = res.json()["automations"]
    target = next(item for item in autos if item["name"] == "Metrics Auto")
    assert target["success_24h"] >= 1
    assert target["failures_24h"] >= 1
    assert target["timeouts_24h"] >= 1
    assert target["avg_duration_24h_seconds"] is not None
    assert target["schedule_summary"] == "Manual"
    assert target["last_execution_id"] is not None
    assert target["operational_state"] in ["attention", "healthy", "in_progress", "idle", "paused"]


def test_wait_for_task_requires_api_key(client):
    res = client.get("/api/system/wait-for-task")
    assert res.status_code == 403


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
    assert res.json()["validated"] is True
    assert res.json()["audit_id"] is not None


def test_system_router_project_root_points_to_repo_root():
    import app.routers.system as system_router

    expected_root = Path(__file__).resolve().parents[2]
    assert Path(system_router.PROJECT_ROOT).resolve() == expected_root.resolve()
