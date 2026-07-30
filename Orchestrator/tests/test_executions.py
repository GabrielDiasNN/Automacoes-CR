"""
Testes focados nas operações e controle de Execuções do Orchestrator.
"""

from datetime import timedelta

from app import models
from app.timezone import get_now_local
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_start_automation_creates_pending(client: TestClient) -> None:
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


def test_reject_duplicate_execution(client: TestClient) -> None:
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


def test_stop_execution(client: TestClient) -> None:
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


def test_list_recent_executions(client: TestClient) -> None:
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
    payload = res.json()
    assert len(payload) >= 1
    assert "operator_action_label" in payload[0]
    assert "requeue_allowed" in payload[0]


def test_execution_summary_exposes_operator_triage_fields(
    client: TestClient, db_session: Session
) -> None:

    auto = models.Automation(
        name="Operator Summary",
        script_path="./test/run.ps1",
        max_retries=2,
        queue_group="financeiro",
    )
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_TRIAGE_SUMMARY",
            automation_id=auto.id,
            status="ERROR",
            retry_count=0,
            max_retries=2,
            queue_group="financeiro",
            failure_reason="EXIT_CODE_12",
            requested_by="QA",
            started_at=get_now_local() - timedelta(minutes=3),
        )
    )
    db_session.commit()

    res = client.get("/api/executions?page=1&per_page=10", headers=AUTH_HEADERS)
    assert res.status_code == 200
    item = next(
        entry for entry in res.json()["items"] if entry["id"] == "EXEC_TRIAGE_SUMMARY"
    )
    assert item["operator_action_label"] == "Reenfileirar"
    assert item["requeue_allowed"] is True
    assert item["operator_attention_required"] is True
    assert item["related_queue_group"] == "financeiro"
    assert item["operator_severity"] in ["CRITICAL", "HIGH", "MODERATE", "NORMAL"]
    assert item["operator_score"] >= 20
    assert item["operator_reason_summary"]


def test_execution_summary_keeps_success_rows_compact_when_healthy(
    client: TestClient, db_session: Session
) -> None:

    auto = models.Automation(
        name="Healthy Success",
        script_path="./test/run.ps1",
        max_retries=3,
        queue_group="sucesso",
    )
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add(
        models.Execution(
            id="EXEC_HEALTHY_SUCCESS",
            automation_id=auto.id,
            status="SUCCESS",
            retry_count=0,
            max_retries=3,
            queue_group="sucesso",
            requested_by="QA",
            started_at=now - timedelta(minutes=2),
            finished_at=now - timedelta(minutes=1),
            duration_seconds=14,
        )
    )
    db_session.commit()

    res = client.get("/api/executions?page=1&per_page=10", headers=AUTH_HEADERS)
    assert res.status_code == 200
    item = next(
        entry for entry in res.json()["items"] if entry["id"] == "EXEC_HEALTHY_SUCCESS"
    )
    assert item["requeue_allowed"] is True
    assert item["operator_attention_required"] is False
    assert item["operator_action_code"] == "REQUEUE"
    assert item["operator_action_label"] is None
    assert item["operator_reason_summary"] is None
    assert item["operator_score"] == 0
    assert item["operator_severity"] == "NORMAL"


def test_execution_summary_blocks_requeue_for_success_with_active_conflict(
    client: TestClient, db_session: Session
) -> None:
    """SUCCESS não deve oferecer reenfileirar se já há execução ativa no grupo (#dashboard-log-review)."""
    auto = models.Automation(
        name="Success With Conflict",
        script_path="./test/run.ps1",
        max_retries=3,
        queue_group="conflito",
    )
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add(
        models.Execution(
            id="EXEC_SUCCESS_CONFLICT",
            automation_id=auto.id,
            status="SUCCESS",
            retry_count=0,
            max_retries=3,
            queue_group="conflito",
            requested_by="QA",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            duration_seconds=14,
        )
    )
    db_session.add(
        models.Execution(
            id="EXEC_SUCCESS_CONFLICT_ACTIVE",
            automation_id=auto.id,
            status="RUNNING",
            retry_count=0,
            max_retries=3,
            queue_group="conflito",
            requested_by="QA",
            started_at=now - timedelta(seconds=30),
        )
    )
    db_session.commit()

    res = client.get("/api/executions?page=1&per_page=10", headers=AUTH_HEADERS)
    assert res.status_code == 200
    item = next(
        entry for entry in res.json()["items"] if entry["id"] == "EXEC_SUCCESS_CONFLICT"
    )
    assert item["requeue_allowed"] is False
    assert item["requeue_block_reason"]


