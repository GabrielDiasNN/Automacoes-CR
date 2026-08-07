"""Testes de integração do módulo analítico SQLite de Beneficiamento."""

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import AUTH_HEADERS
from fastapi.testclient import TestClient


def test_beneficiamento_historico_init_db_maintains_derived_columns_and_indexes(
    tmp_path: Path,
) -> None:
    """Schema local deve garantir colunas derivadas e índices idempotentes do overview."""
    from beneficiamento.historico_db import (  # pylint: disable=import-outside-toplevel
        descrever_schema_historico,
        init_db,
    )

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


def test_beneficiamento_historico_analytics_endpoint_removed(
    client: TestClient,
) -> None:
    """O contrato analytics legado foi removido; a rota não deve mais existir."""
    response = client.get(
        "/api/beneficiamento/historico/analytics",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_beneficiamento_refresh_endpoint_rejects_invalid_period(
    client: TestClient,
) -> None:
    """O refresh on-demand só aceita os períodos suportados (diario/mensal)."""
    response = client.post(
        "/api/beneficiamento/refresh",
        headers=AUTH_HEADERS,
        params={"period": "anual"},
    )
    assert response.status_code == 400


def test_beneficiamento_overview_endpoint_contract(client: TestClient) -> None:
    """Valida o contrato V1 principal sem depender de refresh Oracle."""
    response = client.get(
        "/api/beneficiamento/overview",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload).issuperset(
        {
            "generated_at",
            "filters",
            "health",
            "kpis",
            "rankings",
            "series",
            "filter_options",
            "turnos",
            "treemap",
            "interaction",
        }
    )
    assert payload["health"]["source"] == "sqlite_historico"
    assert payload["filters"]["effective"]["dt_inicio"]
    assert payload["filters"]["effective"]["dt_fim"]
    assert payload["turnos"]
    assert payload["turnos"][0]["turno_label"].startswith("TURNO")

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
    assert payload["periods_total"] == 2
    assert payload["periods_loaded"] >= 0
    assert "reason_code" in payload
    assert "recommended_action" in payload
    assert "issues" in payload
    assert "summary" in payload
    assert "snapshot_files" in payload
    assert len(payload["periods"]) == 2
    assert {item["period"] for item in payload["periods"]} == {
        "diario",
        "mensal",
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
    assert payload["default_period"] in ["diario", "mensal"]
    assert len(payload["periods"]) == 2
    diario = next(item for item in payload["periods"] if item["key"] == "diario")
    assert set(diario).issuperset(
        {
            "key",
            "label",
            "available",
            "status",
            "metrics",
            "quality",
            "oracle",
            "snapshot",
        }
    )


def test_beneficiamento_dashboard_endpoint_contract(client: TestClient) -> None:
    """Agrega períodos, comparação e saúde para a home do Beneficiamento."""
    response = client.get(
        "/api/beneficiamento/dashboard",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload).issuperset(
        {
            "generated_at",
            "default_period",
            "overall",
            "comparison",
            "periods",
            "health",
        }
    )
    assert payload["default_period"] in payload["periods"]
    assert {item["key"] for item in payload["comparison"]} == {
        "diario",
        "mensal",
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
            "setor": "SETOR TINGIMENTO",
            "grupo_fase": "TINGIMENTO",
            "tipo_maquina": "HIDROEXTRATORA",
            "reprocesso": "0",
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
    assert effective["setor"] == "SETOR TINGIMENTO"
    assert effective["grupo_fase"] == "TINGIMENTO"
    assert effective["tipo_maquina"] == "HIDROEXTRATORA"
    assert effective["reprocesso"] == "0"


def test_beneficiamento_overview_rankings_gerais_nao_expoe_reprocesso(
    client: TestClient,
) -> None:
    """Reprocesso só tem sinal relativizado a uma fase (Tingimento); rankings
    gerais de setor/fase não devem mais expor esse campo."""
    response = client.get("/api/beneficiamento/overview", headers=AUTH_HEADERS)

    assert response.status_code == 200
    rankings = response.json()["rankings"]
    for item in rankings["fases_criticas"]:
        assert "reprocesso_kg_pct" not in item
        assert "amostra_insuficiente" not in item
    for item in rankings["setores"]:
        assert "reprocesso_kg_pct" not in item


def test_beneficiamento_tingimento_endpoint_contract(client: TestClient) -> None:
    """Painel dedicado de Tingimento: escopo fixo CODIGO_FASE=40."""
    response = client.get("/api/beneficiamento/tingimento", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert set(payload).issuperset(
        {"generated_at", "filters", "health", "resumo", "series", "rankings"}
    )
    resumo = payload["resumo"]
    for key in [
        "ob_distintas",
        "fases",
        "kg_total",
        "mt_total",
        "eficiencia_tempo_pct",
        "reprocesso_kg_pct",
        "setup_medio_min",
        "desvio_medio_min",
        "produtividade_kg_h",
    ]:
        assert key in resumo
    assert "por_maquina" in payload["rankings"]
    assert "por_cor" in payload["rankings"]
    assert "por_turno" in payload["rankings"]
    assert payload["rankings"]["por_maquina"]
    maquina_item = payload["rankings"]["por_maquina"][0]
    assert {
        "maquina",
        "fases",
        "kg_total",
        "eficiencia_tempo_pct",
        "setup_medio_min",
        "reprocesso_kg_pct",
        "amostra_insuficiente",
    }.issubset(maquina_item)


def test_beneficiamento_tingimento_ignora_filtros_gerais(client: TestClient) -> None:
    """O painel de tingimento e escopo fixo: so aceita dt_inicio/dt_fim."""
    response = client.get(
        "/api/beneficiamento/tingimento",
        headers=AUTH_HEADERS,
        params={"dt_inicio": "2026-01-01", "dt_fim": "2026-12-31"},
    )

    assert response.status_code == 200
    effective = response.json()["filters"]["effective"]
    assert effective["dt_inicio"] == "2026-01-01"
    assert effective["dt_fim"] == "2026-12-31"


def test_beneficiamento_overview_expoe_setores_e_treemap(client: TestClient) -> None:
    """Overview deve expor ranking por setor e agregação de treemap."""
    response = client.get("/api/beneficiamento/overview", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert "setores" in payload["rankings"]
    assert payload["rankings"]["setores"]
    assert payload["treemap"]
    node = payload["treemap"][0]
    assert {"setor", "fase", "maquina", "kg_total"}.issubset(node)


def test_beneficiamento_overview_kpis_expoe_planejado_pct(client: TestClient) -> None:
    """KPIs devem indicar quanto do total no recorte é produção apenas planejada."""
    response = client.get("/api/beneficiamento/overview", headers=AUTH_HEADERS)

    assert response.status_code == 200
    kpis = response.json()["kpis"]
    assert "fases_planejadas" in kpis
    assert "planejado_pct" in kpis
    assert kpis["fases_planejadas"] >= 1
    assert kpis["planejado_pct"] > 0.0


def test_beneficiamento_overview_filtra_por_status(client: TestClient) -> None:
    """Filtro de status deve restringir o recorte a confirmada ou planejada."""
    confirmada = client.get(
        "/api/beneficiamento/overview",
        headers=AUTH_HEADERS,
        params={"status": "confirmada"},
    ).json()
    planejada = client.get(
        "/api/beneficiamento/overview",
        headers=AUTH_HEADERS,
        params={"status": "planejada"},
    ).json()

    assert confirmada["kpis"]["planejado_pct"] == 0.0
    assert (
        planejada["kpis"]["fases_planejadas"] == planejada["kpis"]["fases_concluidas"]
    )
    assert planejada["filters"]["effective"]["status"] == "planejada"


def test_beneficiamento_produtos_autocomplete(client: TestClient) -> None:
    """Endpoint de autocomplete de produto deve buscar por código ou descrição."""
    response = client.get(
        "/api/beneficiamento/produtos",
        headers=AUTH_HEADERS,
        params={"q": "03212"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert any(item["codigo"] == "03212" for item in payload["items"])


def test_beneficiamento_produtos_autocomplete_requires_min_length(
    client: TestClient,
) -> None:
    """Termo de busca abaixo do mínimo deve ser rejeitado pela validação de query."""
    response = client.get(
        "/api/beneficiamento/produtos",
        headers=AUTH_HEADERS,
        params={"q": "a"},
    )

    assert response.status_code == 422


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
    import app.routers.beneficiamento as router  # pylint: disable=import-outside-toplevel

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
        params={"ob": "2401", "limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "total_records" in payload
    assert "records" in payload


@pytest.mark.parametrize("limit_value", [-1, 0, 5001])
def test_beneficiamento_historico_rejects_out_of_range_limit(
    client: TestClient, limit_value: int
) -> None:
    # Regressão do achado #7: limit sem clamp permitia limit=-1 (dump completo
    # no SQLite). Agora valores fora de [1, 5000] devem retornar 422.
    response = client.get(
        "/api/beneficiamento/historico",
        headers=AUTH_HEADERS,
        params={"ob": "2401", "limit": limit_value},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("page_value,limit_value", [(0, 10), (1, 0), (1, 201)])
def test_beneficiamento_detail_rejects_out_of_range_page_and_limit(
    client: TestClient, page_value: int, limit_value: int
) -> None:
    # Regressão do achado #17: page/limit não tinham nenhum bound (ge/le),
    # diferente da paginação de automations.py/executions.py (page: ge=1,
    # limit: ge=1/le=200). Agora valores fora do range devem retornar 422.
    response = client.get(
        "/api/beneficiamento/detail",
        headers=AUTH_HEADERS,
        params={
            "target_type": "produto",
            "alternativo": "03212",
            "page": page_value,
            "limit": limit_value,
        },
    )
    assert response.status_code == 422


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


def test_beneficiamento_detail_endpoint_returns_raw_payload_on_demand(
    client: TestClient,
) -> None:
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


def test_beneficiamento_snapshot_dashboard_reuses_period_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O dashboard de snapshots não deve reler os períodos ao montar health e overview."""
    from beneficiamento import (  # pylint: disable=import-outside-toplevel
        snapshot_dashboard,
    )

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

    monkeypatch.setattr(
        snapshot_dashboard, "load_period_payload", fake_load_period_payload
    )

    dashboard = snapshot_dashboard.build_dashboard_payload()

    assert call_count["count"] == 2
    assert dashboard["health"]["periods_loaded"] == 2
    assert dashboard["default_period"] in {"diario", "mensal"}


def test_beneficiamento_health_payload_structures_attention_causes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health deve expor causa estruturada e ação recomendada quando um período entra em atenção."""
    from beneficiamento import (  # pylint: disable=import-outside-toplevel
        snapshot_dashboard,
    )

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

    monkeypatch.setattr(
        snapshot_dashboard, "_load_periods_payload", lambda: fake_periods
    )

    payload = snapshot_dashboard.build_health_payload()

    assert payload["status"] == "attention"
    assert payload["reason_code"] == "snapshot_stale"
    assert payload["recommended_action"] == fake_periods["diario"]["recommended_action"]
    assert payload["summary"]["stale_periods"] == 1
    assert payload["summary"]["attention_periods"] == 1
    assert payload["latest_period"]["period"] == "mensal"
    assert payload["issues"][0]["code"] == "snapshot_stale"
    assert payload["snapshot_files"]["diario"]["analytics"] == "diario.analytics.json"


def test_beneficiamento_health_prefers_most_severe_issue_as_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quando houver mais de um desvio, o health deve expor a causa principal mais grave."""
    from beneficiamento import (  # pylint: disable=import-outside-toplevel
        snapshot_dashboard,
    )

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

    monkeypatch.setattr(
        snapshot_dashboard, "_load_periods_payload", lambda: fake_periods
    )

    payload = snapshot_dashboard.build_health_payload()

    assert payload["status"] == "attention"
    assert payload["reason_code"] == "snapshot_missing"
    assert payload["recommended_action"] == fake_periods["diario"]["recommended_action"]
    assert payload["issues"][0]["code"] == "snapshot_missing"
    assert payload["summary"]["missing_periods"] == 1
    assert payload["summary"]["stale_periods"] == 1


def test_beneficiamento_health_expands_quality_blocked_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quality blocked deve descrever o tipo de bloqueio operacional com detalhe."""
    from beneficiamento import (  # pylint: disable=import-outside-toplevel
        snapshot_dashboard,
    )

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
            "source_files": {"analytics": "diario.analytics.json", "profile": None},
            "metrics": {"linhas": 10},
            "quality": {"status": "ok"},
            "profile": {},
            "rankings": {},
            "highlights": {},
            "oracle": {"oracle_timeout_applied": True},
            "snapshot": {"generated_at": "2026-06-10T00:00:00"},
        },
        "mensal": {
            "key": "mensal",
            "label": "Mensal",
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
                    "period": "mensal",
                    "label": "Mensal",
                    "message": (
                        "Quality gate bloqueou o período por colunas obrigatórias ausentes: LOCAL_PRODUCAO"
                    ),
                    "action_hint": (
                        "Regerar o snapshot garantindo as colunas obrigatórias ausentes antes de "
                        "promover o período."
                    ),
                }
            ],
            "source_files": {"analytics": "mensal.analytics.json", "profile": None},
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
    }

    monkeypatch.setattr(
        snapshot_dashboard, "_load_periods_payload", lambda: fake_periods
    )

    payload = snapshot_dashboard.build_health_payload()

    assert payload["status"] == "attention"
    assert payload["reason_code"] == "quality_missing_required_columns"
    assert payload["recommended_action"] == (
        "Regerar o snapshot garantindo as colunas obrigatórias ausentes antes de "
        "promover o período."
    )
    assert payload["issues"][0]["code"] == "quality_missing_required_columns"
    assert "LOCAL_PRODUCAO" in payload["issues"][0]["message"]


def test_beneficiamento_historico_date_filter_includes_end_of_day(
    tmp_path: Path,
) -> None:
    """A busca histórica deve considerar o fim do dia quando o filtro recebe só a data."""
    from beneficiamento.historico_db import (  # pylint: disable=import-outside-toplevel
        buscar_historico,
        salvar_historico,
    )

    db_path = tmp_path / "beneficiamento_historico.db"
    salvar_historico(
        [
            {
                "NUMERO_OB": "123456",
                "SEQ": 1,
                "DATA_FIM": "2026-06-10T10:30:00",
                "NOME_MAQUINA": "JET 01",
                "DESCR_FASE": "03 - TINGIMENTO",
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falha ao persistir o histórico deve ser refletida no status final do refresh."""
    from beneficiamento import runner  # pylint: disable=import-outside-toplevel

    def fake_build_snapshot_payloads(
        *_unused_args: Any, **_unused_kwargs: Any
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
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

    def fake_salvar_historico(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("SQLite indisponivel")

    monkeypatch.setattr(runner, "build_snapshot_payloads", fake_build_snapshot_payloads)
    monkeypatch.setattr(runner, "salvar_historico", fake_salvar_historico)

    sql_file = tmp_path / "dummy.sql"
    sql_file.write_text("select 1 from dual", encoding="utf-8")

    analytics_path, refresh_status = runner.run_period(
        "diario",
        sql_file=sql_file,
        analytics_json=tmp_path / "analytics.json",
    )

    assert refresh_status == "partial_failure"
    assert analytics_path.exists()

    analytics = json.loads(analytics_path.read_text(encoding="utf-8"))
    assert analytics["snapshot"]["refresh_status"] == "partial_failure"
    assert analytics["snapshot"]["historico_write_status"] == "partial_failure"
    assert analytics["snapshot"]["historico_rows_saved"] == 0
