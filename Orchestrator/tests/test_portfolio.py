"""Testes dos endpoints de catálogo governado do portfólio."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import app.routers.portfolio as portfolio_router
from app import models
from app.timezone import get_now_local
from conftest import AUTH_HEADERS


def _create_catalog_automation(  # pylint: disable=too-many-arguments
    root: Path,
    *,
    folder_name: str,
    catalog_id: str,
    slug: str,
    criticality: str = "high",
    queue_group: str = "oracle",
    runbook: bool = True,
    smoke_tests: list[str] | None = None,
) -> dict[str, Any]:
    auto_dir = root / folder_name
    docs_dir = root / "docs" / "runbooks"
    auto_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    (auto_dir / "README.md").write_text(
        f"# {folder_name}\n\nAutomação de teste.\n", encoding="utf-8"
    )
    (auto_dir / "CONTEXT.md").write_text(
        f"# Contexto {folder_name}\n", encoding="utf-8"
    )
    (auto_dir / "run.ps1").write_text("Write-Host 'Teste'\n", encoding="utf-8")

    runbook_path = root / "docs" / "runbooks" / f"{slug}-runbook.md"
    if runbook:
        runbook_path.write_text(
            f"# Runbook {folder_name}\n\nProcedimento oficial.\n", encoding="utf-8"
        )

    manifest = {
        "id": catalog_id,
        "name": folder_name,
        "slug": slug,
        "criticality": criticality,
        "sla_minutes": 180,
        "owner_area": "Operação Fiscal",
        "entrypoint": "run.ps1",
        "runtime": "powershell",
        "channels": ["email"],
        "queue_group": queue_group,
        "max_runtime_minutes": 30,
        "max_retries": 2,
        "schedule_summary": "Manual",
        "runbook_path": f"docs/runbooks/{slug}-runbook.md",
        "context_path": f"{folder_name}/CONTEXT.md",
        "readme_path": f"{folder_name}/README.md",
        "orchestrator": {"script_path": f"./{folder_name}/run.ps1"},
        "dependencies": {
            "oracle": True,
            "outlook": True,
            "whatsapp": False,
        },
        "smoke_tests": smoke_tests or [],
    }
    (auto_dir / "automation.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def test_portfolio_health_endpoint_reports_manifest_and_runtime_state(
    client: Any, db_session: Any, monkeypatch: Any, tmp_path: Path
) -> None:

    manifest = _create_catalog_automation(
        tmp_path,
        folder_name="Auto Governada",
        catalog_id="AG-01",
        slug="auto-governada",
    )
    monkeypatch.setattr(portfolio_router, "PROJECT_ROOT", str(tmp_path))

    auto = models.Automation(
        name=manifest["name"],
        script_path=manifest["orchestrator"]["script_path"],
        queue_group=manifest["queue_group"],
        max_runtime_minutes=manifest["max_runtime_minutes"],
        max_retries=manifest["max_retries"],
        sla_minutes=manifest["sla_minutes"],
        notification_channels="email",
        enabled=True,
    )
    db_session.add(auto)
    db_session.flush()
    db_session.add(
        models.Execution(
            id="EXEC_PORTFOLIO_SUCCESS",
            automation_id=auto.id,
            status="SUCCESS",
            requested_by="TEST",
            started_at=get_now_local() - timedelta(minutes=20),
            finished_at=get_now_local() - timedelta(minutes=18),
            duration_seconds=120,
        )
    )
    db_session.commit()

    response = client.get("/api/portfolio/health", headers=AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["governed_items"] == 1
    assert payload["summary"]["drift_items"] == 0
    assert payload["summary"]["status"] == "healthy"
    assert payload["summary"]["healthy_items"] == 1
    assert payload["summary"]["incident_items"] == 0
    assert payload["summary"]["recommended_action"] is None
    item = payload["items"][0]
    assert item["catalog_id"] == "AG-01"
    assert item["criticality"] == "high"
    assert item["docs_status"] == "complete"
    assert item["drift_count"] == 0
    assert item["enabled"] is True
    assert item["dependency_status"]["oracle"] == "healthy"
    assert item["runbook_path"] == "docs/runbooks/auto-governada-runbook.md"
    assert item["review_status"] == "active"
    assert item["schedule_lag_seconds"] is None
    assert item["last_success_age_seconds"] is not None
    assert item["last_failure_age_seconds"] is None


def test_portfolio_drift_endpoint_reports_runtime_mismatch_and_missing_docs(
    client: Any, db_session: Any, monkeypatch: Any, tmp_path: Path
) -> None:

    manifest = _create_catalog_automation(
        tmp_path,
        folder_name="Auto com Drift",
        catalog_id="AD-02",
        slug="auto-com-drift",
        queue_group="oracle",
        runbook=False,
    )
    monkeypatch.setattr(portfolio_router, "PROJECT_ROOT", str(tmp_path))

    auto = models.Automation(
        name=manifest["name"],
        script_path=manifest["orchestrator"]["script_path"],
        queue_group="financeiro",
        max_runtime_minutes=15,
        max_retries=0,
        sla_minutes=60,
        notification_channels="whatsapp",
        enabled=True,
    )
    db_session.add(auto)
    db_session.commit()

    response = client.get("/api/portfolio/drift", headers=AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["items_with_drift"] >= 1

    item = payload["items"][0]
    issue_codes = {issue["code"] for issue in item["issues"]}
    assert "queue_group_mismatch" in issue_codes
    assert "max_runtime_mismatch" in issue_codes
    assert "max_retries_mismatch" in issue_codes
    assert "sla_mismatch" in issue_codes
    assert "notification_channels_mismatch" in issue_codes
    assert "runbook_missing" in issue_codes


def test_portfolio_health_summary_escalates_catalog_drift_for_high_criticality(
    client: Any, db_session: Any, monkeypatch: Any, tmp_path: Path
) -> None:

    manifest = _create_catalog_automation(
        tmp_path,
        folder_name="Auto Critica",
        catalog_id="AC-04",
        slug="auto-critica",
        criticality="high",
        queue_group="oracle",
        runbook=False,
    )
    monkeypatch.setattr(portfolio_router, "PROJECT_ROOT", str(tmp_path))

    auto = models.Automation(
        name=manifest["name"],
        script_path=manifest["orchestrator"]["script_path"],
        queue_group="financeiro",
        max_runtime_minutes=15,
        max_retries=0,
        sla_minutes=60,
        notification_channels="whatsapp",
        enabled=True,
    )
    db_session.add(auto)
    db_session.commit()

    response = client.get("/api/portfolio/health", headers=AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "incident"
    assert payload["summary"]["incident_items"] >= 1
    assert payload["summary"]["drift_items"] >= 1
    assert payload["summary"]["docs_missing_items"] >= 1
    assert payload["summary"]["recommended_action"] is not None
    assert payload["summary"]["top_issue"] is not None


def test_portfolio_runbook_endpoint_returns_markdown(
    client: Any, monkeypatch: Any, tmp_path: Path
) -> None:

    _create_catalog_automation(
        tmp_path,
        folder_name="Auto Runbook",
        catalog_id="AR-03",
        slug="auto-runbook",
    )
    monkeypatch.setattr(portfolio_router, "PROJECT_ROOT", str(tmp_path))

    response = client.get("/api/portfolio/runbook/AR-03", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert "# Runbook Auto Runbook" in response.text


def test_portfolio_marks_runtime_only_disabled_automation_as_delete_candidate(
    client: Any, db_session: Any
) -> None:

    auto = models.Automation(
        name="Cadastro Orfao",
        script_path="./test/run.ps1",
        enabled=False,
    )
    db_session.add(auto)
    db_session.commit()

    response = client.get("/api/portfolio/health", headers=AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()

    item = next(
        entry for entry in payload["items"] if entry["name"] == "Cadastro Orfao"
    )
    assert item["review_status"] == "delete_candidate"
    assert any("sem manifesto" in reason.lower() for reason in item["review_reasons"])
    assert payload["summary"]["delete_candidate_items"] >= 1
