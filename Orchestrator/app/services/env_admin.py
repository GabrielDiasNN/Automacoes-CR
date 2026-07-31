"""Serviços de administração segura do arquivo .env."""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404 - execução controlada de script próprio do projeto

from .. import schemas
from ..security import ENV_MASK_PLACEHOLDER
from ..subprocess_env import build_subprocess_env
from ..utils import backup_timestamped_file, timestamp_suffix

logger = logging.getLogger("orchestrator")

# Teto do subprocesso de sincronização. Sem ele, um script travado prendia
# indefinidamente a thread que atende a requisição HTTP (31/07/2026).
_SYNC_TIMEOUT_SECONDS = 60


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
        subprocess.run(  # nosec B603 - argv fixo, sem shell
            comando,
            env=build_subprocess_env(),
            timeout=_SYNC_TIMEOUT_SECONDS,
            check=True,
        )
        return True
    except subprocess.TimeoutExpired:
        logger.error(
            "Sincronizacao de AUTOMACAO_TEST_EMAIL excedeu %ds.",
            _SYNC_TIMEOUT_SECONDS,
        )
        return False
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

        # GET /env devolve segredos mascarados (#9). O placeholder deixou de ser
        # ERRO em 31/07/2026: `restore_masked_values` o substitui pelo valor real
        # antes da escrita. A mensagem anterior mandava "remover a linha para
        # preservar o atual" — instrução que APAGAVA a chave, porque o payload
        # sobrescreve o arquivo inteiro e nunca houve merge.
        _, _, value = raw_line.partition("=")
        if value.strip() == ENV_MASK_PLACEHOLDER:
            issues.append(
                schemas.EnvValidationIssue(
                    line=idx,
                    code="MASKED_VALUE",
                    severity="info",
                    message=(
                        f"Valor de {key} está mascarado; o valor atual será "
                        "preservado. Para alterá-lo, informe o novo valor; para "
                        "remover a chave, apague a linha inteira."
                    ),
                )
            )

    bloqueantes = [issue for issue in issues if issue.severity == "error"]
    return schemas.EnvValidationResponse(
        valid=len(bloqueantes) == 0,
        issue_count=len(issues),
        normalized_line_count=len(lines),
        issues=issues,
    )


def read_env_content(env_path: str) -> str:
    if not os.path.exists(env_path):
        return ""
    with open(env_path, encoding="utf-8") as handle:
        return handle.read()


def restore_masked_values(new_content: str, current_content: str) -> str:
    """Substitui `CHAVE=********` pelo valor real que já está no `.env`.

    `GET /api/system/env` devolve os segredos mascarados, e a validação do PUT
    rejeitava o placeholder com a mensagem "informe o valor real ou **remova a
    linha para preservar o atual**". Só que `write_env_content` sobrescreve o
    arquivo INTEIRO com o payload — não havia merge nenhum. Seguir literalmente
    a instrução da própria API removia `ORCHESTRATOR_API_KEY` e as credenciais
    Oracle do arquivo; o efeito só aparecia no restart seguinte, quando o worker
    perdia o header interno e as automações perdiam o Oracle.

    Resolver o placaholder é melhor que fazer merge de chaves ausentes: preserva
    a semântica previsível de "o payload é o arquivo" (remover uma linha remove
    de fato a chave, que é uma operação legítima) e ainda assim permite o ciclo
    natural GET → editar → PUT sem reescrever todos os segredos.
    """
    atuais: dict[str, str] = {}
    for linha in current_content.splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#") or "=" not in limpa:
            continue
        chave, _, valor = limpa.partition("=")
        atuais[chave.strip()] = valor

    resultado: list[str] = []
    for linha in new_content.splitlines():
        limpa = linha.strip()
        if limpa and not limpa.startswith("#") and "=" in limpa:
            chave, _, valor = limpa.partition("=")
            chave_limpa = chave.strip()
            if valor.strip() == ENV_MASK_PLACEHOLDER and chave_limpa in atuais:
                resultado.append(f"{chave_limpa}={atuais[chave_limpa]}")
                continue
        resultado.append(linha)

    conteudo = "\n".join(resultado)
    if new_content.endswith("\n") and not conteudo.endswith("\n"):
        conteudo += "\n"
    return conteudo


def write_env_content(env_path: str, content: str) -> None:
    with open(env_path, "w", encoding="utf-8") as handle:
        handle.write(content)
