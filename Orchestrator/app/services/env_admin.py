"""Serviços de administração segura do arquivo .env."""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404 - execução controlada de script próprio do projeto

from .. import schemas
from ..security import ENV_MASK_PLACEHOLDER
from ..utils import backup_timestamped_file, timestamp_suffix

logger = logging.getLogger("orchestrator")


def sync_global_test_mode_env(enabled: bool, project_root: str) -> bool:
    """Sincroniza a variável de ambiente AUTOMACAO_TEST_EMAIL via Tools.

    Extraído do router (achado #12): orquestração de subprocesso é
    responsabilidade de serviço, não de camada HTTP. Best-effort — falha aqui
    não invalida a mudança de test_mode já persistida no banco.

    Retorna True se o script foi executado com sucesso.
    """
    ps_script = os.path.join(project_root, "Tools", "ConfigurarEmailTeste.ps1")
    if not os.path.exists(ps_script):
        return False

    comando = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ps_script,
    ]
    if not enabled:
        comando.append("-Remover")

    try:
        subprocess.run(comando, check=True)  # nosec B603 - argv fixo, sem shell
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Erro ao sincronizar variavel AUTOMACAO_TEST_EMAIL: %s", exc)
        return False


def backup_env_file(project_root: str, env_path: str) -> str:
    if not os.path.exists(env_path):
        return ""
    backup_dir = os.path.join(project_root, "Backups", "env")
    backup_name = f".env.{timestamp_suffix()}.bak"
    backup_path = backup_timestamped_file(env_path, backup_dir, backup_name)
    return os.path.relpath(backup_path, project_root)


def validate_env_content(content: str) -> schemas.EnvValidationResponse:
    issues: list[schemas.EnvValidationIssue] = []
    seen_keys: set[str] = set()
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

        # GET /env devolve segredos mascarados (#9): gravar o placeholder de
        # volta sobrescreveria a credencial real por "********".
        _, _, value = raw_line.partition("=")
        if value.strip() == ENV_MASK_PLACEHOLDER:
            issues.append(
                schemas.EnvValidationIssue(
                    line=idx,
                    code="MASKED_VALUE",
                    message=(
                        f"Valor de {key} está mascarado; informe o valor real "
                        "ou remova a linha para preservar o atual."
                    ),
                )
            )

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
