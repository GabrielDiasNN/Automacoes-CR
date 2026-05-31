"""Serviço snapshot-first do dashboard analítico de Beneficiamento."""
# pylint: disable=too-many-locals,relative-beyond-top-level

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..schemas.common import format_dt_br

PERIOD_ORDER = ("diario", "semanal", "mensal", "anual")
PERIOD_LABELS = {
    "diario": "Diário",
    "semanal": "Semanal",
    "mensal": "Mensal",
    "anual": "Anual",
}
MAX_AGE_SECONDS = {
    "diario": 90 * 60,
    "semanal": 15 * 60 * 60,
    "mensal": 15 * 60 * 60,
    "anual": 30 * 60 * 60,
}
PERIOD_FILE_CANDIDATES = {
    key: {
        "analytics": (
            f"{key}.analytics.json",
            f"quality_{key}.analytics.json",
            f"agg_{key}.analytics.json",
        ),
        "profile": (
            f"{key}.profile.json",
            f"quality_{key}.profile.json",
            f"agg_{key}.profile.json",
        ),
    }
    for key in PERIOD_ORDER
}


def _resolve_snapshot_root(project_root: str) -> Path:
    override = os.environ.get("BENEFICIAMENTO_SNAPSHOT_DIR") or os.environ.get(
        "BENEFICIAMENTO_ANALYTICS_DIR"
    )
    if override:
        return Path(override).expanduser().resolve()

    domain_root = Path(project_root).resolve() / "Produção Beneficimento"
    snapshot_root = domain_root / "snapshots" / "latest"
    if snapshot_root.exists():
        return snapshot_root
    return domain_root / "analysis_tmp"


def _first_existing(base: Path, candidates: tuple[str, ...]) -> Path | None:
    for candidate in candidates:
        path = base / candidate
        if path.exists():
            return path
    return None


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _age_seconds(mtime: float | None) -> int | None:
    if mtime is None:
        return None
    return max(0, int(datetime.now().timestamp() - mtime))


def _summarize_metrics(analytics: dict[str, Any]) -> dict[str, Any]:
    geral = analytics.get("geral") or {}
    return {
        "linhas": geral.get("linhas", 0),
        "ob_distintas": geral.get("ob_distintas", 0),
        "maquinas_distintas": geral.get("maquinas_distintas", 0),
        "fases_distintas": geral.get("fases_distintas", 0),
        "turnos_distintos": geral.get("turnos_distintos", 0),
        "kg_total": round(float(geral.get("kg_total", 0) or 0), 2),
        "mt_total": round(float(geral.get("mt_total", 0) or 0), 2),
        "carga_prev_grupo_total": round(
            float(geral.get("carga_prev_grupo_total", 0) or 0), 2
        ),
        "min_prev_total": round(float(geral.get("min_prev_total", 0) or 0), 2),
        "min_real_total": round(float(geral.get("min_real_total", 0) or 0), 2),
        "desvio_min_total": round(float(geral.get("desvio_min_total", 0) or 0), 2),
        "desvio_min_abs_total": round(
            float(geral.get("desvio_min_abs_total", 0) or 0), 2
        ),
        "rendimento_medio_ponderado": float(
            geral.get("rendimento_medio_ponderado", 0) or 0
        ),
        "efic_carga_media_ponderada": float(
            geral.get("efic_carga_media_ponderada", 0) or 0
        ),
    }


def _summarize_quality(analytics: dict[str, Any]) -> dict[str, Any]:
    quality = analytics.get("qualidade") or {}
    if not quality:
        return {
            "status": "missing",
            "ready_for_kpi": False,
            "ready_for_powerbi": False,
            "ready_for_python": False,
            "duplicate_key_rows": 0,
            "duplicate_key_fields": [],
            "critical_issues": ["Arquivo de analytics não encontrado."],
            "warnings": [],
            "checks": [],
            "issues_total": 1,
        }

    critical_issues = list(quality.get("critical_issues") or [])
    warnings = list(quality.get("warnings") or [])
    return {
        "status": str(quality.get("status") or "unknown").lower(),
        "ready_for_kpi": bool(quality.get("ready_for_kpi")),
        "ready_for_powerbi": bool(quality.get("ready_for_powerbi")),
        "ready_for_python": bool(quality.get("ready_for_python")),
        "duplicate_key_rows": int(quality.get("duplicate_key_rows") or 0),
        "duplicate_key_fields": list(quality.get("duplicate_key_fields") or []),
        "critical_issues": critical_issues,
        "warnings": warnings,
        "checks": list(quality.get("checks") or []),
        "issues_total": len(critical_issues) + len(warnings),
    }


def _summarize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    constant_columns = list(profile.get("constant_columns") or [])
    mostly_null_columns = list(profile.get("mostly_null_columns") or [])
    high_cardinality_columns = list(profile.get("high_cardinality_columns") or [])
    return {
        "total_rows": int(profile.get("total_rows") or 0),
        "total_columns": int(profile.get("total_columns") or 0),
        "constant_count": len(constant_columns),
        "mostly_null_count": len(mostly_null_columns),
        "high_cardinality_count": len(high_cardinality_columns),
        "constant_columns": constant_columns,
        "mostly_null_columns": mostly_null_columns,
        "high_cardinality_columns": high_cardinality_columns,
    }


