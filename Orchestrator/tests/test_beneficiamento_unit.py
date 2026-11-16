"""Testes unitarios da logica isolada do dominio Beneficiamento (core/ e data/)."""

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from beneficiamento.contracts import (
    obter_overview_historico,
)
from beneficiamento.core import (
    deviation_minutes,
    first_present,
    normalize_shift,
    parse_iso_date,
    resolve_alias,
    safe_strip,
    safe_text,
    time_efficiency,
    to_float,
    weighted_average,
)
from beneficiamento.data import (
    buscar_historico,
    explicar_busca_historico,
    salvar_historico,
)
from beneficiamento.data.schema import (
    SQLITE_BUSY_TIMEOUT_MS,
    apply_pragmas,
    init_db,
)
from beneficiamento.settings import (
    get_period_config,
)
from beneficiamento.snapshot_dashboard import (
    HealthStatus,
    _compute_health_status,
)

_SRC_ROOT = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ---------------------------------------------------------------------------
# core.coercion
# ---------------------------------------------------------------------------
def test_to_float_handles_comma_none_and_garbage() -> None:

    assert to_float("120,5") == 120.5
    assert to_float(None) == 0.0
    assert to_float("abc") == 0.0
    assert to_float(7) == 7.0


def test_safe_text_and_safe_strip_defaults() -> None:

    assert safe_text(None) == "SEM_VALOR"
    assert safe_text("  ") == "SEM_VALOR"
    assert safe_text("  X ") == "X"
    assert safe_strip(None) == ""
    assert safe_strip("  X ") == "X"


def test_parse_iso_date_valid_and_invalid() -> None:

    assert parse_iso_date("2026-06-12T08:00:00") == date(2026, 6, 12)
    assert parse_iso_date("nao-data") is None
    assert parse_iso_date(None) is None


# ---------------------------------------------------------------------------
# core.shifts
# ---------------------------------------------------------------------------
def test_normalize_shift_prefers_desc_then_falls_back() -> None:

    assert normalize_shift({"TURNO_PROD": "1", "TURNO_DESC": "TURNO A"}) == (
        "1",
        "TURNO A",
    )
    assert normalize_shift({"TURNO_PROD": "2"}) == ("2", "TURNO 2")
    assert normalize_shift({"TURNO": "3"}) == ("3", "TURNO 3")
    assert normalize_shift({}) == (None, None)


# ---------------------------------------------------------------------------
# core.metrics
# ---------------------------------------------------------------------------
def test_time_efficiency_guards_division_by_zero() -> None:

    assert time_efficiency(90, 0) == 0.0
    assert time_efficiency(90, 100) == 90.0


def test_weighted_average_ignores_none_and_empty() -> None:

    assert weighted_average([], 2) is None
    assert weighted_average([None, None], 2) is None
    assert weighted_average([10, None, 20], 2) == 15.0


def test_deviation_minutes() -> None:

    assert deviation_minutes(90, 100) == 10.0
    assert deviation_minutes(100, 90) == -10.0


# ---------------------------------------------------------------------------
# core.schema
# ---------------------------------------------------------------------------
def test_resolve_alias_first_present_wins() -> None:

    assert resolve_alias({"QUANT_PROD": 5, "QT_KG": 9}, "volume_kg") == 5
    assert resolve_alias({"QT_KG": 9}, "volume_kg") == 9
    assert resolve_alias({}, "volume_kg") is None
    assert first_present({"B": 2}, ("A", "B")) == 2


def test_resolve_alias_unknown_raises() -> None:

    with pytest.raises(KeyError):
        resolve_alias({}, "alias_inexistente")


# ---------------------------------------------------------------------------
# data.writer / data.queries
# ---------------------------------------------------------------------------
def _sample_records() -> list[dict[str, Any]]:
    return [
        {
            "NUMERO_OB": "1001",
            "SEQ": 1,
            "DATA_FIM": "2026-06-10T08:00:00",
            "NOME_MAQUINA": "JET-01",
            "DESCR_FASE": "03 - TINGIMENTO",
            "CODIGO_ALTERNATIVO": "ABC",
            "QT_KG": "120,5",
            "MIN_REAL": 100,
            "MIN_PREV": 90,
            "TURNO_PROD": "1",
            "TURNO_DESC": "TURNO A",
            "ANO_MES": "202606",
            "EXTRA_ORACLE": "apenas no blob",
        },
        {"NUMERO_OB": "", "SEQ": 9, "QT_KG": 10},  # deve ser pulado
        {
            "NUMERO_OB": "1002",
            "SEQ": 1,
            "NOME_MAQUINA": "JET-02",
            "REDUZ": "R9",
            "QT_KG": 50,
            "TURNO_PROD": "2",
        },
    ]


def test_salvar_historico_skips_empty_ob_and_is_idempotent(tmp_path: Path) -> None:

    db = tmp_path / "h.db"
    assert salvar_historico(_sample_records(), db_path=db) == 2
    assert salvar_historico(_sample_records(), db_path=db) == 2  # INSERT OR REPLACE
    assert salvar_historico([], db_path=db) == 0


