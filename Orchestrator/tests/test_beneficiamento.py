"""Testes de integração do módulo analítico SQLite de Beneficiamento."""
# mypy: ignore-errors
# pylint: disable=import-outside-toplevel,import-error,protected-access

import json
from datetime import date, timedelta
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from conftest import AUTH_HEADERS


def test_beneficiamento_historico_init_db_maintains_derived_columns_and_indexes(tmp_path) -> None:
    """Schema local deve garantir colunas derivadas e índices idempotentes do overview."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento.historico_db import descrever_schema_historico, init_db

    db_path = tmp_path / "beneficiamento_historico.db"
    resolved = init_db(db_path)
    resolved = init_db(resolved)
    snapshot = descrever_schema_historico(resolved)
    columns = snapshot["columns"]
    indexes = set(snapshot["indexes"])

    for column in ("TURNO_ID", "TURNO_LABEL", "MAQUINA_KEY", "FASE_KEY", "CODIGO_KEY"):
        assert columns[column] == "TEXT"

    for index_name in (
        "idx_producao_turno_label",
        "idx_producao_maquina_key",
        "idx_producao_fase_key",
        "idx_producao_codigo_key",
        "idx_producao_data_maquina_fase",
    ):
        assert index_name in indexes


def test_beneficiamento_historico_analytics_endpoint(client: TestClient) -> None:
    """Valida o endpoint de analíticos de produção com todos os novos filtros cruzados."""
    response = client.get(
        "/api/beneficiamento/historico/analytics",
        headers=AUTH_HEADERS,
        params={
            "dt_inicio": "2026-01-01",
            "dt_fim": "2026-12-31",
            "busca": "tingimento",
            "maquina": "JET 01",
            "fase": "TINGIMENTO",
            "turno": "Turno A",
        }
    )

    assert response.status_code == 200
    payload = response.json()
    assert "geral" in payload
    assert "operadores" in payload
    assert "maquinas" in payload
    assert "produtos" in payload
    assert "turnos" in payload
    assert "fases" in payload
    assert "artigos" in payload
    assert "cores" in payload

    geral = payload["geral"]
    assert "ob_distintas" in geral
    assert "kg_total" in geral
    assert "efic_tempo_media" in geral
    assert "taxa_reprocesso" in geral


def test_beneficiamento_overview_endpoint_contract(client: TestClient) -> None:
    """Valida o contrato V1 principal sem depender de refresh Oracle."""
    response = client.get(
        "/api/beneficiamento/overview",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload).issuperset({
        "generated_at",
        "filters",
        "health",
        "kpis",
        "rankings",
        "series",
        "filter_options",
        "turnos",
        "tingimento",
        "interaction",
    })
    assert payload["health"]["source"] == "sqlite_historico"
    assert payload["filters"]["effective"]["dt_inicio"]
    assert payload["filters"]["effective"]["dt_fim"]
    assert payload["turnos"]
    assert payload["turnos"][0]["turno_label"].startswith("TURNO")
    assert "summary" in payload["tingimento"]

    kpis = payload["kpis"]
    for key in [
        "ob_distintas",
        "fases_concluidas",
        "kg_total",
        "mt_total",
        "eficiencia_tempo_pct",
        "reprocesso_kg_pct",
        "desvio_tempo_min",
        "produtividade_kg_h",
    ]:
        assert key in kpis


def test_beneficiamento_health_endpoint_contract(client: TestClient) -> None:
    """Expõe a saúde dos snapshots locais por período para a UI operacional."""
    response = client.get(
        "/api/beneficiamento/health",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in ["healthy", "attention", "missing", "no_data"]
    assert payload["periods_total"] == 4
    assert payload["periods_loaded"] >= 0
    assert "reason_code" in payload
    assert "recommended_action" in payload
    assert "issues" in payload
    assert "summary" in payload
    assert "snapshot_files" in payload
    assert len(payload["periods"]) == 4
    assert {item["period"] for item in payload["periods"]} == {
        "diario",
        "semanal",
        "mensal",
        "anual",
    }
    diario = next(item for item in payload["periods"] if item["period"] == "diario")
    assert "reason_code" in diario
    assert "reason_message" in diario
    assert "snapshot_state" in diario
    assert "issues" in diario


def test_beneficiamento_periods_endpoint_contract(client: TestClient) -> None:
    """Lista todos os períodos disponíveis com metadados de snapshot e qualidade."""
    response = client.get(
        "/api/beneficiamento/periods",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_period"] in ["diario", "semanal", "mensal", "anual"]
    assert len(payload["periods"]) == 4
    diario = next(item for item in payload["periods"] if item["key"] == "diario")
    assert set(diario).issuperset({
        "key",
        "label",
        "available",
        "status",
        "metrics",
        "quality",
        "oracle",
        "snapshot",
    })


def test_beneficiamento_dashboard_endpoint_contract(client: TestClient) -> None:
    """Agrega períodos, comparação e saúde para a home do Beneficiamento."""
    response = client.get(
        "/api/beneficiamento/dashboard",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload).issuperset({
        "generated_at",
        "default_period",
        "overall",
        "comparison",
        "periods",
        "health",
    })
    assert payload["default_period"] in payload["periods"]
    assert {item["key"] for item in payload["comparison"]} == {
        "diario",
        "semanal",
        "mensal",
        "anual",
    }
    assert payload["health"]["status"] in ["healthy", "attention", "missing", "no_data"]
    assert payload["periods"]["diario"]["key"] == "diario"


def test_beneficiamento_overview_filters(client: TestClient) -> None:
    """Valida os filtros aceitos pelo contrato /overview."""
    response = client.get(
        "/api/beneficiamento/overview",
        headers=AUTH_HEADERS,
        params={
            "dt_inicio": "2026-01-01",
            "dt_fim": "2026-12-31",
            "maquina": "JET 01",
            "fase": "TINGIMENTO",
            "turno": "Turno A",
            "alternativo": "03212",
            "q": "tingimento",
        },
    )

    assert response.status_code == 200
    effective = response.json()["filters"]["effective"]
    assert effective["dt_inicio"] == "2026-01-01"
    assert effective["dt_fim"] == "2026-12-31"
    assert effective["maquina"] == "JET 01"
    assert effective["fase"] == "TINGIMENTO"
    assert effective["turno"] == "Turno A"
    assert effective["alternativo"] == "03212"
    assert effective["q"] == "tingimento"


def test_beneficiamento_overview_empty_cut_returns_no_data(client: TestClient) -> None:
    """Recorte vazio deve responder no_data em vez de erro 500."""
    response = client.get(
        "/api/beneficiamento/overview",
        headers=AUTH_HEADERS,
        params={
            "dt_inicio": "1999-01-01",
            "dt_fim": "1999-01-02",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["status"] == "no_data"
    assert payload["kpis"]["fases_concluidas"] == 0


def test_beneficiamento_get_endpoints_do_not_import_oracle_runner() -> None:
    """GETs do Dashboard devem permanecer restritos ao SQLite local."""
    import app.routers.beneficiamento as router

    source_names = set(router.get_beneficiamento_overview.__code__.co_names)
    assert "runner" not in source_names
    assert "oracle" not in source_names
    dashboard_names = set(router.get_beneficiamento_dashboard.__code__.co_names)
    assert "runner" not in dashboard_names
    assert "oracle" not in dashboard_names
    health_names = set(router.get_beneficiamento_health.__code__.co_names)
    assert "runner" not in health_names
    assert "oracle" not in health_names
    detail_source_names = set(router.get_beneficiamento_detail.__code__.co_names)
    assert "runner" not in detail_source_names
    assert "oracle" not in detail_source_names


def test_beneficiamento_historico_search_endpoint(client: TestClient) -> None:
    """Valida o endpoint de consulta de rastreabilidade de OBs."""
    response = client.get(
        "/api/beneficiamento/historico",
        headers=AUTH_HEADERS,
        params={
            "ob": "2401",
            "limit": 10
        }
    )
    assert response.status_code == 200
    payload = response.json()
    assert "total_records" in payload
    assert "records" in payload


def test_beneficiamento_detail_endpoint_for_product(client: TestClient) -> None:
    """Valida o drill-down por produto com resposta paginada."""
    response = client.get(
        "/api/beneficiamento/detail",
        headers=AUTH_HEADERS,
        params={
            "target_type": "produto",
            "alternativo": "03212",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target"]["type"] == "produto"
    assert "summary" in payload
    assert "records" in payload
    assert "trace" in payload
    assert payload["pagination"]["limit"] == 10


def test_beneficiamento_detail_endpoint_returns_raw_payload_on_demand(client: TestClient) -> None:
    """Payload bruto só deve aparecer quando o detalhe o solicitar explicitamente."""
    response = client.get(
        "/api/beneficiamento/detail",
        headers=AUTH_HEADERS,
        params={
            "target_type": "produto",
            "alternativo": "03212",
            "include_raw": "true",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_records"]


def test_beneficiamento_snapshot_dashboard_reuses_period_reads(monkeypatch) -> None:
    """O dashboard de snapshots não deve reler os períodos ao montar health e overview."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento import snapshot_dashboard

    call_count = {"count": 0}

    def fake_load_period_payload(period: str) -> dict[str, object]:
        call_count["count"] += 1
        return {
            "key": period,
            "label": period.title(),
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T00:00:00+00:00",
            "age_seconds": 0,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": f"{period}.analytics.json",
                "profile": f"{period}.profile.json",
            },
            "metrics": {
                "linhas": 1,
                "kg_total": 1.0,
                "mt_total": 1.0,
                "desvio_min_total": 0.0,
            },
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T00:00:00"},
        }

    monkeypatch.setattr(snapshot_dashboard, "load_period_payload", fake_load_period_payload)

    dashboard = snapshot_dashboard.build_dashboard_payload()

    assert call_count["count"] == 4
    assert dashboard["health"]["periods_loaded"] == 4
    assert dashboard["default_period"] in {"diario", "semanal", "mensal", "anual"}


