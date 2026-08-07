# pylint: disable=protected-access
"""Testes unitários de funções puras de app/services/portfolio_catalog.py."""

from datetime import timedelta
from pathlib import Path
from typing import Any

from app import models, schemas
from app.services import portfolio_catalog as pc
from app.services.portfolio_manifest import CatalogManifest
from app.timezone import get_now_local


def _manifest(**overrides: Any) -> CatalogManifest:
    payload: dict[str, Any] = {
        "id": "TEST-01",
        "name": "Automação Teste",
        "slug": "automacao-teste",
        "directory_name": "Automacao Teste",
        "criticality": "high",
        "owner_area": "Equipe QA",
        "entrypoint": "run.ps1",
        "runtime": "powershell",
        "schedule_summary": "Diariamente às 08:00",
        "runbook_path": "docs/runbooks/teste.md",
        "context_path": "Automacao Teste/CONTEXT.md",
        "readme_path": "Automacao Teste/README.md",
        "orchestrator": {"script_path": "./Automacao Teste/run.ps1"},
        "max_runtime_minutes": 15,
        "max_retries": 0,
    }
    payload.update(overrides)
    return CatalogManifest.model_validate(payload)


def _health_item(**overrides: Any) -> schemas.PortfolioHealthItem:
    payload: dict[str, Any] = {
        "catalog_id": "TEST-01",
        "name": "Automação Teste",
        "slug": "automacao-teste",
        "criticality": "high",
        "runtime": "powershell",
    }
    payload.update(overrides)
    return schemas.PortfolioHealthItem(**payload)


# ---------------------------------------------------------------------------
# _sla_state
# ---------------------------------------------------------------------------


def test_sla_state_sem_sla_configurado_retorna_unknown() -> None:
    assert (
        pc._sla_state(
            None,
            schedule_lag_minutes=100,
            last_status="ERROR",
            last_failure_age_minutes=100,
        )
        == "unknown"
    )


def test_sla_state_violado_por_atraso_de_agendamento() -> None:
    assert (
        pc._sla_state(
            30, schedule_lag_minutes=45, last_status=None, last_failure_age_minutes=None
        )
        == "breached"
    )


def test_sla_state_violado_por_falha_persistente() -> None:
    assert (
        pc._sla_state(
            30,
            schedule_lag_minutes=None,
            last_status="ERROR",
            last_failure_age_minutes=40,
        )
        == "breached"
    )


def test_sla_state_recovering_quando_falha_recente_dentro_do_sla() -> None:
    assert (
        pc._sla_state(
            30,
            schedule_lag_minutes=None,
            last_status="ERROR",
            last_failure_age_minutes=5,
        )
        == "recovering"
    )


def test_sla_state_ok_quando_dentro_do_esperado() -> None:
    assert (
        pc._sla_state(
            30,
            schedule_lag_minutes=0,
            last_status="SUCCESS",
            last_failure_age_minutes=None,
        )
        == "ok"
    )


# ---------------------------------------------------------------------------
# _health_status
# ---------------------------------------------------------------------------


def test_health_status_nao_registrado_tem_prioridade_maxima() -> None:
    resultado = pc._health_status(
        automation_registered=False,
        docs_status="complete",
        drift_count=0,
        sla_state="breached",
        operational_state="idle",
    )
    assert resultado == "not_registered"


def test_health_status_sla_violado() -> None:
    resultado = pc._health_status(
        automation_registered=True,
        docs_status="complete",
        drift_count=0,
        sla_state="breached",
        operational_state="idle",
    )
    assert resultado == "breached"


def test_health_status_atencao_por_docs_ou_drift() -> None:
    assert (
        pc._health_status(
            automation_registered=True,
            docs_status="missing",
            drift_count=0,
            sla_state="ok",
            operational_state="idle",
        )
        == "attention"
    )
    assert (
        pc._health_status(
            automation_registered=True,
            docs_status="complete",
            drift_count=2,
            sla_state="ok",
            operational_state="idle",
        )
        == "attention"
    )


def test_health_status_usa_operational_state_como_fallback() -> None:
    assert (
        pc._health_status(
            automation_registered=True,
            docs_status="complete",
            drift_count=0,
            sla_state="ok",
            operational_state="running",
        )
        == "running"
    )
    assert (
        pc._health_status(
            automation_registered=True,
            docs_status="complete",
            drift_count=0,
            sla_state="ok",
            operational_state="",
        )
        == "idle"
    )


# ---------------------------------------------------------------------------
# _portfolio_operational_status / _count_portfolio_signals
# ---------------------------------------------------------------------------


def test_portfolio_operational_status_incidente_por_nao_registrado() -> None:
    item = _health_item(health_status="not_registered")
    assert pc._portfolio_operational_status(item) == "incident"


def test_portfolio_operational_status_incidente_por_drift_critico() -> None:
    item = _health_item(criticality="critical", drift_count=1, docs_status="complete")
    assert pc._portfolio_operational_status(item) == "incident"


