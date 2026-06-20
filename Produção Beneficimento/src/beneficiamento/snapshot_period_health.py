# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-return-statements,too-many-locals,line-too-long
"""Análise de saúde por período do Beneficiamento.

Construtores de issues e contexto de health para um único período.
Consumido por ``snapshot_dashboard`` via ``_build_period_health_context``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
            critical_nulls = [
                str(item.get("column"))
                for item in check.get("columns") or []
                if item.get("column")
            ]
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
        issue_message = (
            f"Quality gate do snapshot bloqueou o período: {critical_issues[0]}"
        )
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
    available: bool,
    stale: bool,
    metrics: dict[str, Any],
    quality: dict[str, Any],
    oracle: dict[str, Any],
    refresh_status: str,
    historico_write_status: str,
) -> tuple[str, str, dict[str, Any]]:
    quality_status = str(quality.get("status") or "").lower()
    files_present = analytics_exists
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
    if (
        historico_write_status == "partial_failure"
        or refresh_status == "partial_failure"
    ):
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
    if stale and primary_reason != "snapshot_stale":
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
        historico_write_status == "partial_failure"
        or refresh_status == "partial_failure"
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