def test_beneficiamento_health_payload_structures_attention_causes(monkeypatch) -> None:
    """Health deve expor causa estruturada e ação recomendada quando um período entra em atenção."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento import snapshot_dashboard

    fake_periods = {
        "diario": {
            "key": "diario",
            "label": "Diario",
            "available": True,
            "status": "attention",
            "updated_at": "2026-06-10T00:00:00+00:00",
            "age_seconds": 7200,
            "stale": True,
            "source": "snapshot_local",
            "snapshot_state": "stale",
            "reason_code": "snapshot_stale",
            "reason_message": "Snapshot acima da idade operacional esperada.",
            "recommended_action": (
                "Atualizar o período via runner controlado antes de usar "
                "o dado como base de decisão."
            ),
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [
                {
                    "code": "snapshot_stale",
                    "severity": "warn",
                    "period": "diario",
                    "label": "Diario",
                    "message": "Snapshot acima da idade operacional esperada.",
                    "action_hint": (
                        "Atualizar o período via runner controlado antes de "
                        "usar o dado como base de decisão."
                    ),
                }
            ],
            "source_files": {
                "analytics": "diario.analytics.json",
                "profile": "diario.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T00:00:00"},
        },
        "semanal": {
            "key": "semanal",
            "label": "Semanal",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T01:00:00+00:00",
            "age_seconds": 1800,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": "semanal.analytics.json",
                "profile": "semanal.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:00:00"},
        },
        "mensal": {
            "key": "mensal",
            "label": "Mensal",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T01:10:00+00:00",
            "age_seconds": 1200,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": "mensal.analytics.json",
                "profile": "mensal.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:10:00"},
        },
        "anual": {
            "key": "anual",
            "label": "Anual",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T01:20:00+00:00",
            "age_seconds": 600,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {"analytics": "anual.analytics.json", "profile": "anual.profile.json"},
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:20:00"},
        },
    }

    monkeypatch.setattr(snapshot_dashboard, "_load_periods_payload", lambda: fake_periods)

    payload = snapshot_dashboard.build_health_payload()

    assert payload["status"] == "attention"
    assert payload["reason_code"] == "snapshot_stale"
    assert payload["recommended_action"] == fake_periods["diario"]["recommended_action"]
    assert payload["summary"]["stale_periods"] == 1
    assert payload["summary"]["attention_periods"] == 1
    assert payload["latest_period"]["period"] == "anual"
    assert payload["issues"][0]["code"] == "snapshot_stale"
    assert payload["snapshot_files"]["diario"]["analytics"] == "diario.analytics.json"


def test_beneficiamento_health_prefers_most_severe_issue_as_reason(monkeypatch) -> None:
    """Quando houver mais de um desvio, o health deve expor a causa principal mais grave."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento import snapshot_dashboard

    fake_periods = {
        "diario": {
            "key": "diario",
            "label": "Diario",
            "available": False,
            "status": "missing",
            "updated_at": None,
            "age_seconds": None,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "missing",
            "reason_code": "snapshot_missing",
            "reason_message": "Snapshot local ausente ou ainda não promovido.",
            "recommended_action": (
                "Executar refresh controlado do período e promover os arquivos "
                "locais antes de depender do painel."
            ),
            "refresh_status": None,
            "historico_write_status": None,
            "quality_status": None,
            "issues": [
                {
                    "code": "snapshot_missing",
                    "severity": "error",
                    "period": "diario",
                    "label": "Diario",
                    "message": "Snapshot local ausente ou ainda não promovido.",
                    "action_hint": (
                        "Executar refresh controlado do período e promover os arquivos "
                        "locais antes de depender do painel."
                    ),
                }
            ],
            "source_files": {
                "analytics": None,
                "profile": None,
            },
            "metrics": {"linhas": 0},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {},
        },
        "semanal": {
            "key": "semanal",
            "label": "Semanal",
            "available": True,
            "status": "attention",
            "updated_at": "2026-06-10T01:00:00+00:00",
            "age_seconds": 7200,
            "stale": True,
            "source": "snapshot_local",
            "snapshot_state": "stale",
            "reason_code": "snapshot_stale",
            "reason_message": "Snapshot acima da idade operacional esperada.",
            "recommended_action": (
                "Atualizar o período via runner controlado antes de usar "
                "o dado como base de decisão."
            ),
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [
                {
                    "code": "snapshot_stale",
                    "severity": "warn",
                    "period": "semanal",
                    "label": "Semanal",
                    "message": "Snapshot acima da idade operacional esperada.",
                    "action_hint": (
                        "Atualizar o período via runner controlado antes de usar "
                        "o dado como base de decisão."
                    ),
                }
            ],
            "source_files": {
                "analytics": "semanal.analytics.json",
                "profile": "semanal.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:00:00"},
        },
        "mensal": {
            "key": "mensal",
            "label": "Mensal",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T01:10:00+00:00",
            "age_seconds": 1200,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": "mensal.analytics.json",
                "profile": "mensal.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:10:00"},
        },
        "anual": {
            "key": "anual",
            "label": "Anual",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T01:20:00+00:00",
            "age_seconds": 600,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": "anual.analytics.json",
                "profile": "anual.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:20:00"},
        },
    }

    monkeypatch.setattr(snapshot_dashboard, "_load_periods_payload", lambda: fake_periods)

    payload = snapshot_dashboard.build_health_payload()

    assert payload["status"] == "attention"
    assert payload["reason_code"] == "snapshot_missing"
    assert payload["recommended_action"] == fake_periods["diario"]["recommended_action"]
    assert payload["issues"][0]["code"] == "snapshot_missing"
    assert payload["summary"]["missing_periods"] == 1
    assert payload["summary"]["stale_periods"] == 1


