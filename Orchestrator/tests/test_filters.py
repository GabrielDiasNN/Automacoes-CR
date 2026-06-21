# pylint: disable=all
# mypy: ignore-errors
"""
Suite dedicada aos filtros do Orchestrator.

Cobre:
1. Busca/ordenação da listagem de automações.
2. Todos os filtros expostos em /api/executions.
3. Filtro de ação no audit log do sistema.
"""

from datetime import timedelta

from app import models
from app.timezone import get_now_local
from conftest import AUTH_HEADERS


def test_list_automations_search_and_sort(client):
    client.post(
        "/api/automations",
        json={"name": "Receitas Oracle", "script_path": "./test/run.ps1"},
        headers=AUTH_HEADERS,
    )
    client.post(
        "/api/automations",
        json={"name": "Fiscal Oracle", "script_path": "./test/run1.ps1"},
        headers=AUTH_HEADERS,
    )
    client.post(
        "/api/automations",
        json={"name": "WhatsApp Alerts", "script_path": "./test/run2.ps1"},
        headers=AUTH_HEADERS,
    )

    res = client.get(
        "/api/automations?search=oracle&sort=name&order=desc&per_page=10",
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    names = [item["name"] for item in data["items"]]
    assert names == ["Receitas Oracle", "Fiscal Oracle"]


def test_list_executions_supports_all_filters_combined(client, db_session):
    auto_fin = models.Automation(
        name="Financeiro Diario",
        script_path="./test/run.ps1",
        queue_group="financeiro",
    )
    auto_ops = models.Automation(
        name="Operacional Noturno",
        script_path="./test/run1.ps1",
        queue_group="operacional",
    )
    db_session.add_all([auto_fin, auto_ops])
    db_session.flush()

    now = get_now_local()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_FILTER_TARGET",
                automation_id=auto_fin.id,
                status="ERROR",
                priority="HIGH",
                retry_count=0,
                max_retries=2,
                queue_group="financeiro",
                requested_by="Operador QA",
                started_at=now - timedelta(hours=1),
            ),
            models.Execution(
                id="EXEC_FILTER_WRONG_DATE",
                automation_id=auto_fin.id,
                status="ERROR",
                priority="HIGH",
                retry_count=0,
                max_retries=2,
                queue_group="financeiro",
                requested_by="Operador QA",
                started_at=now - timedelta(days=3),
            ),
            models.Execution(
                id="EXEC_FILTER_WRONG_STATUS",
                automation_id=auto_fin.id,
                status="SUCCESS",
                priority="HIGH",
                retry_count=0,
                max_retries=2,
                queue_group="financeiro",
                requested_by="Operador QA",
                started_at=now - timedelta(hours=1),
                finished_at=now - timedelta(minutes=55),
            ),
            models.Execution(
                id="EXEC_FILTER_WRONG_PRIORITY",
                automation_id=auto_fin.id,
                status="ERROR",
                priority="LOW",
                retry_count=0,
                max_retries=2,
                queue_group="financeiro",
                requested_by="Operador QA",
                started_at=now - timedelta(hours=1),
            ),
            models.Execution(
                id="EXEC_FILTER_WRONG_GROUP",
                automation_id=auto_ops.id,
                status="ERROR",
                priority="HIGH",
                retry_count=0,
                max_retries=2,
                queue_group="operacional",
                requested_by="Operador QA",
                started_at=now - timedelta(hours=1),
            ),
            models.Execution(
                id="EXEC_FILTER_WRONG_REQUESTER",
                automation_id=auto_fin.id,
                status="ERROR",
                priority="HIGH",
                retry_count=0,
                max_retries=2,
                queue_group="financeiro",
                requested_by="SYSTEM",
                started_at=now - timedelta(hours=1),
            ),
        ]
    )
    db_session.commit()

    date_from = (now - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    date_to = now.strftime("%Y-%m-%dT23:59:59")
    res = client.get(
        "/api/executions"
        f"?status=ERROR&automation_id={auto_fin.id}&queue_group=financeiro"
        "&priority=HIGH&requested_by=operador"
        f"&date_from={date_from}&date_to={date_to}&per_page=20",
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == ["EXEC_FILTER_TARGET"]


def test_list_executions_date_filters_can_return_empty_result(client, db_session):
    auto = models.Automation(
        name="Filtro Janela",
        script_path="./test/run.ps1",
        queue_group="janela",
    )
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add(
        models.Execution(
            id="EXEC_DATE_WINDOW",
            automation_id=auto.id,
            status="SUCCESS",
            requested_by="QA",
            started_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2, minutes=-1),
            duration_seconds=60,
        )
    )
    db_session.commit()

    future_from = (now + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00")
    future_to = (now + timedelta(days=5)).strftime("%Y-%m-%dT23:59:59")
    res = client.get(
        f"/api/executions?date_from={future_from}&date_to={future_to}",
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 0
    assert payload["items"] == []


def test_system_audit_filter_returns_only_requested_action(client, db_session):
    now = get_now_local()
    db_session.add_all(
        [
            models.AuditLog(
                action="CREATE",
                entity_type="AUTOMATION",
                entity_id="1",
                actor="QA",
                details="create event",
                timestamp=now - timedelta(minutes=2),
            ),
            models.AuditLog(
                action="UPDATE",
                entity_type="AUTOMATION",
                entity_id="1",
                actor="QA",
                details="update event",
                timestamp=now - timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()

    res = client.get("/api/system/audit?action=update&limit=20", headers=AUTH_HEADERS)
    assert res.status_code == 200
    items = res.json()
    assert items
    assert all(item["action"] == "UPDATE" for item in items)


def test_list_executions_pagination_filters_respect_page_boundaries(client, db_session):
    auto = models.Automation(
        name="Filtro Paginado",
        script_path="./test/run.ps1",
        queue_group="paginado",
    )
    db_session.add(auto)
    db_session.flush()
    now = get_now_local()
    db_session.add_all(
        [
            models.Execution(
                id="EXEC_PAGE_1",
                automation_id=auto.id,
                status="ERROR",
                priority="HIGH",
                queue_group="paginado",
                requested_by="QA",
                started_at=now - timedelta(minutes=1),
            ),
            models.Execution(
                id="EXEC_PAGE_2",
                automation_id=auto.id,
                status="ERROR",
                priority="HIGH",
                queue_group="paginado",
                requested_by="QA",
                started_at=now - timedelta(minutes=2),
            ),
            models.Execution(
                id="EXEC_PAGE_3",
                automation_id=auto.id,
                status="ERROR",
                priority="HIGH",
                queue_group="paginado",
                requested_by="QA",
                started_at=now - timedelta(minutes=3),
            ),
        ]
    )
    db_session.commit()

    page_1 = client.get(
        "/api/executions?status=ERROR&queue_group=paginado&priority=HIGH&page=1&per_page=2",
        headers=AUTH_HEADERS,
    )
    assert page_1.status_code == 200
    payload_1 = page_1.json()
    assert payload_1["total"] == 3
    assert payload_1["pages"] == 2
    assert [item["id"] for item in payload_1["items"]] == ["EXEC_PAGE_1", "EXEC_PAGE_2"]

    page_2 = client.get(
        "/api/executions?status=ERROR&queue_group=paginado&priority=HIGH&page=2&per_page=2",
        headers=AUTH_HEADERS,
    )
    assert page_2.status_code == 200
    payload_2 = page_2.json()
    assert [item["id"] for item in payload_2["items"]] == ["EXEC_PAGE_3"]


def test_list_executions_rejects_invalid_pagination_filter_values(client):
    page_res = client.get("/api/executions?page=0", headers=AUTH_HEADERS)
    assert page_res.status_code == 422
    assert "page deve ser >= 1" in page_res.json()["detail"]

    per_page_res = client.get("/api/executions?per_page=201", headers=AUTH_HEADERS)
    assert per_page_res.status_code == 422
    assert "per_page deve estar entre 1 e 200" in per_page_res.json()["detail"]


def test_list_executions_rejects_invalid_status_priority_and_dates(client):
    invalid_status = client.get("/api/executions?status=UNKNOWN", headers=AUTH_HEADERS)
    assert invalid_status.status_code == 422
    assert "status inválido" in invalid_status.json()["detail"]

    invalid_priority = client.get(
        "/api/executions?priority=URGENT", headers=AUTH_HEADERS
    )
    assert invalid_priority.status_code == 422
    assert "priority inválida" in invalid_priority.json()["detail"]

    invalid_date = client.get(
        "/api/executions?date_from=2026/05/21", headers=AUTH_HEADERS
    )
    assert invalid_date.status_code == 422
    assert "date_from inválido" in invalid_date.json()["detail"]

    inverted_range = client.get(
        "/api/executions?date_from=2026-05-22T00:00:00&date_to=2026-05-21T00:00:00",
        headers=AUTH_HEADERS,
    )
    assert inverted_range.status_code == 422
    assert "date_from não pode ser maior que date_to" in inverted_range.json()["detail"]