def test_portfolio_operational_status_atencao_por_delete_candidate() -> None:
    item = _health_item(review_status="delete_candidate")
    assert pc._portfolio_operational_status(item) == "attention"


def test_portfolio_operational_status_saudavel_sem_pendencias() -> None:
    item = _health_item(docs_status="complete", drift_count=0, sla_state="ok")
    assert pc._portfolio_operational_status(item) == "healthy"


def test_count_portfolio_signals_agrega_corretamente() -> None:
    # criticality="low" em todos para isolar o efeito de cada sinal, sem
    # disparar o atalho de "critical_governance_drift" (critical/high + drift).
    items = [
        _health_item(
            catalog_id="A",
            criticality="low",
            health_status="not_registered",
            docs_status="complete",
            drift_count=0,
        ),
        _health_item(
            catalog_id="B",
            criticality="low",
            docs_status="complete",
            drift_count=1,
            review_status="attention",
        ),
        _health_item(
            catalog_id="C", criticality="low", docs_status="complete", drift_count=0
        ),
        _health_item(
            catalog_id="runtime-9",
            criticality="low",
            docs_status="missing",
            drift_count=1,
        ),
    ]
    counts = pc._count_portfolio_signals(items)

    assert counts["incident_items"] == 1  # apenas A (not_registered)
    assert counts["drift_items"] == 2  # B e runtime-9
    assert counts["docs_missing_items"] == 1  # apenas runtime-9
    assert counts["governed_items"] == 3  # exclui o catalog_id "runtime-9"


# ---------------------------------------------------------------------------
# _portfolio_top_issue
# ---------------------------------------------------------------------------


def test_portfolio_top_issue_prioriza_delete_candidate_sobre_o_resto() -> None:
    counts = {
        "delete_candidate_items": 1,
        "not_registered_items": 1,
        "docs_missing_items": 1,
        "drift_items": 1,
        "sla_breached_items": 1,
    }
    top_issue, _ = pc._portfolio_top_issue(counts)
    assert "candidatas à exclusão" in top_issue


def test_portfolio_top_issue_sem_pendencias() -> None:
    counts = {
        "delete_candidate_items": 0,
        "not_registered_items": 0,
        "docs_missing_items": 0,
        "drift_items": 0,
        "sla_breached_items": 0,
    }
    top_issue, action = pc._portfolio_top_issue(counts)
    assert "consistente" in top_issue
    assert action is None


# ---------------------------------------------------------------------------
# _build_portfolio_summary
# ---------------------------------------------------------------------------


def test_build_portfolio_summary_status_incident() -> None:
    items = [_health_item(catalog_id="X", health_status="not_registered")]
    summary = pc._build_portfolio_summary(items)
    assert summary.status == "incident"
    assert summary.total_items == 1


# ---------------------------------------------------------------------------
# _build_review_status (candidatos a exclusao / cadastro orfao)
# ---------------------------------------------------------------------------


def test_build_review_status_cadastro_runtime_orfao_vira_delete_candidate() -> None:
    status, reasons = pc._build_review_status(
        catalog_id="runtime-42",
        enabled=False,
        next_run=None,
        last_success_age_seconds=None,
        last_failure_age_seconds=None,
        drift_count=1,
        docs_status="missing",
        health_status="not_governed",
    )
    assert status == "delete_candidate"
    assert any("sem manifesto" in reason for reason in reasons)


def test_build_review_status_ativa_sem_pendencias() -> None:
    status, reasons = pc._build_review_status(
        catalog_id="TEST-01",
        enabled=True,
        next_run=get_now_local() + timedelta(hours=1),
        last_success_age_seconds=60.0,
        last_failure_age_seconds=None,
        drift_count=0,
        docs_status="complete",
        health_status="healthy",
    )
    assert status == "active"
    assert not reasons


# ---------------------------------------------------------------------------
# _dependency_status
# ---------------------------------------------------------------------------


def test_dependency_status_not_used_quando_dependencia_desativada() -> None:
    manifest = _manifest(
        dependencies={"oracle": False, "outlook": False, "whatsapp": False}
    )
    resultado = pc._dependency_status(manifest, None)
    assert resultado == {
        "oracle": "not_used",
        "outlook": "not_used",
        "whatsapp": "not_used",
    }


def test_dependency_status_degraded_por_palavra_chave_no_failure_reason() -> None:
    manifest = _manifest(
        dependencies={"oracle": True, "outlook": False, "whatsapp": False}
    )
    snapshot = {"status": "ERROR", "failure_reason": "ORA-12154 timeout"}
    resultado = pc._dependency_status(manifest, snapshot)
    assert resultado["oracle"] == "degraded"


def test_dependency_status_healthy_quando_ultima_execucao_entregue() -> None:
    manifest = _manifest(
        dependencies={"oracle": True, "outlook": False, "whatsapp": False}
    )
    snapshot = {"status": "SUCCESS", "failure_reason": None}
    resultado = pc._dependency_status(manifest, snapshot)
    assert resultado["oracle"] == "healthy"


