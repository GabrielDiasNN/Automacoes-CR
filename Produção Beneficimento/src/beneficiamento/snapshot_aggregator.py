# pylint: disable=too-many-locals
"""Agregação cross-período dos snapshots do Beneficiamento.

Consolida issues, resumo e payload de health a partir dos payloads
individuais de cada período. Consumido por ``snapshot_dashboard``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .health import HealthStatus, compute_health_status
from .settings import PERIOD_ORDER
from .snapshot_store import snapshot_path


def _safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _build_period_highlights(
    period: str,
    metrics: dict[str, Any],
    analytics: dict[str, Any],
) -> dict[str, Any]:
    top_machine = ((analytics.get("destaques") or {}).get("maquinas_por_kg") or [None])[
        0
    ] or {}
    top_phase = ((analytics.get("destaques") or {}).get("fases_por_kg") or [None])[
        0
    ] or {}
    top_turno = ((analytics.get("destaques") or {}).get("turnos_por_kg") or [None])[
        0
    ] or {}
    return {
        "period": period,
        "kg_total": metrics.get("kg_total") or 0.0,
        "mt_total": metrics.get("mt_total") or 0.0,
        "efic_carga_media_ponderada": metrics.get("efic_carga_media_ponderada"),
        "desvio_min_total": metrics.get("desvio_min_total"),
        "top_machine": {
            "codigo": top_machine.get("NUMERO_MAQUINA"),
            "nome": top_machine.get("NOME_MAQUINA"),
            "kg_total": top_machine.get("kg_total"),
        },
        "top_phase": {
            "fase": top_phase.get("CD_DS_FASE"),
            "kg_total": top_phase.get("kg_total"),
        },
        "top_turno": {
            "turno": top_turno.get("TURNO_DESC"),
            "kg_total": top_turno.get("kg_total"),
        },
    }


def _build_period_items(periods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    period_items = []
    for period in PERIOD_ORDER:
        payload = periods[period]
        oracle = payload.get("oracle") or {}
        period_items.append(
            {
                "period": period,
                "status": payload.get("status"),
                "available": payload.get("available"),
                "stale": payload.get("stale"),
                "updated_at": payload.get("updated_at"),
                "age_seconds": payload.get("age_seconds"),
                "source": payload.get("source"),
                "snapshot_state": payload.get("snapshot_state"),
                "reason_code": payload.get("reason_code"),
                "reason_message": payload.get("reason_message"),
                "recommended_action": payload.get("recommended_action"),
                "refresh_status": payload.get("refresh_status"),
                "historico_write_status": payload.get("historico_write_status"),
                "quality_status": payload.get("quality_status"),
                "oracle_elapsed_seconds": _safe_float(oracle.get("elapsed_seconds")),
                "oracle_timeout_ms": _safe_int(oracle.get("oracle_timeout_ms")),
                "oracle_timeout_applied": oracle.get("oracle_timeout_applied"),
                "issues": payload.get("issues") or [],
                "source_files": payload.get("source_files") or {},
            }
        )
    return period_items


def _summary_from_periods(periods: dict[str, dict[str, Any]]) -> dict[str, int]:
    summary = {
        "available_periods": 0,
        "healthy_periods": 0,
        "attention_periods": 0,
        "missing_periods": 0,
        "no_data_periods": 0,
        "stale_periods": 0,
        "invalid_periods": 0,
        "timeout_unapplied_periods": 0,
        "partial_failure_periods": 0,
    }
    for payload in periods.values():
        if payload.get("available"):
            summary["available_periods"] += 1
        status = str(payload.get("status") or "")
        if status == "healthy":
            summary["healthy_periods"] += 1
        elif status == "attention":
            summary["attention_periods"] += 1
        elif status == "missing":
            summary["missing_periods"] += 1
        elif status == "no_data":
            summary["no_data_periods"] += 1
        if payload.get("stale"):
            summary["stale_periods"] += 1
        if payload.get("snapshot_state") == "invalid":
            summary["invalid_periods"] += 1
        if (payload.get("oracle") or {}).get("oracle_timeout_applied") is False:
            summary["timeout_unapplied_periods"] += 1
        if payload.get("historico_write_status") == "partial_failure":
            summary["partial_failure_periods"] += 1
    return summary


def _latest_period(periods: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    for period in PERIOD_ORDER:
        payload = periods[period]
        if payload.get("updated_at") is None:
            continue
        age_seconds = payload.get("age_seconds")
        sort_age = age_seconds if isinstance(age_seconds, int) else 10**12
        candidates.append((sort_age, period, payload))
    if not candidates:
        return None
    _, period, payload = min(
        candidates, key=lambda item: (item[0], PERIOD_ORDER.index(item[1]))
    )
    return {
        "period": period,
        "label": payload.get("label") or period,
        "status": payload.get("status") or "missing",
        "updated_at": payload.get("updated_at"),
        "age_seconds": payload.get("age_seconds"),
    }


def _build_findings(periods: dict[str, dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for period in PERIOD_ORDER:
        payload = periods[period]
        reason_message = payload.get("reason_message")
        if reason_message:
            findings.append(f"{payload.get('label') or period}: {reason_message}")
    return findings


def _build_issues(periods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for period in PERIOD_ORDER:
        payload_issues = periods.get(period, {}).get("issues") or []
        for issue in payload_issues:
            issues.append(issue)
    severity_rank = {"error": 0, "warn": 1, "info": 2}
    return sorted(
        issues,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or "info").lower(), 3),
            (
                PERIOD_ORDER.index(str(item.get("period") or "mensal"))
                if str(item.get("period") or "") in PERIOD_ORDER
                else len(PERIOD_ORDER)
            ),
            str(item.get("code") or ""),
        ),
    )


def _primary_health_issue(periods: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    issues = _build_issues(periods)
    return issues[0] if issues else None


def _build_snapshot_files(
    periods: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        period: periods[period].get("source_files") or {} for period in PERIOD_ORDER
    }


def _compute_health_status(
    periods: dict[str, dict[str, Any]],
) -> tuple[HealthStatus, str, str | None]:
    """Compatibilidade interna para testes e consumidores existentes."""
    return compute_health_status(periods, _primary_health_issue)


def _build_health_from_periods(periods: dict[str, dict[str, Any]]) -> dict[str, Any]:
    status, reason_code, recommended_action = _compute_health_status(periods)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_root": str(snapshot_path("diario", "analytics").parent),
        "source": "snapshot_local",
        "status": status.value,
        "reason_code": reason_code,
        "recommended_action": recommended_action,
        "periods_total": len(PERIOD_ORDER),
        "periods_loaded": sum(1 for item in periods.values() if item.get("available")),
        "findings": _build_findings(periods),
        "issues": _build_issues(periods),
        "summary": _summary_from_periods(periods),
        "latest_period": _latest_period(periods),
        "snapshot_files": _build_snapshot_files(periods),
        "periods": _build_period_items(periods),
    }
