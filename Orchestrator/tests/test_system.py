"""
Testes focados nas operações e endpoints de diagnóstico/informações do Sistema.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any

import app.routers.system as system_router
from app import models
from app.constants import ORCHESTRATOR_CONTRACT_VERSION, ORCHESTRATOR_VERSION
from app.schemas import WorkerStatus
from app.timezone import get_now_local
from conftest import AUTH_HEADERS


def test_read_root(client: Any) -> None:
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == ORCHESTRATOR_VERSION
    assert "dashboard_url" in data


def test_reject_without_api_key(client: Any) -> None:
    res = client.get("/api/automations/all")
    assert res.status_code == 403


def test_reject_wrong_api_key(client: Any) -> None:
    res = client.get("/api/automations/all", headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 403


def test_health_check(client: Any) -> None:
    res = client.get("/api/system/health")
    assert res.status_code == 200
    data = res.json()
    assert data["database"] == "online"
    assert data["status"] in ["healthy", "degraded", "unhealthy"]


def test_csp_restringe_connect_src_a_self(client: Any) -> None:
    # Achado #31: "ws: wss:" liberava WebSocket para qualquer host.
    res = client.get("/api/system/health")
    csp = res.headers.get("Content-Security-Policy", "")
    assert "connect-src 'self';" in csp
    assert "ws:" not in csp and "wss:" not in csp


def test_csp_script_src_sem_unsafe_inline(client: Any) -> None:
    # Achado #43: o build do Vite só emite <script src=...> externo, então
    # 'unsafe-inline' era desnecessário e neutralizava a proteção anti-XSS.
    # Continua permitido em style-src (React/Vite injetam estilo inline).
    res = client.get("/api/system/health")
    csp = res.headers.get("Content-Security-Policy", "")
    assert "script-src 'self';" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp


def test_resposta_429_do_rate_limit_recebe_headers_de_seguranca() -> None:
    # Achado #31: o 429 retorna sem chamar call_next; com SecurityHeaders como
    # camada interna ele saía sem CSP/X-Frame-Options. Reproduz a mesma ordem de
    # registro do main.py, com limite de 1 req/min.
    from app.main import (  # pylint: disable=import-outside-toplevel
        SecurityHeadersMiddleware,
    )
    from app.middleware import (  # pylint: disable=import-outside-toplevel
        RateLimitMiddleware,
    )
    from fastapi import FastAPI  # pylint: disable=import-outside-toplevel

    app_teste = FastAPI()

    @app_teste.get("/api/ping")
    def _ping() -> dict[str, str]:
        return {"ok": "1"}

    app_teste.add_middleware(RateLimitMiddleware, rpm=1)
    app_teste.add_middleware(SecurityHeadersMiddleware)

    from fastapi.testclient import (  # pylint: disable=import-outside-toplevel
        TestClient,
    )

    with TestClient(app_teste) as c:
        primeira = c.get("/api/ping")
        segunda = c.get("/api/ping")

    assert primeira.status_code == 200
    assert segunda.status_code == 429
    assert "Content-Security-Policy" in segunda.headers
    assert segunda.headers.get("X-Frame-Options") == "DENY"


def test_mask_env_content_mascara_apenas_chaves_sensiveis() -> None:
    # Achado #9: GET /env expunha o .env completo (credenciais Oracle e a
    # própria API Key) para qualquer portador da chave mestra.
    from app.security import (  # pylint: disable=import-outside-toplevel
        mask_env_content,
    )

    original = (
        "# comentario\n"
        "ORCHESTRATOR_API_KEY=chave-secreta\n"
        "ORACLE_READONLY_PASSWORD=senha-oracle\n"
        "RATE_LIMIT_RPM=120\n"
        "HUB_API_PORT=8000\n"
        "\n"
    )
    mascarado = mask_env_content(original)

    assert "chave-secreta" not in mascarado
    assert "senha-oracle" not in mascarado
    assert "ORCHESTRATOR_API_KEY=********" in mascarado
    assert "ORACLE_READONLY_PASSWORD=********" in mascarado
    # Chaves operacionais seguem legíveis para diagnóstico.
    assert "RATE_LIMIT_RPM=120" in mascarado
    assert "HUB_API_PORT=8000" in mascarado
    assert "# comentario" in mascarado
    assert mascarado.endswith("\n")


def test_env_validate_rejeita_valor_mascarado(client: Any) -> None:
    # Blindagem do round-trip: gravar o placeholder de volta sobrescreveria o
    # segredo real por "********".
    res = client.post(
        "/api/system/env/validate",
        json={"content": "ORCHESTRATOR_API_KEY=********\n"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 200
    body = res.json()
    # MASKED_VALUE deixou de ser bloqueante em 31/07/2026: o placeholder é
    # resolvido para o valor real por `restore_masked_values` antes da gravação.
    # A mensagem antiga mandava "remover a linha para preservar o atual" — e
    # como o payload sobrescreve o arquivo inteiro (nunca houve merge), seguir a
    # instrução APAGAVA a ORCHESTRATOR_API_KEY e as credenciais Oracle.
    assert body["valid"] is True
    masked = [i for i in body["issues"] if i["code"] == "MASKED_VALUE"]
    assert len(masked) == 1
    assert masked[0]["severity"] == "info"


def test_prometheus_metrics_requires_api_key(client: Any) -> None:
    # Achado #8: include_in_schema=False não é controle de acesso.
    res = client.get("/api/system/metrics/prometheus")
    assert res.status_code == 403


def test_request_id_invalido_do_cliente_nao_e_refletido(client: Any) -> None:
    # Achado #24: X-Request-Id malicioso (CRLF/tamanho) não pode ser refletido
    # cru no header de resposta — deve ser substituído por um ID gerado.
    malicioso = "bad\r\nX-Injected: 1" + "a" * 100
    res = client.get("/api/system/health", headers={"X-Request-Id": malicioso})
    devolvido = res.headers.get("X-Request-Id", "")
    assert devolvido != malicioso
    assert "\r" not in devolvido and "\n" not in devolvido
    assert len(devolvido) <= 64


def test_request_id_valido_do_cliente_e_preservado(client: Any) -> None:
    valido = "req-ABC123-2026"
    res = client.get("/api/system/health", headers={"X-Request-Id": valido})
    assert res.headers.get("X-Request-Id") == valido


def test_metrics(client: Any) -> None:
    res = client.get("/api/system/metrics", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert "summary" in res.json()
    assert "automations" in res.json()


def test_uptime(client: Any) -> None:
    res = client.get("/api/system/uptime", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert "uptime_seconds" in res.json()


def test_health_includes_wal_size(client: Any) -> None:
    res = client.get("/api/system/health")
    assert res.status_code == 200
    assert "wal_size_mb" in res.json()


def test_version_endpoint(client: Any) -> None:
    res = client.get("/api/system/version", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == ORCHESTRATOR_VERSION
    assert "python_version" in data
    assert "uptime_seconds" in data
    assert "max_workers" in data


def test_diagnostics_endpoint(client: Any) -> None:
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
    assert "performance" in data
    assert data["performance"]["timings_ms"]["total_ms"] >= 0
    assert data["operational_baseline"]["status"] in [
        "healthy",
        "attention",
        "incident",
    ]


def test_diagnostics_reports_actionable_queue_and_wal_findings(
    client: Any, db_session: Any, monkeypatch: Any
) -> None:

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


def test_system_overview_exposes_contract_version(client: Any) -> None:
    res = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["contract_version"] == ORCHESTRATOR_CONTRACT_VERSION


def test_system_version_exposes_contract_version(client: Any) -> None:
    res = client.get("/api/system/version", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["contract_version"] == ORCHESTRATOR_CONTRACT_VERSION


def test_system_history_endpoint_returns_snapshots(
    client: Any, db_session: Any
) -> None:

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


def test_operational_baseline_endpoint_returns_summary(client: Any) -> None:
    res = client.get("/api/system/baseline", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["healthy", "attention", "incident"]
    assert "metrics" in data
    assert any(item["code"] == "wal_size" for item in data["metrics"])
    assert "recommended_action" in data


def test_diagnostics_offline_worker_prefers_recovery_action(
    client: Any, db_session: Any, monkeypatch: Any
) -> None:

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


def test_system_overview_includes_diagnostics_summary(client: Any) -> None:
    res = client.get("/api/system/overview", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "portfolio" in data
    assert data["portfolio"]["status"] in ["healthy", "attention", "incident"]
    assert "performance" in data
    assert data["performance"]["timings_ms"]["total_ms"] >= 0
    assert "diagnostics" in data
    assert data["diagnostics"]["overall_status"] in ["healthy", "degraded", "unhealthy"]
    assert "findings" in data["diagnostics"]
    assert data["diagnostics"]["performance"]["timings_ms"]["total_ms"] >= 0


def test_system_overview_exposes_automation_operational_metrics(
    client: Any, db_session: Any
) -> None:

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
    assert target["operational_state"] in [
        "attention",
        "healthy",
        "in_progress",
        "idle",
        "paused",
    ]


def test_wait_for_task_requires_api_key(client: Any) -> None:
    res = client.get("/api/system/wait-for-task")
    assert res.status_code == 403


def test_update_env_creates_backup(
    client: Any, monkeypatch: Any, tmp_path: Path
) -> None:

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


def test_system_router_project_root_points_to_repo_root() -> None:

    expected_root = Path(__file__).resolve().parents[2]
    assert Path(system_router.PROJECT_ROOT).resolve() == expected_root.resolve()
