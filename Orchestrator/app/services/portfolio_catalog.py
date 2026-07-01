"""Catálogo canônico do portfólio de automações e leitura operacional cruzada."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..constants import EXECUTION_ACTIVE_STATUSES, EXECUTION_DELIVERED_STATUSES
from ..timezone import get_now_local
from .automation_snapshot import build_automation_response, build_next_run_lookup
from .metrics import (
    get_automation_metrics_24h,
    get_latest_execution_snapshot_by_automation,
)
from .portfolio_manifest import (  # pylint: disable=useless-import-alias
    CatalogManifest as CatalogManifest,  # noqa: F401
)
from .portfolio_manifest import (
    _channels_to_csv,
    _format_value,
    _normalize_repo_relative,
    _path_exists,
    _resolve_repo_path,
    _slugify,
    load_catalog_manifests,
)
from .scheduler_runtime import list_scheduled_jobs

FAILURE_STATUSES = ["ERROR", "TIMEOUT", "TERMINATED", "FAILED_BY_REBOOT"]
SUCCESS_STATUSES = ["SUCCESS"]
CRITICALITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "unclassified": 4,
}


def _get_last_execution_by_statuses(
    db: Session,
    automation_ids: list[int],
    statuses: list[str],
) -> dict[int, dict[str, Any]]:
    if not automation_ids:
        return {}
    ranked = (
        db.query(
            models.Execution.automation_id.label("automation_id"),
            models.Execution.id.label("execution_id"),
            models.Execution.status.label("status"),
            models.Execution.started_at.label("started_at"),
            models.Execution.finished_at.label("finished_at"),
            models.Execution.failure_reason.label("failure_reason"),
            models.Execution.recovery_action.label("recovery_action"),
            func.row_number()
            .over(
                partition_by=models.Execution.automation_id,
                order_by=(
                    models.Execution.started_at.desc(),
                    models.Execution.id.desc(),
                ),
            )
            .label("rn"),
        )
        .filter(
            models.Execution.automation_id.in_(automation_ids),
            models.Execution.status.in_(statuses),
        )
        .subquery()
    )
    rows = db.query(ranked).filter(ranked.c.rn == 1).all()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        auto_id = row.automation_id
        if auto_id is None:
            continue
        result[int(auto_id)] = {
            "id": row.execution_id,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "failure_reason": row.failure_reason,
            "recovery_action": row.recovery_action,
        }
    return result


def _dependency_status(
    manifest: CatalogManifest,
    latest_snapshot: dict[str, Any] | None,
) -> dict[str, str]:
    failure_reason = str((latest_snapshot or {}).get("failure_reason") or "").upper()
    recovery_action = str((latest_snapshot or {}).get("recovery_action") or "").upper()
    status = str((latest_snapshot or {}).get("status") or "").upper()

    def resolve(flag: bool, keywords: tuple[str, ...]) -> str:
        if not flag:
            return "not_used"
        if any(
            keyword in failure_reason or keyword in recovery_action
            for keyword in keywords
        ):
            return "degraded"
        if status in EXECUTION_DELIVERED_STATUSES:
            return "healthy"
        if status in FAILURE_STATUSES:
            return "unknown"
        return "healthy" if status in EXECUTION_ACTIVE_STATUSES else "unknown"

    return {
        "oracle": resolve(
            manifest.dependencies.oracle,
            ("ORA-", "ORACLE", "DB", "DATABASE"),
        ),
        "outlook": resolve(
            manifest.dependencies.outlook,
            ("OUTLOOK", "EMAIL"),
        ),
        "whatsapp": resolve(
            manifest.dependencies.whatsapp,
            ("WHATSAPP", "CHANNEL_DELIVERY_FAILED"),
        ),
    }


def _issue(
    code: str,
    message: str,
    *,
    manifest_value: Any = None,
    runtime_value: Any = None,
    severity: str = "WARN",
) -> schemas.PortfolioDriftIssue:
    return schemas.PortfolioDriftIssue(
        code=code,
        message=message,
        severity=severity,
        manifest_value=_format_value(manifest_value),
        runtime_value=_format_value(runtime_value),
    )


def _manifest_runtime_mismatches(
    project_root: Path,
    manifest: CatalogManifest,
    auto: models.Automation,
) -> list[schemas.PortfolioDriftIssue]:
    issues: list[schemas.PortfolioDriftIssue] = []

    manifest_script = _normalize_repo_relative(
        project_root, manifest.orchestrator.script_path
    )
    runtime_script = _normalize_repo_relative(
        project_root, cast(str | None, auto.script_path)
    )
    if manifest_script != runtime_script:
        issues.append(
            _issue(
                "script_path_mismatch",
                "script_path divergente entre manifesto e cadastro.",
                manifest_value=manifest_script,
                runtime_value=runtime_script,
            )
        )
    runtime_queue_group = cast(str | None, auto.queue_group)
    if (manifest.queue_group or None) != (runtime_queue_group or None):
        issues.append(
            _issue(
                "queue_group_mismatch",
                "queue_group divergente entre manifesto e cadastro.",
                manifest_value=manifest.queue_group,
                runtime_value=runtime_queue_group,
            )
        )
    runtime_max_runtime = cast(int | None, auto.max_runtime_minutes)
    if int(manifest.max_runtime_minutes) != int(runtime_max_runtime or 0):
        issues.append(
            _issue(
                "max_runtime_mismatch",
                "max_runtime_minutes divergente entre manifesto e cadastro.",
                manifest_value=manifest.max_runtime_minutes,
                runtime_value=runtime_max_runtime,
            )
        )
    runtime_max_retries = cast(int | None, auto.max_retries)
    if int(manifest.max_retries) != int(runtime_max_retries or 0):
        issues.append(
            _issue(
                "max_retries_mismatch",
                "max_retries divergente entre manifesto e cadastro.",
                manifest_value=manifest.max_retries,
                runtime_value=runtime_max_retries,
            )
        )
    runtime_sla_minutes = cast(int | None, auto.sla_minutes)
    if (manifest.sla_minutes or None) != (runtime_sla_minutes or None):
        issues.append(
            _issue(
                "sla_mismatch",
                "sla_minutes divergente entre manifesto e cadastro.",
                manifest_value=manifest.sla_minutes,
                runtime_value=runtime_sla_minutes,
            )
        )
    manifest_channels = _channels_to_csv(manifest.channels)
    runtime_channels = cast(str | None, auto.notification_channels) or None
    if manifest_channels != runtime_channels:
        issues.append(
            _issue(
                "notification_channels_mismatch",
                "Canais de notificação divergentes entre manifesto e cadastro.",
                manifest_value=manifest_channels,
                runtime_value=runtime_channels,
            )
        )

    return issues


def _manifest_docs_and_entrypoint_issues(
    project_root: Path,
    manifest: CatalogManifest,
) -> list[schemas.PortfolioDriftIssue]:
    issues: list[schemas.PortfolioDriftIssue] = []

    if not _path_exists(project_root, manifest.readme_path):
        issues.append(
            _issue(
                "readme_missing",
                "README obrigatório ausente no caminho informado pelo manifesto.",
                manifest_value=manifest.readme_path,
                severity="ERROR",
            )
        )
    if not _path_exists(project_root, manifest.context_path):
        issues.append(
            _issue(
                "context_missing",
                "CONTEXT obrigatório ausente no caminho informado pelo manifesto.",
                manifest_value=manifest.context_path,
                severity="ERROR",
            )
        )
    if not _path_exists(project_root, manifest.runbook_path):
        issues.append(
            _issue(
                "runbook_missing",
                "Runbook obrigatório ausente no caminho informado pelo manifesto.",
                manifest_value=manifest.runbook_path,
                severity="ERROR",
            )
        )
    entrypoint_path = f"{manifest.directory_name}/{manifest.entrypoint}"
    try:
        resolved_entrypoint = _resolve_repo_path(
            project_root,
            f"./{manifest.directory_name}/{manifest.entrypoint}",
        )
    except (ValueError, OSError):
        resolved_entrypoint = None
    if resolved_entrypoint is None or not resolved_entrypoint.exists():
        issues.append(
            _issue(
                "entrypoint_missing",
                "Entrypoint declarado no manifesto não existe na pasta da automação.",
                manifest_value=entrypoint_path,
                severity="ERROR",
            )
        )

    for smoke_test in manifest.smoke_tests:
        if not _path_exists(project_root, smoke_test):
            issues.append(
                _issue(
                    "smoke_test_missing",
                    "Smoke test declarado no manifesto não foi encontrado.",
                    manifest_value=smoke_test,
                    severity="ERROR",
                )
            )

    return issues


def _build_manifest_issues(
    project_root: Path,
    manifest: CatalogManifest,
    auto: models.Automation | None,
) -> list[schemas.PortfolioDriftIssue]:
    issues: list[schemas.PortfolioDriftIssue] = []

    if auto is None:
        issues.append(
            _issue(
                "automation_not_registered",
                "Manifesto presente, mas a automação não está cadastrada no Orchestrator.",
                manifest_value=manifest.orchestrator.script_path,
                severity="ERROR",
            )
        )
    else:
        issues.extend(_manifest_runtime_mismatches(project_root, manifest, auto))

    issues.extend(_manifest_docs_and_entrypoint_issues(project_root, manifest))
    return issues


def _find_matching_automation(
    manifest: CatalogManifest,
    project_root: Path,
    db_by_script: dict[str, models.Automation],
    db_by_name: dict[str, models.Automation],
) -> models.Automation | None:
    manifest_script = _normalize_repo_relative(
        project_root, manifest.orchestrator.script_path
    )
    if manifest_script and manifest_script in db_by_script:
        return db_by_script[manifest_script]
    return db_by_name.get(manifest.name.strip().lower())


def _minutes_since(timestamp: Any) -> int | None:
    if timestamp is None:
        return None
    delta = get_now_local() - timestamp
    return max(0, int(delta.total_seconds() // 60))


def _seconds_since(timestamp: Any) -> float | None:
    if timestamp is None:
        return None
    delta = get_now_local() - cast(datetime, timestamp)
    return max(0.0, round(delta.total_seconds(), 2))


def _schedule_lag_minutes(next_run: Any, active_execution_count: int) -> int | None:
    if next_run is None or active_execution_count > 0:
        return None
    delay = get_now_local() - next_run
    minutes = int(delay.total_seconds() // 60)
    return minutes if minutes > 0 else 0


def _schedule_lag_seconds(next_run: Any, active_execution_count: int) -> float | None:
    if next_run is None or active_execution_count > 0:
        return None
    delay = get_now_local() - next_run
    seconds = round(delay.total_seconds(), 2)
    return seconds if seconds > 0 else 0.0


def _sla_state(
    sla_minutes: int | None,
    *,
    schedule_lag_minutes: int | None,
    last_status: str | None,
    last_failure_age_minutes: int | None,
) -> str:
    if not sla_minutes:
        return "unknown"
    if schedule_lag_minutes is not None and schedule_lag_minutes > sla_minutes:
        return "breached"
    if (
        last_status in FAILURE_STATUSES
        and last_failure_age_minutes is not None
        and last_failure_age_minutes > sla_minutes
    ):
        return "breached"
    if last_status in FAILURE_STATUSES:
        return "recovering"
    return "ok"


def _health_status(
    *,
    automation_registered: bool,
    docs_status: str,
    drift_count: int,
    sla_state: str,
    operational_state: str,
) -> str:
    if not automation_registered:
        return "not_registered"
    if sla_state == "breached":
        return "breached"
    if docs_status != "complete" or drift_count > 0:
        return "attention"
    return operational_state or "idle"


def _portfolio_operational_status(item: schemas.PortfolioHealthItem) -> str:
    critical_governance_drift = item.criticality in {"critical", "high"} and (
        item.docs_status != "complete" or item.drift_count > 0
    )
    if item.review_status == "delete_candidate":
        return "attention"
    if item.health_status in {"not_registered", "not_governed", "breached"}:
        return "incident"
    if critical_governance_drift:
        return "incident"
    if item.docs_status != "complete" or item.drift_count > 0:
        return "attention"
    if item.sla_state == "recovering" or item.health_status == "attention":
        return "attention"
    return "healthy"


def _count_portfolio_signals(
    health_items: list[schemas.PortfolioHealthItem],
) -> dict[str, int]:
    incident_items = 0
    attention_items = 0
    healthy_items = 0
    for item in health_items:
        signal = _portfolio_operational_status(item)
        if signal == "incident":
            incident_items += 1
        elif signal == "attention":
            attention_items += 1
        else:
            healthy_items += 1

    return {
        "incident_items": incident_items,
        "attention_items": attention_items,
        "healthy_items": healthy_items,
        "governed_items": sum(
            1 for item in health_items if not item.catalog_id.startswith("runtime-")
        ),
        "enabled_items": sum(1 for item in health_items if item.enabled),
        "drift_items": sum(1 for item in health_items if item.drift_count > 0),
        "docs_missing_items": sum(
            1 for item in health_items if item.docs_status != "complete"
        ),
        "sla_breached_items": sum(
            1 for item in health_items if item.sla_state == "breached"
        ),
        "not_registered_items": sum(
            1
            for item in health_items
            if item.health_status in {"not_registered", "not_governed"}
        ),
        "delete_candidate_items": sum(
            1 for item in health_items if item.review_status == "delete_candidate"
        ),
    }


def _portfolio_top_issue(counts: dict[str, int]) -> tuple[str, str | None]:
    if counts["delete_candidate_items"] > 0:
        return (
            "Há automações candidatas à exclusão do cadastro por inatividade, ausência de manifesto ou cadastro órfão.",
            "Revise as candidatas na aba Automações e exclua apenas os registros confirmadamente sem utilidade.",
        )
    if counts["not_registered_items"] > 0:
        return (
            "Há automações ativas fora do catálogo governado ou sem cadastro reconciliado.",
            "Reconcilie manifesto e cadastro runtime antes de expandir o portfólio.",
        )
    if counts["docs_missing_items"] > 0:
        return (
            "Há automações com runbook, README ou CONTEXT pendentes no catálogo.",
            "Complete a documentação obrigatória das automações governadas.",
        )
    if counts["drift_items"] > 0:
        return (
            "Há drift entre manifesto e parâmetros efetivos do runtime.",
            "Alinhe script_path, fila, SLA, retries e canais com o manifesto canônico.",
        )
    if counts["sla_breached_items"] > 0:
        return (
            "Há automações governadas com SLA violado.",
            "Priorize a recuperação das automações com atraso acima do SLA.",
        )
    return "Catálogo governado consistente com o runtime.", None


def _build_portfolio_summary(
    health_items: list[schemas.PortfolioHealthItem],
) -> schemas.PortfolioHealthSummary:
    counts = _count_portfolio_signals(health_items)

    status = "healthy"
    if counts["incident_items"] > 0:
        status = "incident"
    elif counts["attention_items"] > 0:
        status = "attention"

    top_issue, recommended_action = _portfolio_top_issue(counts)

    return schemas.PortfolioHealthSummary(
        total_items=len(health_items),
        governed_items=counts["governed_items"],
        enabled_items=counts["enabled_items"],
        drift_items=counts["drift_items"],
        docs_missing_items=counts["docs_missing_items"],
        sla_breached_items=counts["sla_breached_items"],
        not_registered_items=counts["not_registered_items"],
        delete_candidate_items=counts["delete_candidate_items"],
        healthy_items=counts["healthy_items"],
        attention_items=counts["attention_items"],
        incident_items=counts["incident_items"],
        status=status,
        top_issue=top_issue,
        recommended_action=recommended_action,
    )


def _sort_health_item(item: schemas.PortfolioHealthItem) -> tuple[int, str]:
    return (CRITICALITY_RANK.get(item.criticality, 99), item.name.lower())


def _build_review_status(  # pylint: disable=too-many-arguments
    *,
    catalog_id: str,
    enabled: bool,
    next_run: Any,
    last_success_age_seconds: float | None,
    last_failure_age_seconds: float | None,
    drift_count: int,
    docs_status: str,
    health_status: str,
) -> tuple[str, list[str]]:
    review_reasons: list[str] = []
    inactivity_cutoff_seconds = 30 * 24 * 60 * 60

    if catalog_id.startswith("runtime-"):
        review_reasons.append(
            "Cadastro runtime sem manifesto governado correspondente."
        )

    if not enabled and next_run is None:
        review_reasons.append("Automação desabilitada e sem próxima execução agendada.")

    last_activity_age_seconds = min(
        (
            value
            for value in (last_success_age_seconds, last_failure_age_seconds)
            if value is not None
        ),
        default=None,
    )
    if last_activity_age_seconds is None:
        review_reasons.append("Sem execução registrada no histórico disponível.")
    elif last_activity_age_seconds >= inactivity_cutoff_seconds:
        review_reasons.append("Sem atividade operacional nos últimos 30 dias.")

    if health_status in {"not_registered", "not_governed"}:
        review_reasons.append("Cadastro sem reconciliação com o catálogo governado.")
    elif drift_count > 0:
        review_reasons.append("Cadastro com drift em relação ao manifesto canônico.")
    elif docs_status != "complete":
        review_reasons.append(
            "Documentação obrigatória incompleta para revisão segura."
        )

    if review_reasons and (
        catalog_id.startswith("runtime-") or (not enabled and next_run is None)
    ):
        return "delete_candidate", review_reasons
    if review_reasons:
        return "attention", review_reasons
    return "active", []


def _build_portfolio_lookups(
    db: Session, automation_ids: list[int]
) -> dict[str, Any]:
    jobs = list_scheduled_jobs(db)
    next_run_lookup = build_next_run_lookup(jobs)
    return {
        "next_run_lookup": next_run_lookup,
        "latest_lookup": get_latest_execution_snapshot_by_automation(
            db, automation_ids
        ),
        "metrics_lookup": get_automation_metrics_24h(db, automation_ids),
        "last_success_lookup": _get_last_execution_by_statuses(
            db, automation_ids, SUCCESS_STATUSES
        ),
        "last_failure_lookup": _get_last_execution_by_statuses(
            db, automation_ids, FAILURE_STATUSES
        ),
    }


def _index_automations(
    root: Path,
    automations: list[models.Automation],
    lookups: dict[str, Any],
) -> tuple[
    dict[str, models.Automation],
    dict[str, models.Automation],
    dict[int, schemas.AutomationResponse],
]:
    db_by_script: dict[str, models.Automation] = {}
    db_by_name: dict[str, models.Automation] = {}
    automation_response_by_id: dict[int, schemas.AutomationResponse] = {}
    for auto in automations:
        auto_id = int(auto.id)
        normalized_script = _normalize_repo_relative(
            root, cast(str | None, auto.script_path)
        )
        if normalized_script:
            db_by_script[normalized_script] = auto
        db_by_name[cast(str, auto.name).strip().lower()] = auto
        automation_response_by_id[auto_id] = build_automation_response(
            auto=auto,
            next_run_lookup=lookups["next_run_lookup"],
            latest_execution_lookup=lookups["latest_lookup"],
            metrics_24h_lookup=lookups["metrics_lookup"],
        )
    return db_by_script, db_by_name, automation_response_by_id


def _governed_row_lookups(
    matched_auto: models.Automation | None,
    lookups: dict[str, Any],
    automation_response_by_id: dict[int, schemas.AutomationResponse],
) -> dict[str, Any]:
    matched_id = int(matched_auto.id) if matched_auto else None
    response = automation_response_by_id.get(matched_id) if matched_id else None
    latest_snapshot = lookups["latest_lookup"].get(matched_id) if matched_id else None
    last_success = (
        lookups["last_success_lookup"].get(matched_id) if matched_id else None
    )
    last_failure = (
        lookups["last_failure_lookup"].get(matched_id) if matched_id else None
    )
    return {
        "matched_id": matched_id,
        "response": response,
        "latest_snapshot": latest_snapshot,
        "last_success": last_success,
        "last_failure": last_failure,
    }


def _governed_row_activity(base: dict[str, Any]) -> dict[str, Any]:
    response = base["response"]
    last_success = base["last_success"]
    last_failure = base["last_failure"]

    next_run_dt = (
        schemas.parse_dt_br(response.next_run)
        if response and response.next_run
        else None
    )
    last_success_at = (
        last_success.get("finished_at") or last_success.get("started_at")
        if last_success
        else None
    )
    last_failure_at = (
        last_failure.get("finished_at") or last_failure.get("started_at")
        if last_failure
        else None
    )
    active_count = response.active_execution_count if response else 0

    return {
        "next_run_dt": next_run_dt,
        "last_status": response.last_status if response else None,
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "last_success_age_seconds": _seconds_since(last_success_at),
        "last_failure_age_seconds": _seconds_since(last_failure_at),
        "last_failure_age_minutes": _minutes_since(last_failure_at),
        "lag_minutes": _schedule_lag_minutes(next_run_dt, active_count),
        "lag_seconds": _schedule_lag_seconds(next_run_dt, active_count),
        "operational_state": (
            response.operational_state if response else "not_registered"
        ),
    }


def _governed_row_metrics(
    manifest: CatalogManifest,
    matched_auto: models.Automation | None,
    issues: list[schemas.PortfolioDriftIssue],
    lookups: dict[str, Any],
    automation_response_by_id: dict[int, schemas.AutomationResponse],
) -> dict[str, Any]:
    base = _governed_row_lookups(matched_auto, lookups, automation_response_by_id)
    activity = _governed_row_activity(base)

    sla_state = _sla_state(
        manifest.sla_minutes,
        schedule_lag_minutes=activity["lag_minutes"],
        last_status=activity["last_status"],
        last_failure_age_minutes=activity["last_failure_age_minutes"],
    )
    docs_status = (
        "complete"
        if not any(
            issue.code
            in {
                "readme_missing",
                "context_missing",
                "runbook_missing",
                "entrypoint_missing",
            }
            for issue in issues
        )
        else "missing"
    )

    return {
        "matched_id": base["matched_id"],
        "response": base["response"],
        "dependency_status": _dependency_status(manifest, base["latest_snapshot"]),
        "next_run_dt": activity["next_run_dt"],
        "last_status": activity["last_status"],
        "last_success_at": activity["last_success_at"],
        "last_failure_at": activity["last_failure_at"],
        "last_success_age_seconds": activity["last_success_age_seconds"],
        "last_failure_age_seconds": activity["last_failure_age_seconds"],
        "last_failure_age_minutes": activity["last_failure_age_minutes"],
        "lag_minutes": activity["lag_minutes"],
        "lag_seconds": activity["lag_seconds"],
        "sla_state": sla_state,
        "docs_status": docs_status,
        "operational_state": activity["operational_state"],
        "health_status": _health_status(
            automation_registered=matched_auto is not None,
            docs_status=docs_status,
            drift_count=len(issues),
            sla_state=sla_state,
            operational_state=activity["operational_state"],
        ),
    }


def _build_governed_row(
    root: Path,
    manifest: CatalogManifest,
    matched_auto: models.Automation | None,
    lookups: dict[str, Any],
    automation_response_by_id: dict[int, schemas.AutomationResponse],
) -> tuple[schemas.PortfolioHealthItem, schemas.PortfolioDriftItem]:
    issues = _build_manifest_issues(root, manifest, matched_auto)
    m = _governed_row_metrics(
        manifest, matched_auto, issues, lookups, automation_response_by_id
    )
    response = m["response"]

    drift_item = schemas.PortfolioDriftItem(
        catalog_id=manifest.id,
        automation_id=m["matched_id"],
        name=manifest.name,
        slug=manifest.slug,
        issues=issues,
    )

    review_status, review_reasons = _build_review_status(
        catalog_id=manifest.id,
        enabled=bool(matched_auto.enabled) if matched_auto else False,
        next_run=m["next_run_dt"],
        last_success_age_seconds=m["last_success_age_seconds"],
        last_failure_age_seconds=m["last_failure_age_seconds"],
        drift_count=len(issues),
        docs_status=m["docs_status"],
        health_status=m["health_status"],
    )

    health_item = schemas.PortfolioHealthItem(
        catalog_id=manifest.id,
        automation_id=m["matched_id"],
        name=manifest.name,
        slug=manifest.slug,
        criticality=manifest.criticality,
        owner_area=manifest.owner_area,
        runtime=manifest.runtime,
        enabled=bool(matched_auto.enabled) if matched_auto else False,
        queue_group=(
            manifest.queue_group
            if manifest.queue_group
            else (
                cast(str | None, matched_auto.queue_group) if matched_auto else None
            )
        ),
        sla_minutes=manifest.sla_minutes,
        health_status=m["health_status"],
        sla_state=m["sla_state"],
        docs_status=m["docs_status"],
        drift_status="drift" if issues else "ok",
        drift_count=len(issues),
        runbook_path=manifest.runbook_path,
        readme_path=manifest.readme_path,
        context_path=manifest.context_path,
        next_run=m["next_run_dt"],
        schedule_summary=(
            response.schedule_summary if response else manifest.schedule_summary
        ),
        schedule_lag_minutes=m["lag_minutes"],
        schedule_lag_seconds=m["lag_seconds"],
        last_status=m["last_status"],
        last_success_at=m["last_success_at"],
        last_failure_at=m["last_failure_at"],
        last_success_age_minutes=_minutes_since(m["last_success_at"]),
        last_failure_age_minutes=m["last_failure_age_minutes"],
        last_success_age_seconds=m["last_success_age_seconds"],
        last_failure_age_seconds=m["last_failure_age_seconds"],
        review_status=review_status,
        review_reasons=review_reasons,
        dependency_status=schemas.PortfolioDependencyStatus(**m["dependency_status"]),
    )
    return health_item, drift_item


def _ungoverned_row_metrics(
    auto: models.Automation,
    response: schemas.AutomationResponse,
    lookups: dict[str, Any],
) -> dict[str, Any]:
    auto_id = int(auto.id)
    latest_snapshot = lookups["latest_lookup"].get(auto_id, {})
    last_success = lookups["last_success_lookup"].get(auto_id)
    last_failure = lookups["last_failure_lookup"].get(auto_id)

    next_run_dt = schemas.parse_dt_br(response.next_run) if response.next_run else None
    last_success_at = (
        last_success.get("finished_at") or last_success.get("started_at")
        if last_success
        else None
    )
    last_failure_at = (
        last_failure.get("finished_at") or last_failure.get("started_at")
        if last_failure
        else None
    )

    return {
        "latest_snapshot": latest_snapshot,
        "next_run_dt": next_run_dt,
        "lag_minutes": _schedule_lag_minutes(
            next_run_dt, response.active_execution_count
        ),
        "lag_seconds": _schedule_lag_seconds(
            next_run_dt, response.active_execution_count
        ),
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "last_success_age_seconds": _seconds_since(last_success_at),
        "last_failure_age_seconds": _seconds_since(last_failure_at),
    }


def _build_ungoverned_row(
    auto: models.Automation,
    lookups: dict[str, Any],
    automation_response_by_id: dict[int, schemas.AutomationResponse],
) -> tuple[schemas.PortfolioHealthItem, schemas.PortfolioDriftItem]:
    auto_id = int(auto.id)
    response = automation_response_by_id[auto_id]
    m = _ungoverned_row_metrics(auto, response, lookups)

    issues = [
        _issue(
            "manifest_missing",
            "Automação cadastrada no Orchestrator sem automation.manifest.json correspondente.",
            runtime_value=auto.script_path,
            severity="ERROR",
        )
    ]
    drift_item = schemas.PortfolioDriftItem(
        catalog_id=f"runtime-{auto_id}",
        automation_id=auto_id,
        name=cast(str, auto.name),
        slug=_slugify(cast(str, auto.name)),
        issues=issues,
    )
    review_status, review_reasons = _build_review_status(
        catalog_id=f"runtime-{auto_id}",
        enabled=bool(auto.enabled),
        next_run=m["next_run_dt"],
        last_success_age_seconds=m["last_success_age_seconds"],
        last_failure_age_seconds=m["last_failure_age_seconds"],
        drift_count=1,
        docs_status="missing",
        health_status="not_governed",
    )
    health_item = schemas.PortfolioHealthItem(
        catalog_id=f"runtime-{auto_id}",
        automation_id=auto_id,
        name=cast(str, auto.name),
        slug=_slugify(cast(str, auto.name)),
        criticality="unclassified",
        owner_area=None,
        runtime="unknown",
        enabled=bool(auto.enabled),
        queue_group=cast(str | None, auto.queue_group),
        sla_minutes=cast(int | None, auto.sla_minutes),
        health_status="not_governed",
        sla_state=_sla_state(
            cast(int | None, auto.sla_minutes),
            schedule_lag_minutes=m["lag_minutes"],
            last_status=response.last_status,
            last_failure_age_minutes=_minutes_since(m["last_failure_at"]),
        ),
        docs_status="missing",
        drift_status="drift",
        drift_count=1,
        runbook_path=None,
        readme_path=None,
        context_path=None,
        next_run=m["next_run_dt"],
        schedule_summary=response.schedule_summary,
        schedule_lag_minutes=m["lag_minutes"],
        schedule_lag_seconds=m["lag_seconds"],
        last_status=response.last_status,
        last_success_at=m["last_success_at"],
        last_failure_at=m["last_failure_at"],
        last_success_age_minutes=_minutes_since(m["last_success_at"]),
        last_failure_age_minutes=_minutes_since(m["last_failure_at"]),
        last_success_age_seconds=m["last_success_age_seconds"],
        last_failure_age_seconds=m["last_failure_age_seconds"],
        review_status=review_status,
        review_reasons=review_reasons,
        dependency_status=schemas.PortfolioDependencyStatus(
            oracle=(
                "unknown"
                if m["latest_snapshot"].get("status") in FAILURE_STATUSES
                else "not_used"
            )
        ),
    )
    return health_item, drift_item


def _collect_governed_rows(  # pylint: disable=too-many-arguments
    root: Path,
    manifest_entries: list[Any],
    *,
    db_by_script: dict[str, models.Automation],
    db_by_name: dict[str, models.Automation],
    lookups: dict[str, Any],
    automation_response_by_id: dict[int, schemas.AutomationResponse],
) -> tuple[
    list[schemas.PortfolioHealthItem], list[schemas.PortfolioDriftItem], set[int]
]:
    matched_automation_ids: set[int] = set()
    health_items: list[schemas.PortfolioHealthItem] = []
    drift_items: list[schemas.PortfolioDriftItem] = []

    for entry in manifest_entries:
        manifest = entry.manifest
        matched_auto = _find_matching_automation(
            manifest, root, db_by_script, db_by_name
        )
        if matched_auto is not None:
            matched_automation_ids.add(int(matched_auto.id))

        health_item, drift_item = _build_governed_row(
            root, manifest, matched_auto, lookups, automation_response_by_id
        )
        health_items.append(health_item)
        drift_items.append(drift_item)

    return health_items, drift_items, matched_automation_ids


def _collect_ungoverned_rows(
    automations: list[models.Automation],
    matched_automation_ids: set[int],
    lookups: dict[str, Any],
    automation_response_by_id: dict[int, schemas.AutomationResponse],
) -> tuple[list[schemas.PortfolioHealthItem], list[schemas.PortfolioDriftItem]]:
    health_items: list[schemas.PortfolioHealthItem] = []
    drift_items: list[schemas.PortfolioDriftItem] = []
    for auto in automations:
        if int(auto.id) in matched_automation_ids:
            continue
        health_item, drift_item = _build_ungoverned_row(
            auto, lookups, automation_response_by_id
        )
        health_items.append(health_item)
        drift_items.append(drift_item)
    return health_items, drift_items


def _collect_portfolio_rows(
    db: Session,
    project_root: str | Path,
) -> tuple[list[schemas.PortfolioHealthItem], list[schemas.PortfolioDriftItem]]:
    root = Path(project_root).resolve()
    manifest_entries = load_catalog_manifests(root, include_template=False)

    automations = (
        db.query(models.Automation).order_by(models.Automation.name.asc()).all()
    )
    automation_ids = [int(auto.id) for auto in automations]
    lookups = _build_portfolio_lookups(db, automation_ids)
    db_by_script, db_by_name, automation_response_by_id = _index_automations(
        root, automations, lookups
    )

    governed = _collect_governed_rows(
        root,
        manifest_entries,
        db_by_script=db_by_script,
        db_by_name=db_by_name,
        lookups=lookups,
        automation_response_by_id=automation_response_by_id,
    )
    ungoverned = _collect_ungoverned_rows(
        automations, governed[2], lookups, automation_response_by_id
    )

    health_items = governed[0] + ungoverned[0]
    drift_items = governed[1] + ungoverned[1]

    health_items.sort(key=_sort_health_item)
    drift_items = [item for item in drift_items if item.issues]
    drift_items.sort(key=lambda item: item.name.lower())
    return health_items, drift_items


def build_portfolio_health_response(
    db: Session,
    project_root: str | Path,
) -> schemas.PortfolioHealthResponse:
    health_items, _ = _collect_portfolio_rows(db, project_root)
    summary = _build_portfolio_summary(health_items)
    return schemas.PortfolioHealthResponse(
        generated_at=schemas.format_dt_br(get_now_local()),
        summary=summary,
        items=health_items,
    )


def build_portfolio_drift_response(
    db: Session,
    project_root: str | Path,
) -> schemas.PortfolioDriftResponse:
    _, drift_items = _collect_portfolio_rows(db, project_root)
    return schemas.PortfolioDriftResponse(
        generated_at=schemas.format_dt_br(get_now_local()),
        summary=schemas.PortfolioDriftSummary(
            items_with_drift=len(drift_items),
            total_issues=sum(len(item.issues) for item in drift_items),
        ),
        items=drift_items,
    )


def read_portfolio_runbook(
    project_root: str | Path,
    catalog_id: str,
) -> tuple[str, str]:
    root = Path(project_root).resolve()
    for entry in load_catalog_manifests(root, include_template=False):
        manifest = entry.manifest
        if catalog_id not in (manifest.id, manifest.slug):
            continue
        path = _resolve_repo_path(root, manifest.runbook_path)
        return manifest.runbook_path, path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Runbook não encontrado para {catalog_id}.")
