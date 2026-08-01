# pylint: disable=useless-import-alias,unused-import,missing-function-docstring,duplicate-code
"""Leitura agregada dos snapshots do Beneficiamento para o Dashboard.

Ponto público do módulo: ``load_period_payload``, ``build_health_payload``,
``build_periods_payload``, ``build_dashboard_payload``.

As camadas internas estão em ``snapshot_period_health`` (análise por período)
e ``snapshot_aggregator`` (consolidação cross-período).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .health import HealthStatus as HealthStatus
from .settings import PERIOD_ORDER, get_period_config
from .snapshot_aggregator import (
    _build_health_from_periods,
    _build_period_highlights,
    _compute_health_status as _compute_health_status,
)
from .snapshot_period_health import _build_period_health_context
from .snapshot_store import read_json, snapshot_path


def _file_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    age = max(0.0, datetime.now().timestamp() - path.stat().st_mtime)
    return int(age)


def _file_updated_at(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def load_period_payload(period: str) -> dict[str, Any]:
    config = get_period_config(period)
    analytics_path = snapshot_path(period, "analytics")
    analytics = read_json(analytics_path)
    available = bool(analytics)
    updated_at = (
        (analytics.get("snapshot") or {}).get("generated_at")
    ) or _file_updated_at(analytics_path)
    age_seconds = _file_age_seconds(analytics_path)
    stale = bool(
        age_seconds is not None and age_seconds > (config.max_age_minutes * 60)
    )
    metrics = analytics.get("geral") or {}
    quality = analytics.get("qualidade") or {}
    rankings = {
        "por_maquina": analytics.get("por_maquina") or [],
        "por_fase": analytics.get("por_fase") or [],
        "por_turno": analytics.get("por_turno") or [],
    }
    oracle = ((analytics.get("execucao_oracle") or {}).get("consulta_principal")) or {}
    snapshot = analytics.get("snapshot") or {}
    health_context = _build_period_health_context(
        period=period,
        label=config.label,
        analytics_path=analytics_path,
        available=available,
        stale=stale,
        metrics=metrics,
        quality=quality,
        oracle=oracle,
        snapshot=snapshot,
    )
    return {
        "key": config.key,
        "label": config.label,
        "available": available,
        "status": health_context["status"],
        "updated_at": updated_at,
        "age_seconds": age_seconds,
        "stale": stale,
        "source": "snapshot_local",
        "snapshot_state": health_context["snapshot_state"],
        "reason_code": health_context["reason_code"],
        "reason_message": health_context["reason_message"],
        "recommended_action": health_context["recommended_action"],
        "refresh_status": health_context["refresh_status"],
        "historico_write_status": health_context["historico_write_status"],
        "quality_status": health_context["quality_status"],
        "issues": health_context["issues"],
        "source_files": {
            "analytics": str(analytics_path),
            "profile": None,
        },
        "metrics": metrics,
        "quality": quality,
        "profile": {},
        "rankings": rankings,
        "highlights": _build_period_highlights(period, metrics, analytics),
        "oracle": oracle,
        "snapshot": snapshot,
    }


def _load_periods_payload() -> dict[str, dict[str, Any]]:
    return {period: load_period_payload(period) for period in PERIOD_ORDER}


def _default_period_key(periods: dict[str, dict[str, Any]]) -> str:
    preferred_statuses = ("healthy", "attention", "no_data")
    for wanted_status in preferred_statuses:
        for period in PERIOD_ORDER:
            payload = periods[period]
            if payload.get("available") and payload.get("status") == wanted_status:
                return period
    for period in PERIOD_ORDER:
        if periods[period].get("available"):
            return period
    return "mensal"


def build_health_payload() -> dict[str, Any]:
    periods = _load_periods_payload()
    return _build_health_from_periods(periods)


def build_periods_payload() -> dict[str, Any]:
    periods = _load_periods_payload()
    periods_list = [periods[period] for period in PERIOD_ORDER]
    periods_map = {item["key"]: item for item in periods_list}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "default_period": _default_period_key(periods_map),
        "periods": periods_list,
    }


def build_dashboard_payload() -> dict[str, Any]:
    periods = _load_periods_payload()
    default_period = _default_period_key(periods)
    active_period = periods[default_period]
    comparison = []
    for period in PERIOD_ORDER:
        payload = periods[period]
        metrics = payload.get("metrics") or {}
        comparison.append(
            {
                "key": period,
                "label": payload.get("label"),
                "status": payload.get("status"),
                "available": payload.get("available"),
                "stale": payload.get("stale"),
                "updated_at": payload.get("updated_at"),
                "age_seconds": payload.get("age_seconds"),
                "kg_total": metrics.get("kg_total") or 0.0,
                "mt_total": metrics.get("mt_total") or 0.0,
                "linhas": metrics.get("linhas") or 0,
                "desvio_min_total": metrics.get("desvio_min_total") or 0.0,
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "default_period": default_period,
        "overall": {
            "period": default_period,
            "label": active_period.get("label"),
            "status": active_period.get("status"),
            "updated_at": active_period.get("updated_at"),
            "age_seconds": active_period.get("age_seconds"),
            "metrics": active_period.get("metrics") or {},
            "quality": active_period.get("quality") or {},
            "highlights": active_period.get("highlights") or {},
            "oracle": active_period.get("oracle") or {},
        },
        "comparison": comparison,
        "periods": periods,
        "health": _build_health_from_periods(periods),
    }
