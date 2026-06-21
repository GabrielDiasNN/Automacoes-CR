# pylint: disable=all
"""Validação consolidada de automações antes de persistir alterações."""

import json
import os
from typing import Any

from .. import schemas
from ..utils import validate_script_path
from .portfolio_catalog import CatalogManifest


def _is_reserved_cleanup_script(resolved_script_path: str, project_root: str) -> bool:
    reserved_path = os.path.abspath(
        os.path.join(project_root, "Tools", "AplicarPoliticaRetencao.ps1")
    )
    return os.path.normcase(resolved_script_path) == os.path.normcase(reserved_path)


def _resolve_script_candidate(script_path: str, project_root: str) -> str:
    if script_path.startswith("./") or script_path.startswith(".\\"):
        return os.path.abspath(os.path.join(project_root, script_path[2:]))
    if not os.path.isabs(script_path):
        return os.path.abspath(os.path.join(project_root, script_path))
    return os.path.abspath(script_path)


def _channels_to_csv(channels: list[str]) -> str | None:
    if not channels:
        return None
    allowed_order = ["email", "whatsapp"]
    normalized = [item for item in allowed_order if item in channels]
    return ",".join(normalized) if normalized else None


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "WARN",
) -> schemas.AutomationPreflightIssue:
    return schemas.AutomationPreflightIssue(
        code=code,
        message=message,
        severity=severity,
    )


def _project_file_exists(project_root: str, relative_path: str) -> bool:
    target = os.path.abspath(os.path.join(project_root, relative_path))
    return os.path.isfile(target)


