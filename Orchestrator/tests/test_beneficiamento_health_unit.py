"""Testes unitários da classificação de saúde por período do Beneficiamento.

Cobre snapshot_period_health._build_period_health_context (regras de
precedência que decidem status/issue de um único período) e
snapshot_aggregator._build_health_from_periods (agregação cross-período).
Os testes existentes de saúde do domínio fazem monkeypatch de
load_period_payload, contornando por completo essa lógica de classificação;
aqui ela é exercitada diretamente, sem tocar Oracle/rede.
"""

# pylint: disable=too-many-arguments

import sys
from pathlib import Path
from typing import Any, cast

_SRC_ROOT = Path(__file__).resolve().parents[2] / "Produção Beneficimento" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from beneficiamento.snapshot_aggregator import (  # noqa: E402  pylint: disable=wrong-import-position
    _build_health_from_periods,
)
from beneficiamento.snapshot_period_health import (  # noqa: E402  pylint: disable=wrong-import-position
    _build_period_health_context,
)


def _context(
    tmp_path: Path,
    *,
    period: str = "diario",
    label: str = "Diário",
    exists: bool = True,
    available: bool = True,
    stale: bool = False,
    metrics: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analytics_path = tmp_path / f"{period}.analytics.json"
    if exists:
        analytics_path.write_text("{}", encoding="utf-8")
    return cast(
        "dict[str, Any]",
        _build_period_health_context(
            period=period,
            label=label,
            analytics_path=analytics_path,
            available=available,
            stale=stale,
            metrics=metrics if metrics is not None else {"linhas": 100},
            quality=quality if quality is not None else {},
            oracle=oracle if oracle is not None else {},
            snapshot=snapshot if snapshot is not None else {},
        ),
    )


# ---------------------------------------------------------------------------
# _build_period_health_context — precedência de _primary_issue_for_period
# ---------------------------------------------------------------------------


def test_snapshot_ausente_gera_status_missing(tmp_path: Path) -> None:
    ctx = _context(tmp_path, exists=False)
    assert ctx["status"] == "missing"
    assert ctx["reason_code"] == "snapshot_missing"
    assert ctx["snapshot_state"] == "missing"


def test_snapshot_invalido_gera_status_attention(tmp_path: Path) -> None:
    ctx = _context(tmp_path, exists=True, available=False)
    assert ctx["status"] == "attention"
    assert ctx["reason_code"] == "snapshot_invalid"
    assert ctx["snapshot_state"] == "invalid"


def test_falha_parcial_no_historico_gera_attention(tmp_path: Path) -> None:
    ctx = _context(tmp_path, snapshot={"historico_write_status": "partial_failure"})
    assert ctx["status"] == "attention"
    assert ctx["reason_code"] == "historico_partial_failure"
    assert ctx["snapshot_state"] == "invalid"


def test_falha_parcial_no_refresh_gera_attention(tmp_path: Path) -> None:
    ctx = _context(tmp_path, snapshot={"refresh_status": "partial_failure"})
    assert ctx["status"] == "attention"
    assert ctx["reason_code"] == "historico_partial_failure"


def test_quality_bloqueado_por_colunas_ausentes(tmp_path: Path) -> None:
    ctx = _context(
        tmp_path,
        quality={
            "status": "blocked",
            "checks": [{"name": "schema_presence", "missing": ["peso_kg"]}],
        },
    )
    assert ctx["status"] == "attention"
    assert ctx["reason_code"] == "quality_missing_required_columns"
    assert "peso_kg" in ctx["reason_message"]


def test_quality_bloqueado_por_nulos_criticos(tmp_path: Path) -> None:
    ctx = _context(
        tmp_path,
        quality={
            "status": "blocked",
            "checks": [
                {"name": "critical_nulls", "columns": [{"column": "producao_kg"}]}
            ],
        },
    )
    assert ctx["reason_code"] == "quality_critical_nulls"
    assert "producao_kg" in ctx["reason_message"]


def test_quality_bloqueado_por_chave_duplicada(tmp_path: Path) -> None:
    ctx = _context(
        tmp_path,
        quality={
            "status": "blocked",
            "checks": [{"name": "group_key_uniqueness", "duplicate_rows": 7}],
        },
    )
    assert ctx["reason_code"] == "quality_duplicate_keys"
    assert "7" in ctx["reason_message"]


def test_quality_bloqueado_generico_usa_critical_issues(tmp_path: Path) -> None:
    ctx = _context(
        tmp_path,
        quality={"status": "blocked", "critical_issues": ["motivo não mapeado"]},
    )
    assert ctx["reason_code"] == "quality_blocked"
    assert "motivo não mapeado" in ctx["reason_message"]


def test_sem_linhas_gera_status_no_data(tmp_path: Path) -> None:
    ctx = _context(tmp_path, metrics={"linhas": 0})
    assert ctx["status"] == "no_data"
    assert ctx["reason_code"] == "snapshot_no_data"


def test_stale_gera_status_attention(tmp_path: Path) -> None:
    ctx = _context(tmp_path, stale=True)
    assert ctx["status"] == "attention"
    assert ctx["reason_code"] == "snapshot_stale"


def test_quality_attention_gera_status_attention(tmp_path: Path) -> None:
    ctx = _context(tmp_path, quality={"status": "attention"})
    assert ctx["status"] == "attention"
    assert ctx["reason_code"] == "quality_attention"


def test_oracle_timeout_nao_aplicado_gera_attention(tmp_path: Path) -> None:
    ctx = _context(tmp_path, oracle={"oracle_timeout_applied": False})
    assert ctx["status"] == "attention"
    assert ctx["reason_code"] == "oracle_timeout_unapplied"


def test_tudo_ok_gera_status_healthy(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    assert ctx["status"] == "healthy"
    assert ctx["reason_code"] == "healthy"
    assert ctx["issues"] == [ctx["issues"][0]]  # única issue, sem secundárias


def test_precedencia_missing_vence_sobre_outras_condicoes(tmp_path: Path) -> None:
    """Ausência de snapshot precede qualquer outra condição na cadeia de
    _primary_issue_for_period, mesmo com stale/quality bloqueada presentes."""
    ctx = _context(
        tmp_path,
        exists=False,
        stale=True,
        quality={"status": "blocked", "critical_issues": ["x"]},
        oracle={"oracle_timeout_applied": False},
    )
    assert ctx["status"] == "missing"
    assert ctx["reason_code"] == "snapshot_missing"


def test_issues_secundarias_sao_acumuladas_sem_duplicar_a_primaria(
    tmp_path: Path,
) -> None:
    """no_data como causa primária não deve suprimir stale/oracle_timeout como
    issues secundárias, e a issue primária não deve se repetir na lista."""
    ctx = _context(
        tmp_path,
        metrics={"linhas": 0},
        stale=True,
        oracle={"oracle_timeout_applied": False},
    )
    assert ctx["status"] == "no_data"
    assert ctx["reason_code"] == "snapshot_no_data"
    codes = [issue["code"] for issue in ctx["issues"]]
    assert codes == ["snapshot_no_data", "snapshot_stale", "oracle_timeout_unapplied"]
    assert codes.count("snapshot_no_data") == 1


# ---------------------------------------------------------------------------
# _build_health_from_periods — agregação cross-período
# ---------------------------------------------------------------------------


def _envelope(
    tmp_path: Path,
    period: str,
    label: str,
    *,
    exists: bool = True,
    available: bool = True,
    stale: bool = False,
    updated_at: str | None = "2026-08-01T00:00:00+00:00",
    age_seconds: int | None = 10,
    metrics: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    oracle = oracle if oracle is not None else {}
    ctx = _context(
        tmp_path,
        period=period,
        label=label,
        exists=exists,
        available=available,
        stale=stale,
        metrics=metrics,
        quality=quality,
        oracle=oracle,
        snapshot=snapshot,
    )
    return {
        "label": label,
        "available": available,
        "status": ctx["status"],
        "updated_at": updated_at,
        "age_seconds": age_seconds,
        "stale": stale,
        "source": "snapshot_local",
        "snapshot_state": ctx["snapshot_state"],
        "reason_code": ctx["reason_code"],
        "reason_message": ctx["reason_message"],
        "recommended_action": ctx["recommended_action"],
        "refresh_status": ctx["refresh_status"],
        "historico_write_status": ctx["historico_write_status"],
        "quality_status": ctx["quality_status"],
        "issues": ctx["issues"],
        "source_files": {"analytics": str(tmp_path / f"{period}.analytics.json")},
        "oracle": oracle,
    }


def test_ambos_periodos_saudaveis_gera_status_healthy(tmp_path: Path) -> None:
    periods = {
        "diario": _envelope(tmp_path, "diario", "Diário"),
        "mensal": _envelope(tmp_path, "mensal", "Mensal"),
    }
    payload = _build_health_from_periods(periods)
    assert payload["status"] == "healthy"
    assert payload["periods_loaded"] == 2


def test_um_periodo_com_atencao_agrega_status_attention_com_reason_do_mais_severo(
    tmp_path: Path,
) -> None:
    periods = {
        "diario": _envelope(tmp_path, "diario", "Diário"),
        "mensal": _envelope(
            tmp_path, "mensal", "Mensal", quality={"status": "attention"}
        ),
    }
    payload = _build_health_from_periods(periods)
    assert payload["status"] == "attention"
    # issue de severidade "warn" (quality_attention) precede a "info" (healthy)
    # na ordenação de _build_issues, mesmo diario vindo antes na PERIOD_ORDER.
    assert payload["reason_code"] == "quality_attention"


def test_ambos_periodos_ausentes_gera_status_missing(tmp_path: Path) -> None:
    periods = {
        "diario": _envelope(
            tmp_path, "diario", "Diário", exists=False, available=False
        ),
        "mensal": _envelope(
            tmp_path, "mensal", "Mensal", exists=False, available=False
        ),
    }
    payload = _build_health_from_periods(periods)
    assert payload["status"] == "missing"
    assert payload["reason_code"] == "snapshot_missing"
    assert payload["periods_loaded"] == 0


def test_summary_conta_periodos_por_status_e_por_flags(tmp_path: Path) -> None:
    periods = {
        "diario": _envelope(tmp_path, "diario", "Diário", stale=True),
        "mensal": _envelope(tmp_path, "mensal", "Mensal", metrics={"linhas": 0}),
    }
    payload = _build_health_from_periods(periods)
    summary = payload["summary"]
    assert summary["available_periods"] == 2
    assert summary["attention_periods"] == 1
    assert summary["no_data_periods"] == 1
    assert summary["stale_periods"] == 1


def test_findings_reune_mensagem_de_cada_periodo_com_reason_message(
    tmp_path: Path,
) -> None:
    periods = {
        "diario": _envelope(tmp_path, "diario", "Diário", stale=True),
        "mensal": _envelope(tmp_path, "mensal", "Mensal"),
    }
    payload = _build_health_from_periods(periods)
    assert any("Diário" in finding for finding in payload["findings"])
    assert any("Mensal" in finding for finding in payload["findings"])