# ---------------------------------------------------------------------------
# _minutes_since / _seconds_since / _schedule_lag_*
# ---------------------------------------------------------------------------


def test_minutes_since_none_retorna_none() -> None:
    assert pc._minutes_since(None) is None


def test_minutes_since_calcula_diferenca_positiva() -> None:
    timestamp = get_now_local() - timedelta(minutes=10)
    resultado = pc._minutes_since(timestamp)
    assert resultado is not None
    assert resultado >= 9


def test_schedule_lag_minutes_nula_com_execucao_ativa() -> None:
    next_run = get_now_local() - timedelta(minutes=5)
    assert pc._schedule_lag_minutes(next_run, active_execution_count=1) is None


def test_schedule_lag_minutes_zero_quando_agendamento_no_futuro() -> None:
    next_run = get_now_local() + timedelta(minutes=5)
    assert pc._schedule_lag_minutes(next_run, active_execution_count=0) == 0


def test_schedule_lag_minutes_positivo_quando_atrasado() -> None:
    next_run = get_now_local() - timedelta(minutes=12)
    resultado = pc._schedule_lag_minutes(next_run, active_execution_count=0)
    assert resultado is not None
    assert resultado >= 11


# ---------------------------------------------------------------------------
# _sort_health_item (peso de criticidade)
# ---------------------------------------------------------------------------


def test_sort_health_item_prioriza_criticidade_maior() -> None:
    itens = [
        _health_item(catalog_id="low", name="Zebra", criticality="low"),
        _health_item(catalog_id="critical", name="Alfa", criticality="critical"),
        _health_item(catalog_id="high", name="Beta", criticality="high"),
    ]
    ordenados = sorted(itens, key=pc._sort_health_item)
    assert [item.catalog_id for item in ordenados] == ["critical", "high", "low"]


def test_sort_health_item_desempata_por_nome() -> None:
    itens = [
        _health_item(catalog_id="b", name="Zebra", criticality="high"),
        _health_item(catalog_id="a", name="Alfa", criticality="high"),
    ]
    ordenados = sorted(itens, key=pc._sort_health_item)
    assert [item.catalog_id for item in ordenados] == ["a", "b"]


# ---------------------------------------------------------------------------
# _manifest_runtime_mismatches (drift entre manifesto e cadastro)
# ---------------------------------------------------------------------------


def test_manifest_runtime_mismatches_detecta_divergencia(tmp_path: Path) -> None:
    manifest = _manifest(max_runtime_minutes=15)
    auto = models.Automation(
        name="Automação Teste",
        script_path="./Automacao Teste/run.ps1",
        max_runtime_minutes=30,  # diverge do manifesto (15)
        max_retries=0,
    )

    issues = pc._manifest_runtime_mismatches(tmp_path, manifest, auto)

    codigos = {issue.code for issue in issues}
    assert "max_runtime_mismatch" in codigos


def test_manifest_runtime_mismatches_retorna_vazio_quando_alinhado(
    tmp_path: Path,
) -> None:
    manifest = _manifest(
        max_runtime_minutes=15,
        max_retries=0,
        orchestrator={"script_path": "./Automacao Teste/run.ps1"},
    )
    auto = models.Automation(
        name="Automação Teste",
        script_path="./Automacao Teste/run.ps1",
        max_runtime_minutes=15,
        max_retries=0,
    )

    issues = pc._manifest_runtime_mismatches(tmp_path, manifest, auto)

    assert not issues


def test_build_portfolio_lookups_usa_jobs_recebido_sem_reconsultar(
    db_session: Any, monkeypatch: Any
) -> None:
    """Regressão: GET /api/system/overview já calcula `jobs` uma vez; passar
    esse valor para `_build_portfolio_lookups` não pode disparar uma segunda
    resolução via `list_scheduled_jobs` (achado de performance #8)."""

    def _falha_se_chamado(_db: Any) -> list[schemas.ScheduledJob]:
        raise AssertionError("list_scheduled_jobs não deveria ser chamado de novo")

    monkeypatch.setattr(pc, "list_scheduled_jobs", _falha_se_chamado)

    lookups = pc._build_portfolio_lookups(db_session, automation_ids=[], jobs=[])

    assert not lookups["next_run_lookup"]


def test_build_portfolio_lookups_sem_jobs_recalcula_internamente(
    db_session: Any, monkeypatch: Any
) -> None:
    """Chamadores que não têm `jobs` prontos (ex.: GET /api/portfolio/health
    isolado) continuam funcionando: sem o parâmetro, a função recalcula."""
    chamadas = []

    def _rastreia(db: Any) -> list[schemas.ScheduledJob]:
        chamadas.append(db)
        return []

    monkeypatch.setattr(pc, "list_scheduled_jobs", _rastreia)

    pc._build_portfolio_lookups(db_session, automation_ids=[])

    assert len(chamadas) == 1