def test_beneficiamento_health_expands_quality_blocked_details(monkeypatch) -> None:
    """Quality blocked deve descrever o tipo de bloqueio operacional com detalhe."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento import snapshot_dashboard

    fake_periods = {
        "diario": {
            "key": "diario",
            "label": "Diario",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T00:00:00+00:00",
            "age_seconds": 600,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": "diario.analytics.json",
                "profile": "diario.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T00:00:00"},
        },
        "semanal": {
            "key": "semanal",
            "label": "Semanal",
            "available": True,
            "status": "attention",
            "updated_at": "2026-06-10T01:00:00+00:00",
            "age_seconds": 1200,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "quality_missing_required_columns",
            "reason_message": (
                "Quality gate bloqueou o período por colunas obrigatórias ausentes: LOCAL_PRODUCAO"
            ),
            "recommended_action": (
                "Regerar o snapshot garantindo as colunas obrigatórias ausentes antes de "
                "promover o período."
            ),
            "refresh_status": "attention",
            "historico_write_status": "ok",
            "quality_status": "blocked",
            "issues": [
                {
                    "code": "quality_missing_required_columns",
                    "severity": "error",
                    "period": "semanal",
                    "label": "Semanal",
                    "message": (
                        "Quality gate bloqueou o período por colunas obrigatórias ausentes: LOCAL_PRODUCAO"
                    ),
                    "action_hint": (
                        "Regerar o snapshot garantindo as colunas obrigatórias ausentes antes de "
                        "promover o período."
                    ),
                }
            ],
            "source_files": {
                "analytics": "semanal.analytics.json",
                "profile": "semanal.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {
                "status": "blocked",
                "checks": [
                    {
                        "name": "schema_presence",
                        "status": "blocked",
                        "missing": ["LOCAL_PRODUCAO"],
                    }
                ],
                "critical_issues": [
                    "colunas obrigatorias ausentes: LOCAL_PRODUCAO",
                ],
            },
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:00:00"},
        },
        "mensal": {
            "key": "mensal",
            "label": "Mensal",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T01:10:00+00:00",
            "age_seconds": 1800,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": "mensal.analytics.json",
                "profile": "mensal.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:10:00"},
        },
        "anual": {
            "key": "anual",
            "label": "Anual",
            "available": True,
            "status": "healthy",
            "updated_at": "2026-06-10T01:20:00+00:00",
            "age_seconds": 2400,
            "stale": False,
            "source": "snapshot_local",
            "snapshot_state": "promoted",
            "reason_code": "healthy",
            "reason_message": "Snapshot válido e promovido.",
            "recommended_action": None,
            "refresh_status": "ok",
            "historico_write_status": "ok",
            "quality_status": "ok",
            "issues": [],
            "source_files": {
                "analytics": "anual.analytics.json",
                "profile": "anual.profile.json",
            },
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T01:20:00"},
        },
    }

    monkeypatch.setattr(snapshot_dashboard, "_load_periods_payload", lambda: fake_periods)

    payload = snapshot_dashboard.build_health_payload()

    assert payload["status"] == "attention"
    assert payload["reason_code"] == "quality_missing_required_columns"
    assert payload["recommended_action"] == (
        "Regerar o snapshot garantindo as colunas obrigatórias ausentes antes de "
        "promover o período."
    )
    assert payload["issues"][0]["code"] == "quality_missing_required_columns"
    assert "LOCAL_PRODUCAO" in payload["issues"][0]["message"]


def test_beneficiamento_historico_date_filter_includes_end_of_day(tmp_path) -> None:
    """A busca histórica deve considerar o fim do dia quando o filtro recebe só a data."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento.historico_db import buscar_historico, salvar_historico

    db_path = tmp_path / "beneficiamento_historico.db"
    salvar_historico(
        [
            {
                "NUMERO_OB": "123456",
                "SEQ": 1,
                "DATA_FIM": "2026-06-10T10:30:00",
                "NOME_MAQUINA": "JET 01",
                "CD_DS_FASE": "03 - TINGIMENTO",
                "CODIGO_ALTERNATIVO": "03212",
                "DESCR_ITEM": "Produto teste",
                "ARTIGO": "ART-1",
                "DESCR_ARTIGO": "Artigo teste",
                "COR": "AZUL",
                "DESCR_COR": "Azul",
                "QT_KG": 12.5,
                "QT_MT": 4.2,
                "MIN_REAL": 10.0,
                "MIN_PREV": 8.0,
                "TURNO_PROD": "1",
                "TURNO_DESC": "TURNO 1",
            }
        ],
        db_path=db_path,
    )

    records = buscar_historico({"dt_fim": "2026-06-10"}, db_path=db_path, limit=10)

    assert len(records) == 1
    assert records[0]["NUMERO_OB"] == "123456"


