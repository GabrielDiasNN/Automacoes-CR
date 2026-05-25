# pylint: disable=all
"""Validação consolidada de automações antes de persistir alterações."""

import os
from typing import Any

from .. import schemas
from ..utils import validate_script_path


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

    return schemas.AutomationPreflightResponse(
        valid=True,
        validated=True,
        normalized_payload=normalized_payload,
        resolved_script_path=resolved_script_path,
        automation_dir=automation_dir,
        normalized_notification_channels=validated.notification_channels,
        schedule_summary=schemas.describe_schedule_payload(parsed_schedule),
        next_runs_preview=schemas.preview_next_runs(parsed_schedule, 5),
        warnings=warnings,
    )