def test_salvar_historico_coerces_typed_columns_and_derives_keys(
    tmp_path: Path,
) -> None:

    db = tmp_path / "h.db"
    salvar_historico(_sample_records(), db_path=db)
    rows = buscar_historico({}, db_path=db)
    by_ob = {row["NUMERO_OB"]: row for row in rows}

    assert by_ob["1001"]["QT_KG"] == 120.5  # virgula decimal coergida
    assert by_ob["1001"]["CODIGO_KEY"] == "ABC"
    assert by_ob["1002"]["CODIGO_KEY"] == "R9"  # fallback REDUZ
    assert by_ob["1001"]["TURNO_PROD"] == "1"
    assert by_ob["1001"]["TURNO_DESC"] == "TURNO A"
    assert by_ob["1002"]["TURNO_DESC"] == "TURNO 2"  # rotulo derivado


def test_buscar_historico_typed_projection_omits_blob_unless_requested(
    tmp_path: Path,
) -> None:

    db = tmp_path / "h.db"
    salvar_historico(_sample_records(), db_path=db)

    default = buscar_historico({"ob": "1001"}, db_path=db)[0]
    assert "DADOS_COMPLETOS" not in default

    raw = buscar_historico({"ob": "1001"}, db_path=db, include_raw=True)[0]
    assert raw["DADOS_COMPLETOS"]["EXTRA_ORACLE"] == "apenas no blob"


def test_buscar_historico_filters_by_ob_prefix_and_date_range(tmp_path: Path) -> None:

    db = tmp_path / "h.db"
    salvar_historico(_sample_records(), db_path=db)

    assert {r["NUMERO_OB"] for r in buscar_historico({"ob": "1001"}, db_path=db)} == {
        "1001"
    }
    janela = buscar_historico(
        {"dt_inicio": "2026-06-10", "dt_fim": "2026-06-10"}, db_path=db
    )
    assert {r["NUMERO_OB"] for r in janela} == {"1001"}


def test_sql_aggregation_matches_typed_records(tmp_path: Path) -> None:

    db = tmp_path / "h.db"
    salvar_historico(_sample_records(), db_path=db)

    typed_records = buscar_historico(
        {"dt_inicio": "2026-06-10", "dt_fim": "2026-06-10"},
        db_path=db,
    )
    python_total = round(sum(float(row["QT_KG"] or 0) for row in typed_records), 2)
    overview = obter_overview_historico(
        {"dt_inicio": "2026-06-10", "dt_fim": "2026-06-10"},
        db_path=db,
    )

    assert overview["kpis"]["kg_total"] == python_total == 120.5


def test_date_range_query_plan_uses_temporal_index(tmp_path: Path) -> None:

    db = tmp_path / "h.db"
    salvar_historico(_sample_records(), db_path=db)

    plan = explicar_busca_historico(
        {"dt_inicio": "2026-06-10", "dt_fim": "2026-06-10"},
        db_path=db,
    )

    assert any("idx_producao_data" in step for step in plan)


def test_compute_health_status_has_explicit_precedence() -> None:

    periods = {
        "diario": {
            "status": "attention",
            "issues": [
                {
                    "code": "snapshot_stale",
                    "severity": "warn",
                    "period": "diario",
                    "action_hint": "Atualizar snapshot.",
                }
            ],
        },
        "mensal": {
            "status": "missing",
            "issues": [
                {
                    "code": "snapshot_missing",
                    "severity": "error",
                    "period": "mensal",
                    "action_hint": "Executar refresh.",
                }
            ],
        },
    }

    status, reason, action = _compute_health_status(periods)

    assert status is HealthStatus.ATTENTION
    assert reason == "snapshot_missing"
    assert action == "Executar refresh."


def test_get_period_config_deriva_max_age_do_ambiente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.delenv("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("BENEFICIAMENTO_MENSAL_INTERVAL_SECONDS", raising=False)
    assert get_period_config("diario").max_age_minutes == 17
    assert get_period_config("mensal").max_age_minutes == 25

    monkeypatch.setenv("BENEFICIAMENTO_LIVE_INTERVAL_SECONDS", "1800")
    monkeypatch.setenv("BENEFICIAMENTO_MENSAL_INTERVAL_SECONDS", "86400")
    assert get_period_config("diario").max_age_minutes == 45
    assert get_period_config("mensal").max_age_minutes == 1560


def test_apply_pragmas_define_busy_timeout(tmp_path: Path) -> None:

    executed: list[str] = []
    fake_conn = cast(Any, SimpleNamespace(execute=executed.append))
    apply_pragmas(fake_conn)

    assert f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};" in executed
    # Garante tambem em conexao real via init_db que o PRAGMA e aceito pelo SQLite.
    db = init_db(tmp_path / "h.db")
    assert db.exists()