def _top_items(items: Any, limit: int = 5) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [item for item in items[:limit] if isinstance(item, dict)]


def _summarize_rankings(analytics: dict[str, Any]) -> dict[str, Any]:
    destaques = analytics.get("destaques") or {}
    return {
        "machines_by_kg": _top_items(analytics.get("por_maquina"), 5),
        "phases_by_kg": _top_items(analytics.get("por_fase"), 5),
        "turns_by_kg": _top_items(analytics.get("por_turno"), 3),
        "machines_by_desvio_min_abs": _top_items(
            destaques.get("maquinas_por_desvio_min_abs"), 5
        ),
        "phases_by_desvio_min_abs": _top_items(
            destaques.get("fases_por_desvio_min_abs"), 5
        ),
    }


def _extract_oracle_meta(analytics: dict[str, Any]) -> dict[str, Any]:
    meta = ((analytics.get("execucao_oracle") or {}).get("consulta_principal") or {})
    return {
        "elapsed_seconds": meta.get("elapsed_seconds"),
        "oracle_timeout_ms": meta.get("oracle_timeout_ms"),
        "oracle_timeout_applied": meta.get("oracle_timeout_applied"),
        "oracle_timeout_warning": meta.get("oracle_timeout_warning") or "",
        "row_count": meta.get("row_count"),
        "max_rows_limit": meta.get("max_rows_limit"),
    }


def _period_operational_status(
    available: bool,
    quality: dict[str, Any],
    stale: bool,
    oracle: dict[str, Any],
) -> str:
    if not available:
        return "missing"
    quality_status = str(quality.get("status") or "missing").lower()
    if quality_status == "blocked":
        return "blocked"
    if stale or oracle.get("oracle_timeout_applied") is False:
        return "attention"
    if quality_status == "attention":
        return "attention"
    return "ok"


def _build_period_summary(
    period_key: str,
    analytics_path: Path | None,
    profile_path: Path | None,
) -> tuple[dict[str, Any], float | None]:
    analytics = _load_json(analytics_path)
    profile = _load_json(profile_path)
    source_times = [
        path.stat().st_mtime
        for path in (analytics_path, profile_path)
        if path is not None and path.exists()
    ]
    updated_mtime = max(source_times) if source_times else None
    age = _age_seconds(updated_mtime)
    stale = bool(age is not None and age > MAX_AGE_SECONDS[period_key])
    metrics = _summarize_metrics(analytics)
    quality = _summarize_quality(analytics)
    profile_summary = _summarize_profile(profile)
    rankings = _summarize_rankings(analytics)
    oracle = _extract_oracle_meta(analytics)
    available = bool(analytics)
    status = _period_operational_status(available, quality, stale, oracle)

    period_payload = {
        "key": period_key,
        "label": PERIOD_LABELS.get(period_key, period_key),
        "available": available,
        "status": status,
        "updated_at": format_dt_br(datetime.fromtimestamp(updated_mtime))
        if updated_mtime is not None
        else None,
        "age_seconds": age,
        "stale": stale,
        "source_files": {
            "analytics": analytics_path.name if analytics_path else None,
            "profile": profile_path.name if profile_path else None,
        },
        "metrics": metrics,
        "quality": quality,
        "profile": profile_summary,
        "rankings": rankings,
        "fato_producao": analytics.get("fato_producao") or [],
        "oracle": oracle,
        "snapshot": {
            "analytics_sha256": _sha256(analytics_path),
            "profile_sha256": _sha256(profile_path),
        },
        "highlights": {
            "top_machine": rankings["machines_by_kg"][0]
            if rankings["machines_by_kg"]
            else None,
            "top_phase": rankings["phases_by_kg"][0]
            if rankings["phases_by_kg"]
            else None,
            "top_turno": rankings["turns_by_kg"][0]
            if rankings["turns_by_kg"]
            else None,
        },
    }
    return period_payload, updated_mtime


