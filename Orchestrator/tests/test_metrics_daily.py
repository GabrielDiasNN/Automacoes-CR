"""Testes de métricas diárias agregadas (Fase 3 do plano Monitor/Beneficiamento)."""

from typing import Any

from app import models
from app.services.metrics_queries import get_daily_execution_metrics
from app.timezone import get_now_local
from conftest import AUTH_HEADERS


def _make_automation(db_session: Any) -> int:
    auto = models.Automation(name="Metrics Daily Auto", script_path="./test/run.ps1")
    db_session.add(auto)
    db_session.flush()
    return int(auto.id)


def test_get_daily_execution_metrics_empty(db_session: Any) -> None:
    assert not get_daily_execution_metrics(db_session, days=14)


def test_get_daily_execution_metrics_aggregates_single_day(db_session: Any) -> None:
    automation_id = _make_automation(db_session)
    now = get_now_local()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_DAILY_1",
                automation_id=automation_id,
                status="SUCCESS",
                started_at=now,
                duration_seconds=10.0,
            ),
            models.Execution(
                id="EXEC_DAILY_2",
                automation_id=automation_id,
                status="SUCCESS",
                started_at=now,
                duration_seconds=20.0,
            ),
            models.Execution(
                id="EXEC_DAILY_3",
                automation_id=automation_id,
                status="ERROR",
                started_at=now,
                duration_seconds=30.0,
            ),
        ]
    )
    db_session.commit()

    items = get_daily_execution_metrics(db_session, days=1)

    assert len(items) == 1
    day = items[0]
    assert day["total"] == 3
    assert day["success"] == 2
    assert day["errors"] == 1
    assert day["success_rate_pct"] == 66.67
    assert day["avg_duration_seconds"] == 20.0
    assert day["p95_duration_seconds"] == 30.0


def test_get_daily_execution_metrics_pending_has_no_terminal_rate(
    db_session: Any,
) -> None:
    automation_id = _make_automation(db_session)
    db_session.add(
        models.Execution(
            id="EXEC_DAILY_PENDING",
            automation_id=automation_id,
            status="PENDING",
            started_at=get_now_local(),
        )
    )
    db_session.commit()

    items = get_daily_execution_metrics(db_session, days=1)

    assert len(items) == 1
    assert items[0]["total"] == 1
    assert items[0]["success"] == 0
    assert items[0]["errors"] == 0
    assert items[0]["success_rate_pct"] is None
    assert items[0]["avg_duration_seconds"] is None
    assert items[0]["p95_duration_seconds"] is None


def test_system_metrics_daily_endpoint_returns_payload(
    client: Any, db_session: Any
) -> None:
    automation_id = _make_automation(db_session)
    db_session.add(
        models.Execution(
            id="EXEC_DAILY_ENDPOINT",
            automation_id=automation_id,
            status="SUCCESS",
            started_at=get_now_local(),
            duration_seconds=5.0,
        )
    )
    db_session.commit()

    res = client.get("/api/system/metrics/daily?days=7", headers=AUTH_HEADERS)

    assert res.status_code == 200
    data = res.json()
    assert data["days"] == 7
    assert len(data["items"]) == 1
    assert data["items"][0]["total"] == 1
    assert data["items"][0]["success"] == 1


def test_system_metrics_daily_endpoint_default_days(client: Any) -> None:
    res = client.get("/api/system/metrics/daily", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["days"] == 14


def test_system_metrics_daily_endpoint_rejects_out_of_bounds_days(
    client: Any,
) -> None:
    assert (
        client.get("/api/system/metrics/daily?days=0", headers=AUTH_HEADERS).status_code
        == 422
    )
    assert (
        client.get(
            "/api/system/metrics/daily?days=91", headers=AUTH_HEADERS
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/system/metrics/daily?days=90", headers=AUTH_HEADERS
        ).status_code
        == 200
    )