def test_beneficiamento_runner_marks_partial_failure_when_history_write_fails(
    tmp_path, monkeypatch
) -> None:
    """Falha ao persistir o histórico deve ser refletida no status final do refresh."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento import runner

    def fake_build_snapshot_payloads(*_unused_args, **_unused_kwargs):
        profile = {
            "total_rows": 1,
            "total_columns": 1,
            "constant_columns": [],
            "mostly_null_columns": [],
            "high_cardinality_columns": [],
            "columns": [],
            "window": {"dt_inicio": "2026-06-10", "dt_fim": "2026-06-10"},
        }
        analytics = {
            "geral": {"kg_total": 1.0},
            "qualidade": {"status": "ok"},
            "execucao_oracle": {
                "consulta_principal": {
                    "oracle_timeout_applied": True,
                    "oracle_timeout_ms": 18000,
                    "elapsed_seconds": 0.1,
                    "row_count": 1,
                }
            },
            "snapshot": {"period": "diario", "generated_at": "2026-06-10T00:00:00"},
        }
        records = [
            {
                "NUMERO_OB": "123456",
                "SEQ": 1,
                "DATA_FIM": "2026-06-10T10:30:00",
                "TURNO_PROD": "1",
                "TURNO_DESC": "TURNO 1",
            }
        ]
        return profile, analytics, records

    def fake_salvar_historico(*args, **kwargs):
        raise RuntimeError("SQLite indisponivel")

    monkeypatch.setattr(runner, "build_snapshot_payloads", fake_build_snapshot_payloads)
    monkeypatch.setattr(runner, "salvar_historico", fake_salvar_historico)

    sql_file = tmp_path / "dummy.sql"
    sql_file.write_text("select 1 from dual", encoding="utf-8")

    profile_path, analytics_path, refresh_status = runner.run_period(
        "diario",
        sql_file=sql_file,
        output_json=tmp_path / "profile.json",
        analytics_json=tmp_path / "analytics.json",
    )

    assert refresh_status == "partial_failure"
    assert profile_path.exists()
    assert analytics_path.exists()

    analytics = json.loads(analytics_path.read_text(encoding="utf-8"))
    assert analytics["snapshot"]["refresh_status"] == "partial_failure"
    assert analytics["snapshot"]["historico_write_status"] == "partial_failure"
    assert analytics["snapshot"]["historico_rows_saved"] == 0


def test_beneficiamento_runner_annual_slice_metadata_preserves_timeout_flag(monkeypatch) -> None:
    """A execução anual fatiada deve preservar a metadata real do call_timeout."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento import runner

    def fake_execute_query(*_unused_args, **_unused_kwargs):
        return runner.QueryResult(
            columns=[],
            rows=[],
            duplicate_columns={},
            metadata={
                "oracle_timeout_applied": False,
                "oracle_timeout_warning": "client did not apply timeout",
                "elapsed_seconds": 0.25,
                "row_count": 0,
            },
        )

    monkeypatch.setattr(runner, "execute_query", fake_execute_query)

    result = runner._execute_query_in_monthly_slices(
        "select 1 from dual",
        date(2026, 1, 1),
        date(2026, 3, 1),
        oracle_timeout_ms=18000,
        max_rows=None,
    )

    assert result.metadata["oracle_timeout_applied"] is False
    assert result.metadata["slice_count"] == 2
    assert "client did not apply timeout" in result.metadata["oracle_timeout_warning"]


