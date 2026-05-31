"""Testes da API snapshot-first de Beneficiamento."""
# mypy: ignore-errors
# pylint: disable=import-outside-toplevel,import-error

import json
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import AUTH_HEADERS


def _write_period_snapshot(root: Path, period: str, *, timeout_applied: bool = True) -> None:
    snapshot_root = root / "Produção Beneficimento" / "snapshots" / "latest"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    analytics = {
        "geral": {
            "linhas": 2,
            "ob_distintas": 2,
            "maquinas_distintas": 1,
            "fases_distintas": 1,
            "turnos_distintos": 1,
            "kg_total": 120.5,
            "mt_total": 44.2,
            "carga_prev_grupo_total": 130,
            "min_prev_total": 20,
            "min_real_total": 22,
            "desvio_min_total": 2,
            "desvio_min_abs_total": 2,
            "rendimento_medio_ponderado": 1.2345,
            "efic_carga_media_ponderada": 92.1,
        },
        "por_maquina": [{"NUMERO_MAQUINA": "101", "NOME_MAQUINA": "M1", "kg_total": 120.5}],
        "por_fase": [{"CD_DS_FASE": "F1", "kg_total": 120.5}],
        "por_turno": [{"TURNO_PROD": "1", "TURNO_DESC": "MANHA", "kg_total": 120.5}],
        "destaques": {
            "maquinas_por_desvio_min_abs": [],
            "fases_por_desvio_min_abs": [],
        },
        "qualidade": {
            "status": "ok",
            "ready_for_kpi": True,
            "ready_for_powerbi": True,
            "ready_for_python": True,
            "duplicate_key_rows": 0,
            "duplicate_key_fields": [],
            "critical_issues": [],
            "warnings": [],
            "checks": [],
        },
        "execucao_oracle": {
            "consulta_principal": {
                "elapsed_seconds": 0.12,
                "oracle_timeout_ms": 18000,
                "oracle_timeout_applied": timeout_applied,
                "row_count": 2,
            }
        },
    }
    profile = {
        "total_rows": 2,
        "total_columns": 4,
        "constant_columns": [],
        "mostly_null_columns": [],
        "high_cardinality_columns": [],
        "columns": [],
    }
    (snapshot_root / f"{period}.analytics.json").write_text(
        json.dumps(analytics), encoding="utf-8"
    )
    (snapshot_root / f"{period}.profile.json").write_text(
        json.dumps(profile), encoding="utf-8"
    )


def test_beneficiamento_dashboard_reads_snapshots_without_oracle(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    import app.routers.beneficiamento as beneficiamento_router

    for period in ("diario", "semanal", "mensal", "anual"):
        _write_period_snapshot(tmp_path, period)
    monkeypatch.setattr(beneficiamento_router, "PROJECT_ROOT", str(tmp_path))

    response = client.get("/api/beneficiamento/dashboard", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall"]["periods_loaded"] == 4
    assert payload["overall"]["status"] == "ok"
    assert payload["periods"]["diario"]["metrics"]["kg_total"] == 120.5
    assert payload["health"]["periods"][0]["oracle_timeout_applied"] is True


def test_beneficiamento_health_flags_timeout_not_applied(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    import app.routers.beneficiamento as beneficiamento_router

    for period in ("diario", "semanal", "mensal", "anual"):
        _write_period_snapshot(tmp_path, period, timeout_applied=False)
    monkeypatch.setattr(beneficiamento_router, "PROJECT_ROOT", str(tmp_path))

    response = client.get("/api/beneficiamento/health", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attention"
    assert any("call_timeout Oracle nao aplicado" in item for item in payload["findings"])


def test_beneficiamento_period_endpoint_validates_period(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    import app.routers.beneficiamento as beneficiamento_router

    _write_period_snapshot(tmp_path, "diario")
    monkeypatch.setattr(beneficiamento_router, "PROJECT_ROOT", str(tmp_path))

    ok_response = client.get("/api/beneficiamento/periods/diario", headers=AUTH_HEADERS)
    missing_response = client.get("/api/beneficiamento/periods/invalido", headers=AUTH_HEADERS)

    assert ok_response.status_code == 200
    assert ok_response.json()["key"] == "diario"
    assert missing_response.status_code == 404