def build_beneficiamento_dashboard_payload(project_root: str) -> dict[str, Any]:
    """Consolida os snapshots locais sem consultar Oracle em request GET."""

    snapshot_root = _resolve_snapshot_root(project_root)
    periods: dict[str, Any] = {}
    comparison: list[dict[str, Any]] = []
    status_counts = {"ok": 0, "attention": 0, "blocked": 0, "missing": 0}
    latest_period = None
    latest_mtime: float | None = None
    findings: list[str] = []

    for period_key in PERIOD_ORDER:
        file_candidates = PERIOD_FILE_CANDIDATES[period_key]
        analytics_path = _first_existing(snapshot_root, file_candidates["analytics"])
        profile_path = _first_existing(snapshot_root, file_candidates["profile"])
        period_payload, period_mtime = _build_period_summary(
            period_key, analytics_path, profile_path
        )
        periods[period_key] = period_payload

        status = str(period_payload["status"] or "missing").lower()
        if status not in status_counts:
            status = "missing"
        status_counts[status] += 1
        if status != "ok":
            findings.append(f"{period_key}: {status}")
        if period_payload["oracle"].get("oracle_timeout_applied") is False:
            findings.append(f"{period_key}: call_timeout Oracle nao aplicado")

        comparison.append(
            {
                "period": period_key,
                "label": period_payload["label"],
                "status": period_payload["status"],
                "updated_at": period_payload["updated_at"],
                "stale": period_payload["stale"],
                "kg_total": period_payload["metrics"]["kg_total"],
                "mt_total": period_payload["metrics"]["mt_total"],
                "rendimento_medio_ponderado": period_payload["metrics"][
                    "rendimento_medio_ponderado"
                ],
                "efic_carga_media_ponderada": period_payload["metrics"][
                    "efic_carga_media_ponderada"
                ],
                "desvio_min_abs_total": period_payload["metrics"][
                    "desvio_min_abs_total"
                ],
                "ready_for_kpi": period_payload["quality"]["ready_for_kpi"],
                "ready_for_powerbi": period_payload["quality"]["ready_for_powerbi"],
                "ready_for_python": period_payload["quality"]["ready_for_python"],
            }
        )

        if period_mtime is not None and (
            latest_mtime is None or period_mtime >= latest_mtime
        ):
            latest_mtime = period_mtime
            latest_period = period_key

    available_periods = [item for item in comparison if periods[item["period"]]["available"]]
    first_available = next((item["period"] for item in available_periods), None)
    default_period = (
        "mensal"
        if periods.get("mensal", {}).get("available")
        else first_available
        or latest_period
        or "diario"
    )

    overall_status = "ok"
    if status_counts["blocked"] > 0 or status_counts["missing"] > 0:
        overall_status = "blocked"
    elif status_counts["attention"] > 0:
        overall_status = "attention"

    ready_for_kpi = all(item["ready_for_kpi"] for item in comparison if item["status"] != "missing")
    ready_for_powerbi = all(
        item["ready_for_powerbi"] for item in comparison if item["status"] != "missing"
    )
    ready_for_python = all(
        item["ready_for_python"] for item in comparison if item["status"] != "missing"
    )
    generated_at = (
        format_dt_br(datetime.fromtimestamp(latest_mtime))
        if latest_mtime is not None
        else format_dt_br(datetime.now())
    )
    health_periods = [
        {
            "period": key,
            "status": payload["status"],
            "available": payload["available"],
            "stale": payload["stale"],
            "updated_at": payload["updated_at"],
            "age_seconds": payload["age_seconds"],
            "oracle_elapsed_seconds": payload["oracle"].get("elapsed_seconds"),
            "oracle_timeout_ms": payload["oracle"].get("oracle_timeout_ms"),
            "oracle_timeout_applied": payload["oracle"].get("oracle_timeout_applied"),
            "source_files": payload["source_files"],
        }
        for key, payload in periods.items()
    ]

    return {
        "generated_at": generated_at,
        "default_period": default_period,
        "overall": {
            "status": overall_status,
            "ready_for_kpi": ready_for_kpi and overall_status == "ok",
            "ready_for_powerbi": ready_for_powerbi and overall_status == "ok",
            "ready_for_python": ready_for_python and overall_status == "ok",
            "latest_period": latest_period,
            "periods_total": len(PERIOD_ORDER),
            "periods_loaded": len(available_periods),
            "status_counts": status_counts,
        },
        "comparison": comparison,
        "periods": periods,
        "health": {
            "generated_at": generated_at,
            "snapshot_root": str(snapshot_root),
            "status": overall_status,
            "periods_total": len(PERIOD_ORDER),
            "periods_loaded": len(available_periods),
            "findings": findings,
            "periods": health_periods,
        },
    }


def build_beneficiamento_health_payload(project_root: str) -> dict[str, Any]:
    payload = build_beneficiamento_dashboard_payload(project_root)
    health = payload.get("health")
    return health if isinstance(health, dict) else {}


def build_beneficiamento_periods_payload(project_root: str) -> dict[str, Any]:
    payload = build_beneficiamento_dashboard_payload(project_root)
    return {
        "generated_at": payload["generated_at"],
        "default_period": payload["default_period"],
        "periods": list(payload["periods"].values()),
    }


def build_beneficiamento_period_payload(project_root: str, period: str) -> dict[str, Any]:
    normalized = period.strip().lower()
    if normalized not in PERIOD_ORDER:
        raise ValueError(f"Periodo invalido: {period}")
    payload = build_beneficiamento_dashboard_payload(project_root)
    periods = payload.get("periods")
    if not isinstance(periods, dict):
        raise ValueError(f"Periodo indisponivel: {period}")
    period_payload = periods.get(normalized)
    if not isinstance(period_payload, dict):
        raise ValueError(f"Periodo indisponivel: {period}")
    return period_payload
