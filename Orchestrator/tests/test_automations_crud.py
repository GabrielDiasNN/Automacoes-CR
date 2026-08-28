"""
Testes focados nas operações de CRUD de Automações.
"""

import json
import os
from datetime import timedelta
from pathlib import Path

import app.routers.automations as auto_router
import pytest
from app import models, schemas
from app.runtime import scheduler
from app.services import scheduler_runtime
from app.timezone import get_now_local
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker


def test_create_automation(client: TestClient) -> None:
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


def test_preflight_automation_normalizes_channels(client: TestClient) -> None:
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
    assert data["resolved_script_path"].endswith(os.path.join("test", "run.ps1"))
    assert data["schedule_summary"] == "Manual"
    assert data["governance"]["status"] in ["healthy", "attention"]


def test_preflight_rejects_reserved_cleanup_script() -> None:
    from app.services.automation_preflight import (  # pylint: disable=import-outside-toplevel
        build_automation_preflight,
    )

    with pytest.raises(ValueError, match="rotina reservada do sistema"):
        build_automation_preflight(
            {
                "name": "Cleanup Legacy",
                "script_path": "./Tools/AplicarPoliticaRetencao.ps1",
                "enabled": True,
            },
            "C:\\Automacoes",
        )


def test_preflight_reports_manifest_drift_without_persisting(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:

    auto_dir = tmp_path / "Auto Governada"
    docs_dir = tmp_path / "docs" / "runbooks"
    auto_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (auto_dir / "README.md").write_text("# Auto Governada\n", encoding="utf-8")
    (auto_dir / "CONTEXT.md").write_text("# Contexto\n", encoding="utf-8")
    (auto_dir / "run.ps1").write_text("Write-Host 'ok'\n", encoding="utf-8")
    (docs_dir / "auto-governada-runbook.md").write_text("# Runbook\n", encoding="utf-8")
    (auto_dir / "automation.manifest.json").write_text(
        json.dumps(
            {
                "id": "AG-10",
                "name": "Auto Governada",
                "slug": "auto-governada",
                "criticality": "high",
                "owner_area": "Operação",
                "entrypoint": "run.ps1",
                "runtime": "powershell",
                "channels": ["email"],
                "queue_group": "oracle",
                "max_runtime_minutes": 30,
                "max_retries": 2,
                "schedule_summary": "Manual",
                "runbook_path": "docs/runbooks/auto-governada-runbook.md",
                "context_path": "Auto Governada/CONTEXT.md",
                "readme_path": "Auto Governada/README.md",
                "orchestrator": {"script_path": "./Auto Governada/run.ps1"},
                "dependencies": {"oracle": True, "outlook": False, "whatsapp": False},
                "smoke_tests": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))

    res = client.post(
        "/api/automations/preflight",
        json={
            "name": "Auto Governada",
            "script_path": "./Auto Governada/run.ps1",
            "queue_group": "financeiro",
            "max_runtime_minutes": 15,
            "max_retries": 0,
            "notification_channels": "whatsapp",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    assert data["governance"]["status"] == "incident"
    issue_codes = {item["code"] for item in data["governance"]["blocking_issues"]}
    assert "queue_group_mismatch" in issue_codes
    assert "max_runtime_mismatch" in issue_codes
    assert "max_retries_mismatch" in issue_codes
    assert "notification_channels_mismatch" in issue_codes


def _write_whatsapp_manifest(
    auto_dir: Path, docs_dir: Path, *, slug: str, name: str
) -> None:
    auto_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (auto_dir / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    (auto_dir / "CONTEXT.md").write_text("# Contexto\n", encoding="utf-8")
    (auto_dir / "run.ps1").write_text("Write-Host 'ok'\n", encoding="utf-8")
    (docs_dir / f"{slug}-runbook.md").write_text("# Runbook\n", encoding="utf-8")
    (auto_dir / "automation.manifest.json").write_text(
        json.dumps(
            {
                "id": "WA-99",
                "name": name,
                "slug": slug,
                "criticality": "high",
                "owner_area": "Operação",
                "entrypoint": "run.ps1",
                "runtime": "powershell",
                "channels": ["whatsapp"],
                "max_runtime_minutes": 30,
                "max_retries": 0,
                "schedule_summary": "Manual",
                "runbook_path": f"docs/runbooks/{slug}-runbook.md",
                "context_path": f"{name}/CONTEXT.md",
                "readme_path": f"{name}/README.md",
                "orchestrator": {"script_path": f"./{name}/run.ps1"},
                "dependencies": {"oracle": False, "outlook": False, "whatsapp": True},
                "smoke_tests": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_preflight_blocks_missing_whatsapp_config(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    name = "Auto WhatsApp Sem Config"
    auto_dir = tmp_path / name
    docs_dir = tmp_path / "docs" / "runbooks"
    _write_whatsapp_manifest(
        auto_dir, docs_dir, slug="auto-whatsapp-sem-config", name=name
    )
    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))

    res = client.post(
        "/api/automations/preflight",
        json={
            "name": name,
            "script_path": f"./{name}/run.ps1",
            "notification_channels": "whatsapp",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    issue_codes = {item["code"] for item in data["governance"]["blocking_issues"]}
    assert "whatsapp_config_missing" in issue_codes


def test_preflight_blocks_invalid_whatsapp_config_schema(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    name = "Auto WhatsApp Config Invalida"
    auto_dir = tmp_path / name
    docs_dir = tmp_path / "docs" / "runbooks"
    _write_whatsapp_manifest(
        auto_dir, docs_dir, slug="auto-whatsapp-config-invalida", name=name
    )
    (auto_dir / "whatsapp-config.json").write_text(
        json.dumps({"auth": {}, "target": {"type": "broadcast", "contactId": "123"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))

    res = client.post(
        "/api/automations/preflight",
        json={
            "name": name,
            "script_path": f"./{name}/run.ps1",
            "notification_channels": "whatsapp",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is False
    issue_codes = {item["code"] for item in data["governance"]["blocking_issues"]}
    assert "whatsapp_config_client_id_missing" in issue_codes
    assert "whatsapp_config_target_type_invalid" in issue_codes
    assert "whatsapp_config_contact_id_invalid" in issue_codes


@pytest.mark.parametrize(
    "automation_dir_name", ["Receitas Bloqueadas", "OBs Paradas Fase"]
)
def test_whatsapp_config_issues_accepts_real_production_configs(
    automation_dir_name: str,
) -> None:
    from app.runtime import get_project_root  # pylint: disable=import-outside-toplevel
    from app.services.automation_preflight import (  # pylint: disable=import-outside-toplevel
        _whatsapp_config_issues,
    )
    from app.services.portfolio_manifest import (  # pylint: disable=import-outside-toplevel
        CatalogManifest,
    )

    automation_dir = os.path.join(get_project_root(), automation_dir_name)
    manifest_path = os.path.join(automation_dir, "automation.manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = CatalogManifest.model_validate(json.load(f))

    assert "whatsapp" in manifest.channels
    issues = _whatsapp_config_issues(automation_dir=automation_dir, manifest=manifest)
    assert not issues


def test_create_automation_rejects_manifest_drift(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:

    auto_dir = tmp_path / "Auto Bloqueada"
    docs_dir = tmp_path / "docs" / "runbooks"
    auto_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (auto_dir / "README.md").write_text("# Auto Bloqueada\n", encoding="utf-8")
    (auto_dir / "CONTEXT.md").write_text("# Contexto\n", encoding="utf-8")
    (auto_dir / "run.ps1").write_text("Write-Host 'ok'\n", encoding="utf-8")
    (docs_dir / "auto-bloqueada-runbook.md").write_text("# Runbook\n", encoding="utf-8")
    (auto_dir / "automation.manifest.json").write_text(
        json.dumps(
            {
                "id": "AB-11",
                "name": "Auto Bloqueada",
                "slug": "auto-bloqueada",
                "criticality": "high",
                "owner_area": "Operação",
                "entrypoint": "run.ps1",
                "runtime": "powershell",
                "channels": ["email"],
                "queue_group": "oracle",
                "max_runtime_minutes": 30,
                "max_retries": 1,
                "schedule_summary": "Manual",
                "runbook_path": "docs/runbooks/auto-bloqueada-runbook.md",
                "context_path": "Auto Bloqueada/CONTEXT.md",
                "readme_path": "Auto Bloqueada/README.md",
                "orchestrator": {"script_path": "./Auto Bloqueada/run.ps1"},
                "dependencies": {"oracle": True, "outlook": False, "whatsapp": False},
                "smoke_tests": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(auto_router, "PROJECT_ROOT", str(tmp_path))

    res = client.post(
        "/api/automations",
        json={
            "name": "Auto Bloqueada",
            "script_path": "./Auto Bloqueada/run.ps1",
            "queue_group": "financeiro",
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422
    assert "queue_group" in res.json()["detail"]


def test_create_duplicate_name_rejected(client: TestClient) -> None:
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


def test_list_automations_paginated(client: TestClient) -> None:
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


def test_update_automation(client: TestClient) -> None:
    client.post(
        "/api/automations",
        json={
            "name": "To Update",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.patch(
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


def test_update_automation_rejects_put_verb(client: TestClient) -> None:
    """Achado #19: o endpoint sempre teve semântica de update parcial
    (exclude_unset=True) mas era exposto como PUT — corrigido para PATCH.
    PUT no mesmo caminho não deve mais ter rota registrada."""
    client.post(
        "/api/automations",
        json={
            "name": "Verbo Errado",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.put(
        "/api/automations/1",
        json={"description": "Não deveria funcionar"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 405


def test_update_automation_reloads_scheduler(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:

    client.post(
        "/api/automations",
        json={
            "name": "Reload Scheduler",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        auto_router, "_reload_scheduler_safe", lambda: calls.append("reload")
    )

    res = client.patch(
        "/api/automations/1",
        json={
            "enabled": False,
        },
        headers=AUTH_HEADERS,
    )

    assert res.status_code == 200
    assert calls == ["reload"]


def test_reload_scheduler_neutralizes_reserved_cleanup_automation(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        assert bool(cleanup_auto.enabled) is False
        assert cleanup_auto.schedule is None
        assert not any(job.id.startswith("job_") for job in scheduler.get_jobs())
    finally:
        for job in list(scheduler.get_jobs()):
            scheduler.remove_job(job.id)


def test_update_automation_rejects_path_escape(client: TestClient) -> None:
    client.post(
        "/api/automations",
        json={
            "name": "Path Guard",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    res = client.patch(
        "/api/automations/1",
        json={
            "script_path": "C:\\Windows\\win.ini",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_delete_automation(client: TestClient) -> None:
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


def test_reject_path_traversal(client: TestClient) -> None:
    res = client.post(
        "/api/automations",
        json={
            "name": "Evil Task",
            "script_path": "../../etc/passwd",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_reject_dangerous_name(client: TestClient) -> None:
    res = client.post(
        "/api/automations",
        json={
            "name": "<script>alert(1)</script>",
            "script_path": "./test/run.ps1",
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_reject_invalid_schedule(client: TestClient) -> None:
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


def test_reject_schedule_with_invalid_time(client: TestClient) -> None:
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


def test_list_all_automations_includes_operational_snapshot(
    client: TestClient, db_session: Session
) -> None:

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


def test_get_automation_returns_latest_execution_context_for_modal(
    client: TestClient, db_session: Session
) -> None:

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


def test_set_automation_test_mode_via_json_body(client: TestClient) -> None:
    """Achado #20: enabled viajava como query param cru; agora é corpo tipado."""
    client.post(
        "/api/automations",
        json={"name": "Test Mode Auto", "script_path": "./test/run.ps1"},
        headers=AUTH_HEADERS,
    )
    res = client.post(
        "/api/automations/1/test-mode",
        json={"enabled": True},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    assert "ativado" in res.json()["message"] or "True" in res.json()["message"]


def test_set_automation_test_mode_rejects_query_param(client: TestClient) -> None:
    """`?enabled=true` sem corpo JSON não deve mais funcionar (achado #20)."""
    client.post(
        "/api/automations",
        json={"name": "Test Mode Query Rejeitado", "script_path": "./test/run.ps1"},
        headers=AUTH_HEADERS,
    )
    res = client.post(
        "/api/automations/1/test-mode?enabled=true",
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_set_global_test_mode_via_json_body(client: TestClient) -> None:
    res = client.post(
        "/api/automations/test-mode/global",
        json={"enabled": False},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    assert "desativado" in res.json()["message"]


def test_clone_bloqueado_quando_manifesto_some_do_disco(client: TestClient) -> None:
    # Achado nº 18: `clone_automation` montava e persistia `models.Automation`
    # direto, sem gate. Uma automação criada quando o manifesto existia, cujo
    # `automation.manifest.json` depois some (pasta removida, rollback parcial),
    # podia ser clonada e o clone nascia habilitável fora da governança.
    criada = client.post(
        "/api/automations",
        json={"name": "Alvo de Clone", "script_path": "./test/run.ps1"},
        headers=AUTH_HEADERS,
    )
    assert criada.status_code == 201
    auto_id = criada.json()["id"]

    manifesto = Path(auto_router.PROJECT_ROOT) / "test" / "automation.manifest.json"
    assert manifesto.is_file()
    manifesto.unlink()

    clonada = client.post(f"/api/automations/{auto_id}/clone", headers=AUTH_HEADERS)
    assert clonada.status_code == 422
    assert "manifest" in clonada.json()["detail"].lower()


def test_clone_de_nome_longo_fica_editavel_via_patch(client: TestClient) -> None:
    # Achado nº 19: o clone ganhava " (Clone)" (+8 chars) sem checagem de
    # tamanho e não passava pelo Pydantic (max_length=100), então um clone com
    # nome > 100 era persistido — mas todo PATCH nele falhava com 422.
    nome_longo = "Auto " + "n" * 90  # 95 chars — legítimo (limite é 100)
    assert len(nome_longo) == 95
    criada = client.post(
        "/api/automations",
        json={"name": nome_longo, "script_path": "./test/run.ps1"},
        headers=AUTH_HEADERS,
    )
    assert criada.status_code == 201
    auto_id = criada.json()["id"]

    clonada = client.post(f"/api/automations/{auto_id}/clone", headers=AUTH_HEADERS)
    assert clonada.status_code == 201
    clone_id = clonada.json()["id"]
    assert len(clonada.json()["name"]) <= 100

    # O PATCH que só liga/desliga uma flag precisa passar — antes: 422 em "name".
    patch = client.patch(
        f"/api/automations/{clone_id}",
        json={"description": "editado apos clone"},
        headers=AUTH_HEADERS,
    )
    assert patch.status_code == 200
