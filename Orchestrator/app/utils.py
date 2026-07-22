"""
Utilitarios compartilhados do Orchestrator Central de Automacoes v1.0.0.

Modulo centralizado para eliminar duplicacao entre routers:
  - log_audit(): Registra trilha de auditoria no AuditLog.
  - get_client_ip(): Extrai IP do cliente de forma segura.
  - validate_script_path(): Pre-flight de existencia de script (Pilar V).
"""

import json
import logging
import os
import shutil
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .middleware import request_id_var
from .timezone import get_now_local

logger = logging.getLogger("orchestrator")

_AUDIT_DETAILS_MAX_CHARS = 20000


def _build_safe_details(details: Any, correlation_id: str) -> str:
    """Serializa os detalhes de auditoria garantindo JSON valido e tamanho limitado."""
    if details:
        try:
            parsed = json.loads(details)
            if isinstance(parsed, dict):
                parsed.setdefault("correlation_id", correlation_id)
                safe_details = json.dumps(parsed, ensure_ascii=False)
            else:
                safe_details = json.dumps(
                    {"value": parsed, "correlation_id": correlation_id},
                    ensure_ascii=False,
                )
        except (json.JSONDecodeError, TypeError):
            # details não é JSON válido: preserva como mensagem de texto simples.
            safe_details = json.dumps(
                {"message": str(details), "correlation_id": correlation_id},
                ensure_ascii=False,
            )
    else:
        safe_details = json.dumps(
            {"correlation_id": correlation_id}, ensure_ascii=False
        )

    # Truncar detalhes excessivos preservando JSON valido (evita inchaco do DB)
    if len(safe_details) > _AUDIT_DETAILS_MAX_CHARS:
        safe_details = json.dumps(
            {
                "message": safe_details[:_AUDIT_DETAILS_MAX_CHARS],
                "truncated": True,
                "correlation_id": correlation_id,
            },
            ensure_ascii=False,
        )
    return safe_details


def log_audit(  # pylint: disable=R0913,R0917
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Any,
    actor: str,
    details: str | None = None,
) -> models.AuditLog:
    """Registra uma entrada no AuditLog de forma centralizada com protecao de tamanho.

    Best-effort: falhas na auditoria nao derrubam a operacao principal — a entry
    e sempre retornada (persistida ou nao) para os callers que leem entry.id.
    """
    correlation_id = request_id_var.get("SYSTEM")
    try:
        safe_details = _build_safe_details(details, correlation_id)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Falha ao serializar detalhes de auditoria: %s", exc)
        safe_details = json.dumps(
            {"correlation_id": correlation_id, "details_error": True}
        )

    entry = models.AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        actor=actor,
        details=safe_details,
    )
    try:
        db.add(entry)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Falha ao registrar auditoria action=%s entity=%s: %s",
            action,
            entity_type,
            exc,
        )
    return entry


# ---------------------------------------------------------------------------
# IP do Cliente
# ---------------------------------------------------------------------------


def get_client_ip(request: Request) -> str:
    """Extrai IP do cliente priorizando headers de proxy reverso."""
    # Suporte a X-Forwarded-For para futuros deploys com proxy
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Backup de arquivos gerenciados
# ---------------------------------------------------------------------------


def backup_timestamped_file(source_path: str, backup_dir: str, backup_name: str) -> str:
    """Copia ``source_path`` para ``backup_dir/backup_name`` antes de sobrescrever.

    Fonte única da receita de backup (makedirs → copy2), usada por
    ``services/env_admin.py`` (backup de .env) e
    ``services/managed_file_access.py`` (backup de arquivo gerenciado de
    automação) — evita que as duas divirjam silenciosamente se a estratégia de
    cópia precisar mudar.
    """
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(source_path, backup_path)
    return backup_path


def timestamp_suffix() -> str:
    """Timestamp local no formato usado pelos nomes de arquivo de backup."""
    return get_now_local().strftime("%Y%m%d_%H%M%S_%f")


# ---------------------------------------------------------------------------
# Validacao V - Pilar de Validacao (Pre-flight)
# ---------------------------------------------------------------------------


def validate_script_path(script_path: str, project_root: str) -> tuple[bool, str]:
    """
    Resolve e valida o caminho do script.

    Retorna (True, caminho_absoluto) se o arquivo existir,
    ou (False, mensagem_de_erro) caso contrario.

    Regras:
      - Caminhos relativos (./  ou .\\) sao resolvidos contra project_root.
      - Path traversal (/../) e bloqueado.
    """
    if not script_path:
        return False, "script_path não pode ser vazio."

    # Resolver caminho
    if script_path.startswith("./") or script_path.startswith(".\\"):
        abs_path = os.path.join(project_root, script_path[2:])
    elif not os.path.isabs(script_path):
        abs_path = os.path.join(project_root, script_path)
    else:
        abs_path = script_path

    abs_path = os.path.normpath(abs_path)

    # Anti path-traversal: o caminho resolvido deve estar dentro do project_root
    if not abs_path.startswith(os.path.normpath(project_root)):
        return False, f"script_path fora do diretório permitido: {abs_path}"

    if not os.path.isfile(abs_path):
        return False, f"Script não encontrado: {abs_path}"

    return True, abs_path
