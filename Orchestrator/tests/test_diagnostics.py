# pylint: disable=all
# mypy: ignore-errors
"""
Suite de testes focado em diagnósticos de sistema e saúde da fila (Fase 5.3).

Valida:
1. Detecção de worker offline baseado no atraso de heartbeat.
2. Diagnóstico de fila parada ou execuções lentas envelhecidas.
3. Alerta de risco do WAL elevado do banco SQLite.
"""

from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.constants import (
    ACTION_CODE_CHECKPOINT,
    DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS,
    DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
)
from app.timezone import get_now_local
from tests.conftest import AUTH_HEADERS


def test_diagnostics_worker_offline(client: TestClient, db_session: Session):
    """Garante que um worker sem ping recente seja classificado como offline no diagnóstico."""
    # Criar um heartbeat muito antigo (ex: 2 minutos atrás, limite é 30s)
    old_ping = get_now_local() - timedelta(minutes=2)
    hb = models.WorkerHeartbeat(
        id=1,
        last_ping=old_ping,
        pid=1234,
    )
    db_session.add(hb)
    db_session.commit()

    response = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()

    # overall_status deve ser degraded ou unhealthy
    assert data["overall_status"] in ["degraded", "unhealthy"]
    
    # Encontrar a descoberta sobre o worker sem heartbeat
    findings = [f for f in data["findings"] if f["component"] == "worker"]
    assert len(findings) > 0
    assert "Worker sem heartbeat recente" in findings[0]["message"]


def test_diagnostics_stalled_queue(client: TestClient, db_session: Session):
    """Verifica se execuções pendentes ou em execução há muito tempo ativam alertas de fila parada."""
    # Criar automação de teste
    auto = models.Automation(
        id=903,
        name="Automacao Diagnostico",
        script_path="Orchestrator/tests/test/run1.ps1",
        enabled=True,
    )
    db_session.add(auto)
    db_session.commit()

    # Criar execução pendente há 20 minutos (limite para alerta é 15 minutos / 900s)
    stalled_time = get_now_local() - timedelta(minutes=20)
    exec_stalled = models.Execution(
        id="STALLED_001",
        automation_id=903,
        status=EXECUTION_STATUS_PENDING,
        started_at=stalled_time,  # started_at ou data de criação servem como marco
    )
    db_session.add(exec_stalled)
    db_session.commit()

    response = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()

    # Deve conter um finding relacionado à fila (queue)
    queue_findings = [f for f in data["findings"] if f["component"] == "queue"]
    assert len(queue_findings) > 0
    assert "Execução pendente há" in queue_findings[0]["message"]


def test_diagnostics_wal_risk(client: TestClient, db_session: Session):
    """Garante que um arquivo WAL do SQLite excessivamente grande seja sinalizado com risco crítico."""
    # Fazer mock do get_wal_size_mb no router de system
    import app.routers.system as system_router
    
    original_get_wal = system_router.get_wal_size_mb
    # Simular WAL gigante com 300 MB (limite para erro é 256 MB)
    system_router.get_wal_size_mb = lambda: 300.0

    try:
        response = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()

        # overall_status deve ser degraded ou unhealthy
        assert data["overall_status"] in ["degraded", "unhealthy"]

        # Procurar o achado do WAL elevado
        db_findings = [f for f in data["findings"] if f["component"] == "database" and "WAL" in f["message"]]
        assert len(db_findings) > 0
        assert db_findings[0]["severity"] == "ERROR"
        assert db_findings[0]["action_code"] == ACTION_CODE_CHECKPOINT
    finally:
        # Restaurar a função original
        system_router.get_wal_size_mb = original_get_wal


def test_diagnostics_running_over_max_runtime(client: TestClient, db_session: Session):
    """Diagnóstico deve diferenciar execução longa legítima de RUNNING acima do max_runtime."""
    auto = models.Automation(
        id=904,
        name="Automacao Travada",
        script_path="Orchestrator/tests/test/run1.ps1",
        max_runtime_minutes=5,
        enabled=True,
    )
    db_session.add(auto)
    db_session.commit()

    old_start = get_now_local() - timedelta(minutes=20)
    execution = models.Execution(
        id="RUNNING_STALE_001",
        automation_id=904,
        status=EXECUTION_STATUS_RUNNING,
        started_at=old_start,
    )
    db_session.add(execution)
    db_session.commit()

    response = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()

    assert data["queue"]["running_over_runtime"][0]["exec_id"] == "RUNNING_STALE_001"
    checks = {item["code"]: item for item in data["checks"]}
    assert checks["running_over_runtime"]["status"] == "warn"
    queue_findings = [f for f in data["findings"] if f["component"] == "queue"]
    assert any("max_runtime" in finding["message"] for finding in queue_findings)
    assert data["slo"]["thresholds"]["pending_stalled_warn_seconds"] == DIAGNOSTIC_PENDING_STALLED_WARN_SECONDS
    assert (
        data["slo"]["thresholds"]["running_over_runtime_grace_seconds"]
        == DIAGNOSTIC_RUNNING_OVER_RUNTIME_GRACE_SECONDS
    )
    assert data["slo"]["breaches"]["running_over_runtime"] is True
    baseline_metrics = {
        item["code"]: item for item in data["operational_baseline"]["metrics"]
    }
    assert baseline_metrics["running_over_runtime"]["status"] in ["attention", "incident"]


def test_diagnostics_queue_risk_summary(client: TestClient, db_session: Session):
    auto = models.Automation(
        id=905,
        name="Fila Pressionada",
        script_path="Orchestrator/tests/test/run1.ps1",
        enabled=True,
        queue_group="financeiro",
    )
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add(
        models.Execution(
            id="QUEUE_RETRY_001",
            automation_id=905,
            status=EXECUTION_STATUS_PENDING,
            priority="HIGH",
            retry_count=1,
            queue_group="financeiro",
            started_at=now - timedelta(minutes=2),
        )
    )
    db_session.add(
        models.Execution(
            id="QUEUE_TIMEOUT_001",
            automation_id=905,
            status="TIMEOUT",
            priority="HIGH",
            retry_count=0,
            queue_group="financeiro",
            started_at=now - timedelta(minutes=30),
        )
    )
    db_session.commit()

    response = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["queue"]["retry_pressure"]
    assert data["queue"]["timeouts_24h_by_group"]
    assert data["performance"]["timings_ms"]["queue_metrics_ms"] >= 0
    assert data["performance"]["timings_ms"]["total_ms"] >= 0


def test_diagnostics_operational_baseline_marks_orphaned_running_as_incident(
    client: TestClient, db_session: Session, monkeypatch
):
    from app import models
    from app.schemas import WorkerStatus

    auto = models.Automation(
        id=906,
        name="Ownership Quebrado",
        script_path="Orchestrator/tests/test/run1.ps1",
        enabled=True,
    )
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="RUNNING_ORPHAN_001",
            automation_id=906,
            status=EXECUTION_STATUS_RUNNING,
            started_at=get_now_local() - timedelta(minutes=10),
            worker_instance_id="worker-antigo",
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.routers.system._get_worker_status",
        lambda db: WorkerStatus(
            is_alive=False,
            pid=4040,
            instance_id="worker-atual",
            last_ping=None,
            tasks_completed=0,
            tasks_failed=0,
            active_tasks=0,
            version="9.3.0",
        ),
    )

    response = client.get("/api/system/diagnostics", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    metrics = {item["code"]: item for item in data["operational_baseline"]["metrics"]}
    assert metrics["orphaned_running"]["status"] == "incident"
    assert data["operational_baseline"]["status"] == "incident"