def test_beneficiamento_runner_splits_timeout_failures_into_smaller_slices(monkeypatch) -> None:
    """Timeout de Oracle deve ser contornado com fatias menores sem perder os dados."""
    src_root = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from beneficiamento import runner

    calls: list[tuple[date, date]] = []

    def fake_execute_query(_sql, parameters, **_kwargs):
        start = parameters["dt_inicio"]
        end = parameters["dt_fim"]
        calls.append((start, end))
        if (end - start) > timedelta(days=1):
            raise RuntimeError("ORA-00028: sessão fechada pelo DBA")
        return runner.QueryResult(
            columns=["NUMERO_OB"],
            rows=[("123456",)],
            duplicate_columns={},
            metadata={
                "oracle_timeout_applied": True,
                "oracle_timeout_warning": "",
                "elapsed_seconds": 0.1,
                "row_count": 1,
            },
        )

    monkeypatch.setattr(runner, "execute_query", fake_execute_query)

    result = runner._execute_query_in_monthly_slices(
        "select 1 from dual",
        date(2026, 1, 1),
        date(2026, 1, 3),
        oracle_timeout_ms=18000,
        max_rows=None,
    )

    assert len(calls) == 3
    assert result.metadata["slice_count"] == 2
    assert result.metadata["row_count"] == 2
    assert result.metadata["oracle_timeout_applied"] is True
