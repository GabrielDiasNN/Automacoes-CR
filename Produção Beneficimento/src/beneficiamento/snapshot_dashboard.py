# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-return-statements,too-many-locals
"""Leitura agregada dos snapshots do Beneficiamento para o Dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import PERIOD_ORDER, get_period_config
from .snapshot_store import read_json, snapshot_path


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


def _file_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    age = max(0.0, datetime.now().timestamp() - path.stat().st_mtime)
    return int(age)


def _file_updated_at(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _build_issue(
    *,
    code: str,
    label: str,
    message: str,
    severity: str = "warn",
    period: str | None = None,
    action_hint: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "period": period,
        "label": label,
        "message": message,
        "action_hint": action_hint,
    }


def _quality_blocked_issue(
    *,
    period: str,
    label: str,
    quality: dict[str, Any],
) -> dict[str, Any]:
    checks = quality.get("checks") or []
    critical_issues = quality.get("critical_issues") or []

    missing_columns = []
    for check in checks:
        if check.get("name") == "schema_presence" and check.get("missing"):
            missing_columns = [str(item) for item in check.get("missing") or []]
            break
    if missing_columns:
        return _build_issue(
            code="quality_missing_required_columns",
            period=period,
            label=label,
            severity="error",
            message=(
                "Quality gate bloqueou o período por colunas obrigatórias ausentes: "
                + ", ".join(missing_columns)
            ),
            action_hint=(
                "Regerar o snapshot garantindo as colunas obrigatórias ausentes antes de "
                "promover o período."
            ),
        )

    critical_nulls = []
    for check in checks:
        if check.get("name") == "critical_nulls" and check.get("columns"):
            critical_nulls = [str(item.get("column")) for item in check.get("columns") or [] if item.get("column")]
            break
    if critical_nulls:
        return _build_issue(
            code="quality_critical_nulls",
            period=period,
            label=label,
            severity="error",
            message=(
                "Quality gate bloqueou o período por nulos críticos em: "
                + ", ".join(critical_nulls)
            ),
            action_hint=(
                "Corrigir os nulos críticos no snapshot antes de promover o período."
            ),
        )

    duplicate_rows = 0
    for check in checks:
        if check.get("name") == "group_key_uniqueness":
            duplicate_rows = int(check.get("duplicate_rows") or 0)
            break
    if duplicate_rows:
        return _build_issue(
            code="quality_duplicate_keys",
            period=period,
            label=label,
            severity="error",
            message=(
                "Quality gate bloqueou o período por chave analítica duplicada em "
                f"{duplicate_rows} linha(s)."
            ),
            action_hint=(
                "Eliminar as duplicidades analíticas antes de promover o snapshot."
            ),
        )

    issue_message = "Quality gate do snapshot bloqueou o período."
    if critical_issues:
        issue_message = f"Quality gate do snapshot bloqueou o período: {critical_issues[0]}"
    return _build_issue(
        code="quality_blocked",
        period=period,
        label=label,
        severity="error",
        message=issue_message,
        action_hint="Corrigir os achados do quality gate e promover novo snapshot do período.",
    )


def _primary_issue_for_period(
    *,
    period: str,
    label: str,
    analytics_exists: bool,
    profile_exists: bool,
    available: bool,
    stale: bool,
    metrics: dict[str, Any],
    quality: dict[str, Any],
    oracle: dict[str, Any],
    refresh_status: str,
    historico_write_status: str,
) -> tuple[str, str, dict[str, Any]]:
    quality_status = str(quality.get("status") or "").lower()
    files_present = analytics_exists or profile_exists
    invalid_snapshot = files_present and not available
    if not files_present:
        return (
            "missing",
            "snapshot_missing",
            _build_issue(
                code="snapshot_missing",
                period=period,
                label=label,
                severity="error",
                message="Snapshot local ausente ou ainda não promovido.",
                action_hint="Executar refresh controlado do período e promover os arquivos locais antes de depender do painel.",
            ),
        )
    if invalid_snapshot:
        return (
            "attention",
            "snapshot_invalid",
            _build_issue(
                code="snapshot_invalid",
                period=period,
                label=label,
                severity="error",
                message="Arquivos do snapshot existem, mas estão incompletos, inválidos ou inconsistentes.",
                action_hint="Regerar o snapshot do período e validar os arquivos analytics/profile antes de liberar a leitura operacional.",
            ),
        )
    if historico_write_status == "partial_failure" or refresh_status == "partial_failure":
        return (
            "attention",
            "historico_partial_failure",
            _build_issue(
                code="historico_partial_failure",
                period=period,
                label=label,
                severity="error",
                message="Refresh concluído com falha parcial na escrita do histórico SQLite.",
                action_hint="Reexecutar o refresh e confirmar a escrita no histórico SQLite antes de confiar no drill-down.",
            ),
        )
    if quality_status == "blocked":
        issue = _quality_blocked_issue(period=period, label=label, quality=quality)
        return (
            "attention",
            str(issue["code"]),
            issue,
        )
    if int(metrics.get("linhas") or 0) <= 0:
        return (
            "no_data",
            "snapshot_no_data",
            _build_issue(
                code="snapshot_no_data",
                period=period,
                label=label,
                severity="info",
                message="Snapshot promovido sem linhas úteis para o período.",
                action_hint="Confirmar se a janela operacional realmente não possui produção antes de concluir ausência de dados.",
            ),
        )
    if stale:
        return (
            "attention",
            "snapshot_stale",
            _build_issue(
                code="snapshot_stale",
                period=period,
                label=label,
                severity="warn",
                message="Snapshot acima da idade operacional esperada.",
                action_hint="Atualizar o período via runner controlado antes de usar o dado como base de decisão.",
            ),
        )
    if quality_status == "attention":
        return (
            "attention",
            "quality_attention",
            _build_issue(
                code="quality_attention",
                period=period,
                label=label,
                severity="warn",
                message="Snapshot promovido com avisos de qualidade.",
                action_hint="Revisar os avisos de qualidade do período antes de ampliar o uso analítico.",
            ),
        )
    if oracle.get("oracle_timeout_applied") is False:
        return (
            "attention",
            "oracle_timeout_unapplied",
            _build_issue(
                code="oracle_timeout_unapplied",
                period=period,
                label=label,
                severity="warn",
                message="Oracle Client não aplicou call_timeout neste snapshot.",
                action_hint="Validar o Oracle Client local; se o tempo ficar abaixo de 19 segundos, registrar o risco operacional e planejar ajuste do client.",
            ),
        )
    return (
        "healthy",
        "healthy",
        _build_issue(
            code="healthy",
            period=period,
            label=label,
            severity="info",
            message="Snapshot válido e promovido.",
        ),
    )


def _snapshot_state_for_reason(reason_code: str) -> str:
    if reason_code == "snapshot_missing":
        return "missing"
    if reason_code in {
        "snapshot_invalid",
        "historico_partial_failure",
        "quality_blocked",
    }:
        return "invalid"
    if reason_code == "snapshot_stale":
        return "stale"
    return "promoted"


def _build_secondary_issues(
    *,
    primary_reason: str,
    period: str,
    label: str,
    stale: bool,
    quality: dict[str, Any],
    oracle: dict[str, Any],
    refresh_status: str,
    historico_write_status: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    quality_status = str(quality.get("status") or "").lower()
    if (
        stale
        and primary_reason != "snapshot_stale"
    ):
        issues.append(
            _build_issue(
                code="snapshot_stale",
                period=period,
                label=label,
                severity="warn",
                message="Snapshot acima da idade operacional esperada.",
                action_hint="Atualizar o período via runner controlado antes de usar o dado como base de decisão.",
            )
        )
    if (
        historico_write_status == "partial_failure" or refresh_status == "partial_failure"
    ) and primary_reason != "historico_partial_failure":
        issues.append(
            _build_issue(
                code="historico_partial_failure",
                period=period,
                label=label,
                severity="error",
                message="Refresh concluído com falha parcial na escrita do histórico SQLite.",
                action_hint="Reexecutar o refresh e confirmar a escrita no histórico SQLite antes de confiar no drill-down.",
            )
        )
    if quality_status == "blocked" and primary_reason != "quality_blocked":
        issues.append(
            _quality_blocked_issue(
                period=period,
                label=label,
                quality=quality,
            )
        )
    if quality_status == "attention" and primary_reason != "quality_attention":
        issues.append(
            _build_issue(
                code="quality_attention",
                period=period,
                label=label,
                severity="warn",
                message="Snapshot promovido com avisos de qualidade.",
                action_hint="Revisar os avisos de qualidade do período antes de ampliar o uso analítico.",
            )
        )
    if (
        oracle.get("oracle_timeout_applied") is False
        and primary_reason != "oracle_timeout_unapplied"
    ):
        issues.append(
            _build_issue(
                code="oracle_timeout_unapplied",
                period=period,
                label=label,
                severity="warn",
                message="Oracle Client não aplicou call_timeout neste snapshot.",
                action_hint="Validar o Oracle Client local; se o tempo ficar abaixo de 19 segundos, registrar o risco operacional e planejar ajuste do client.",
            )
        )
    return issues


def _build_period_health_context(
    *,
    period: str,
    label: str,
    analytics_path: Path,
    profile_path: Path,
    available: bool,
    stale: bool,
    metrics: dict[str, Any],
    quality: dict[str, Any],
    oracle: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    quality_status = str(quality.get("status") or "").lower()
    refresh_status = str(snapshot.get("refresh_status") or "").lower()
    historico_write_status = str(snapshot.get("historico_write_status") or "").lower()
    status, reason_code, primary_issue = _primary_issue_for_period(
        period=period,
        label=label,
        analytics_exists=analytics_path.exists(),
        profile_exists=profile_path.exists(),
        available=available,
        stale=stale,
        metrics=metrics,
        quality=quality,
        oracle=oracle,
        refresh_status=refresh_status,
        historico_write_status=historico_write_status,
    )
    issues = [primary_issue]
    issues.extend(
        _build_secondary_issues(
            primary_reason=reason_code,
            period=period,
            label=label,
            stale=stale,
            quality=quality,
            oracle=oracle,
            refresh_status=refresh_status,
            historico_write_status=historico_write_status,
        )
    )
    return {
        "status": status,
        "snapshot_state": _snapshot_state_for_reason(reason_code),
        "reason_code": reason_code,
        "reason_message": primary_issue["message"],
        "recommended_action": primary_issue.get("action_hint"),
        "quality_status": quality_status or None,
        "refresh_status": refresh_status or None,
        "historico_write_status": historico_write_status or None,
        "issues": issues,
    }


def _build_period_highlights(
    period: str,
    metrics: dict[str, Any],
    analytics: dict[str, Any],
) -> dict[str, Any]:
    top_machine = ((analytics.get("destaques") or {}).get("maquinas_por_kg") or [None])[0] or {}
    top_phase = ((analytics.get("destaques") or {}).get("fases_por_kg") or [None])[0] or {}
    top_turno = ((analytics.get("destaques") or {}).get("turnos_por_kg") or [None])[0] or {}
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


def _load_periods_payload() -> dict[str, dict[str, Any]]:
    return {period: load_period_payload(period) for period in PERIOD_ORDER}


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
    _, period, payload = min(candidates, key=lambda item: (item[0], PERIOD_ORDER.index(item[1])))
    return {
        "period": period,
        "label": payload.get("label") or period,
        "status": payload.get("status") or "missing",
        "updated_at": payload.get("updated_at"),
        "age_seconds": payload.get("age_seconds"),
    }


def _health_reason_code(periods: dict[str, dict[str, Any]], status: str) -> str:
    if status == "healthy":
        return "healthy"
    if status == "missing":
        return "snapshot_missing"
    if status == "no_data":
        return "snapshot_no_data"
    primary_issue = _primary_health_issue(periods)
    if primary_issue:
        return str(primary_issue.get("code") or "snapshot_attention")
    return "snapshot_attention"


def _health_recommended_action(periods: dict[str, dict[str, Any]]) -> str | None:
    primary_issue = _primary_health_issue(periods)
    if primary_issue and primary_issue.get("action_hint"):
        return str(primary_issue["action_hint"])
    return None


def _overall_status(periods: dict[str, dict[str, Any]]) -> str:
    statuses = {item.get("status") for item in periods.values()}
    if statuses == {"missing"}:
        return "missing"
    if "attention" in statuses or "missing" in statuses:
        return "attention"
    if "no_data" in statuses and len(statuses) == 1:
        return "no_data"
    return "healthy"


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
        payload_issues = periods[period].get("issues") or []
        for issue in payload_issues:
            issues.append(issue)
    severity_rank = {"error": 0, "warn": 1, "info": 2}
    return sorted(
        issues,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or "info").lower(), 3),
            PERIOD_ORDER.index(str(item.get("period") or "mensal"))
            if str(item.get("period") or "") in PERIOD_ORDER
            else len(PERIOD_ORDER),
            str(item.get("code") or ""),
        ),
    )


def _primary_health_issue(periods: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    issues = _build_issues(periods)
    return issues[0] if issues else None


def _build_snapshot_files(periods: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        period: periods[period].get("source_files") or {}
        for period in PERIOD_ORDER
    }


def _build_health_from_periods(periods: dict[str, dict[str, Any]]) -> dict[str, Any]:
    status = _overall_status(periods)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_root": str(snapshot_path("diario", "analytics").parent),
        "source": "snapshot_local",
        "status": status,
        "reason_code": _health_reason_code(periods, status),
        "recommended_action": _health_recommended_action(periods),
        "periods_total": len(PERIOD_ORDER),
        "periods_loaded": sum(1 for item in periods.values() if item.get("available")),
        "findings": _build_findings(periods),
        "issues": _build_issues(periods),
        "summary": _summary_from_periods(periods),
        "latest_period": _latest_period(periods),
        "snapshot_files": _build_snapshot_files(periods),
        "periods": _build_period_items(periods),
    }


def load_period_payload(period: str) -> dict[str, Any]:
    config = get_period_config(period)
    analytics_path = snapshot_path(period, "analytics")
    profile_path = snapshot_path(period, "profile")
    analytics = read_json(analytics_path)
    profile = read_json(profile_path)
    available = bool(analytics) and bool(profile)
    updated_at = (
        ((analytics.get("snapshot") or {}).get("generated_at"))
        or _file_updated_at(analytics_path)
        or _file_updated_at(profile_path)
    )
    age_candidates = [
        value
        for value in (
            _file_age_seconds(analytics_path),
            _file_age_seconds(profile_path),
        )
        if value is not None
    ]
    age_seconds = max(age_candidates) if age_candidates else None
    stale = bool(age_seconds is not None and age_seconds > (config.max_age_minutes * 60))
    metrics = analytics.get("geral") or {}
    quality = analytics.get("qualidade") or {}
    rankings = {
        "por_maquina": analytics.get("por_maquina") or [],
        "por_fase": analytics.get("por_fase") or [],
        "por_turno": analytics.get("por_turno") or [],
    }
    oracle = ((analytics.get("execucao_oracle") or {}).get("consulta_principal")) or {}
    snapshot = analytics.get("snapshot") or {}
    profile_summary = {
        "total_columns": profile.get("total_columns"),
        "total_rows": profile.get("total_rows"),
        "window": profile.get("window") or {},
        "mostly_null_columns": profile.get("mostly_null_columns") or [],
        "constant_columns": profile.get("constant_columns") or [],
        "duplicate_source_names": profile.get("duplicate_source_names") or {},
    }
    health_context = _build_period_health_context(
        period=period,
        label=config.label,
        analytics_path=analytics_path,
        profile_path=profile_path,
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
            "profile": str(profile_path),
        },
        "metrics": metrics,
        "quality": quality,
        "profile": profile_summary,
        "rankings": rankings,
        "highlights": _build_period_highlights(period, metrics, analytics),
        "oracle": oracle,
        "snapshot": snapshot,
    }


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
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
