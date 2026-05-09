"""
Utilitários compartilhados do Orchestrator Hub Soberano v5.0.

Módulo centralizado para eliminar duplicação entre routers:
  - log_audit(): Registra trilha de auditoria no AuditLog.
  - get_client_ip(): Extrai IP do cliente de forma segura.
  - sanitize_name(): Valida naming ASCII-safe para automações.
  - validate_script_path(): Pré-flight de existência de script (Pilar V).
"""

import os
import re

from fastapi import Request
from sqlalchemy.orm import Session

from . import models


# ---------------------------------------------------------------------------
# Auditoria (deduplicação de automations.py e executions.py)
# ---------------------------------------------------------------------------

def log_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id,
    actor: str,
    details: str = None,
) -> None:
    """Registra uma entrada no AuditLog de forma centralizada."""
    entry = models.AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        actor=actor,
        details=details,
    )
    db.add(entry)


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
# Validação V — Pilar de Validação (Pre-flight)
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9 _\-\.]+$")


def sanitize_name(name: str) -> bool:
    """Retorna True se o nome é ASCII-safe (sem path traversal)."""
    return bool(_SAFE_NAME_RE.match(name)) if name else False


def validate_script_path(script_path: str, project_root: str) -> tuple[bool, str]:
    """
    Resolve e valida o caminho do script.

    Retorna (True, caminho_absoluto) se o arquivo existir,
    ou (False, mensagem_de_erro) caso contrário.

    Regras:
      - Caminhos relativos (./  ou .\\) são resolvidos contra project_root.
      - Path traversal (/../) é bloqueado.
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