def test_list_executions_filters_by_queue_group(
    client: TestClient, db_session: Session
) -> None:

    auto_a = models.Automation(
        name="Grupo A", script_path="./test/run.ps1", queue_group="grupo_a"
    )
    auto_b = models.Automation(
        name="Grupo B", script_path="./test/run2.ps1", queue_group="grupo_b"
    )
    db_session.add_all([auto_a, auto_b])
    db_session.flush()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_GRUPO_A",
                automation_id=auto_a.id,
                status="ERROR",
                queue_group="grupo_a",
                requested_by="QA",
                started_at=get_now_local(),
            ),
            models.Execution(
                id="EXEC_GRUPO_B",
                automation_id=auto_b.id,
                status="ERROR",
                queue_group="grupo_b",
                requested_by="QA",
                started_at=get_now_local(),
            ),
        ]
    )
    db_session.commit()

    res = client.get("/api/executions?queue_group=grupo_a", headers=AUTH_HEADERS)
    assert res.status_code == 200
    items = res.json()["items"]
    assert any(item["id"] == "EXEC_GRUPO_A" for item in items)
    assert all(item["related_queue_group"] == "grupo_a" for item in items)


def test_list_executions_filters_by_priority(
    client: TestClient, db_session: Session
) -> None:

    auto = models.Automation(name="Filtro Prioridade", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_PRIORITY_HIGH",
                automation_id=auto.id,
                status="ERROR",
                priority="HIGH",
                requested_by="QA",
                started_at=get_now_local(),
            ),
            models.Execution(
                id="EXEC_PRIORITY_LOW",
                automation_id=auto.id,
                status="ERROR",
                priority="LOW",
                requested_by="QA",
                started_at=get_now_local(),
            ),
        ]
    )
    db_session.commit()

    res = client.get("/api/executions?priority=HIGH", headers=AUTH_HEADERS)
    assert res.status_code == 200
    items = res.json()["items"]
    assert any(item["id"] == "EXEC_PRIORITY_HIGH" for item in items)
    assert all(item["priority"] == "HIGH" for item in items)


def test_execution_requeue_creates_auditable_pending_retry(
    client: TestClient, db_session: Session
) -> None:

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

    source = (
        db_session.query(models.Execution)
        .filter(models.Execution.id == "EXEC_RETRY_SRC")
        .first()
    )
    queued = (
        db_session.query(models.Execution)
        .filter(models.Execution.id == payload["queued_exec_id"])
        .first()
    )
    assert source is not None
    assert queued is not None
    assert source.status == "REQUEUED"
    assert source.recovery_action == "REQUEUED_TO_NEW_EXECUTION"
    assert queued.status == "PENDING"
    assert queued.priority == "HIGH"
    assert queued.queue_group == "oracle"
    assert queued.failure_reason == "EXIT_CODE_24"
    assert queued.recovery_action == "REQUEUE_MANUAL"


def test_execution_requeue_ignores_retry_budget(
    client: TestClient, db_session: Session
) -> None:
    """max_retries não bloqueia reenfileiramento manual — não há retry automático
    no worker que o consuma; é só histórico de tentativas (#dashboard-reenfileirar)."""

    auto = models.Automation(
        name="Retry Budget Exhausted", script_path="./test/run.ps1", max_retries=1
    )
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_RETRY_BUDGET",
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
        "/api/executions/EXEC_RETRY_BUDGET/requeue",
        json={"reason": "reprocesso manual apos esgotar budget"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["retry_count"] == 2


def test_execution_requeue_blocks_active_queue_group(
    client: TestClient, db_session: Session
) -> None:

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