def _load_manifest_governance(
    *,
    automation_dir: str,
    payload: dict[str, Any],
    resolved_script_path: str,
    project_root: str,
) -> schemas.AutomationPreflightGovernance:
    manifest_path = os.path.join(automation_dir, "automation.manifest.json")
    if not os.path.isfile(manifest_path):
        return schemas.AutomationPreflightGovernance(
            manifest_present=False,
            status="attention",
            top_issue="A pasta da automação não possui automation.manifest.json.",
            recommended_action="Crie ou complete o manifesto canônico antes de promover a automação.",
            warnings=[
                _issue(
                    "manifest_missing",
                    "Nenhum automation.manifest.json foi encontrado na pasta da automação.",
                )
            ],
        )

    with open(manifest_path, encoding="utf-8") as f:
        manifest_payload = json.load(f)
    manifest = CatalogManifest.model_validate(manifest_payload)
    blocking_issues: list[schemas.AutomationPreflightIssue] = []
    warnings: list[schemas.AutomationPreflightIssue] = []

    manifest_script = os.path.abspath(
        os.path.join(project_root, manifest.orchestrator.script_path.lstrip("./\\"))
    )
    if os.path.normcase(manifest_script) != os.path.normcase(resolved_script_path):
        blocking_issues.append(
            _issue(
                "script_path_mismatch",
                "O script informado diverge do orchestrator.script_path declarado no manifesto.",
                severity="ERROR",
            )
        )

    if str(payload.get("name") or "").strip() != manifest.name:
        blocking_issues.append(
            _issue(
                "name_mismatch",
                "O nome informado diverge do campo name declarado no manifesto.",
                severity="ERROR",
            )
        )

    if (payload.get("queue_group") or None) != (manifest.queue_group or None):
        blocking_issues.append(
            _issue(
                "queue_group_mismatch",
                "queue_group divergente entre o cadastro e o manifesto canônico.",
                severity="ERROR",
            )
        )

    if int(payload.get("max_runtime_minutes") or 0) != int(
        manifest.max_runtime_minutes
    ):
        blocking_issues.append(
            _issue(
                "max_runtime_mismatch",
                "max_runtime_minutes divergente entre o cadastro e o manifesto canônico.",
                severity="ERROR",
            )
        )

    if int(payload.get("max_retries") or 0) != int(manifest.max_retries):
        blocking_issues.append(
            _issue(
                "max_retries_mismatch",
                "max_retries divergente entre o cadastro e o manifesto canônico.",
                severity="ERROR",
            )
        )

    if (payload.get("sla_minutes") or None) != (manifest.sla_minutes or None):
        blocking_issues.append(
            _issue(
                "sla_mismatch",
                "sla_minutes divergente entre o cadastro e o manifesto canônico.",
                severity="ERROR",
            )
        )

    if (payload.get("notification_channels") or None) != _channels_to_csv(
        manifest.channels
    ):
        blocking_issues.append(
            _issue(
                "notification_channels_mismatch",
                "Os canais de notificação divergem do manifesto canônico.",
                severity="ERROR",
            )
        )

    if not _project_file_exists(project_root, manifest.readme_path):
        blocking_issues.append(
            _issue(
                "readme_missing",
                "README obrigatório ausente no caminho informado pelo manifesto.",
                severity="ERROR",
            )
        )
    if not _project_file_exists(project_root, manifest.context_path):
        blocking_issues.append(
            _issue(
                "context_missing",
                "CONTEXT obrigatório ausente no caminho informado pelo manifesto.",
                severity="ERROR",
            )
        )
    if not _project_file_exists(project_root, manifest.runbook_path):
        blocking_issues.append(
            _issue(
                "runbook_missing",
                "Runbook obrigatório ausente no caminho informado pelo manifesto.",
                severity="ERROR",
            )
        )

    entrypoint_path = os.path.abspath(os.path.join(automation_dir, manifest.entrypoint))
    if not os.path.isfile(entrypoint_path):
        blocking_issues.append(
            _issue(
                "entrypoint_missing",
                "Entrypoint declarado no manifesto não existe na pasta da automação.",
                severity="ERROR",
            )
        )

    for smoke_test in manifest.smoke_tests:
        if not _project_file_exists(project_root, smoke_test):
            blocking_issues.append(
                _issue(
                    "smoke_test_missing",
                    f"Smoke test declarado no manifesto não foi encontrado: {smoke_test}",
                    severity="ERROR",
                )
            )

    if not payload.get("enabled"):
        warnings.append(
            _issue(
                "automation_disabled",
                "A automação será persistida desabilitada.",
            )
        )

    if blocking_issues:
        return schemas.AutomationPreflightGovernance(
            manifest_present=True,
            manifest_path=os.path.relpath(manifest_path, project_root),
            catalog_id=manifest.id,
            status="incident",
            top_issue="O cadastro diverge do manifesto governado ou possui dependências obrigatórias ausentes.",
            recommended_action="Alinhe o payload ao automation.manifest.json antes de salvar.",
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

    if warnings:
        return schemas.AutomationPreflightGovernance(
            manifest_present=True,
            manifest_path=os.path.relpath(manifest_path, project_root),
            catalog_id=manifest.id,
            status="attention",
            top_issue="O cadastro está coerente com o manifesto, mas exige atenção operacional.",
            recommended_action="Revise os avisos antes de promover a automação para operação recorrente.",
            warnings=warnings,
        )

    return schemas.AutomationPreflightGovernance(
        manifest_present=True,
        manifest_path=os.path.relpath(manifest_path, project_root),
        catalog_id=manifest.id,
        status="healthy",
        top_issue="Cadastro alinhado ao manifesto governado.",
        recommended_action=None,
    )


def build_automation_preflight(
    payload: dict[str, Any],
    project_root: str,
) -> schemas.AutomationPreflightResponse:
    validated = schemas.AutomationCreate.model_validate(payload)
    normalized_payload = validated.model_dump()

    resolved_candidate = _resolve_script_candidate(validated.script_path, project_root)
    if _is_reserved_cleanup_script(resolved_candidate, project_root):
        raise ValueError(
            "Validação do script: Tools/AplicarPoliticaRetencao.ps1 é uma rotina reservada do sistema e não pode ser cadastrada como automação comum."
        )

    ok, result = validate_script_path(validated.script_path, project_root)
    if not ok:
        raise ValueError(f"Validação do script: {result}")

    resolved_script_path = os.path.abspath(result)
    automation_dir = os.path.dirname(resolved_script_path)
    parsed_schedule = (
        schemas.parse_schedule(validated.schedule) if validated.schedule else None
    )

    warnings: list[str] = []
    if not validated.notification_channels:
        warnings.append("Automação sem canais de notificação configurados.")
    if not validated.queue_group:
        warnings.append("Automação sem queue_group dedicado.")
    if not validated.enabled:
        warnings.append("Automação será persistida desabilitada.")

    governance = _load_manifest_governance(
        automation_dir=automation_dir,
        payload=normalized_payload,
        resolved_script_path=resolved_script_path,
        project_root=project_root,
    )
    is_valid = governance.status != "incident"

    return schemas.AutomationPreflightResponse(
        valid=is_valid,
        validated=is_valid,
        normalized_payload=normalized_payload,
        resolved_script_path=resolved_script_path,
        automation_dir=automation_dir,
        normalized_notification_channels=validated.notification_channels,
        schedule_summary=schemas.describe_schedule_payload(parsed_schedule),
        next_runs_preview=schemas.preview_next_runs(parsed_schedule, 5),
        warnings=warnings,
        governance=governance,
    )
