# pylint: disable=all
# mypy: ignore-errors
"""Serviços de administração segura do arquivo .env."""

import os
import shutil

from .. import schemas
from ..timezone import get_now_local


def backup_env_file(project_root: str, env_path: str) -> str:
    if not os.path.exists(env_path):
        return ""
    backup_dir = os.path.join(project_root, "Backups", "env")
    os.makedirs(backup_dir, exist_ok=True)
    ts = get_now_local().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = os.path.join(backup_dir, f".env.{ts}.bak")
    shutil.copy2(env_path, backup_path)
    return os.path.relpath(backup_path, project_root)


def validate_env_content(content: str) -> schemas.EnvValidationResponse:
    issues = []
    seen_keys = set()
    lines = content.splitlines()

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in raw_line:
            issues.append(
                schemas.EnvValidationIssue(
                    line=idx,
                    code="INVALID_FORMAT",
                    message="Linha deve seguir o formato CHAVE=VALOR.",
                )
            )
            continue
        key, _ = raw_line.split("=", 1)
        key = key.strip()
        if not key:
            issues.append(
                schemas.EnvValidationIssue(
                    line=idx,
                    code="EMPTY_KEY",
                    message="Chave vazia não é permitida.",
                )
            )
            continue
        if " " in key:
            issues.append(
                schemas.EnvValidationIssue(
                    line=idx,
                    code="INVALID_KEY",
                    message="Chave não pode conter espaços.",
                )
            )
        if key in seen_keys:
            issues.append(
                schemas.EnvValidationIssue(
                    line=idx,
                    code="DUPLICATE_KEY",
                    message=f"Chave duplicada detectada: {key}.",
                )
            )
        seen_keys.add(key)

    return schemas.EnvValidationResponse(
        valid=len(issues) == 0,
        issue_count=len(issues),
        normalized_line_count=len(lines),
        issues=issues,
    )


def read_env_content(env_path: str) -> str:
    if not os.path.exists(env_path):
        return ""
    with open(env_path, encoding="utf-8") as handle:
        return handle.read()


def write_env_content(env_path: str, content: str) -> None:
    with open(env_path, "w", encoding="utf-8") as handle:
        handle.write(content)
