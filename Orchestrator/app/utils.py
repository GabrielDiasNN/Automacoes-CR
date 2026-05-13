# pylint: disable=all
# mypy: ignore-errors
"""
Utilitarios compartilhados do Orchestrator Central de Automacoes v5.0.

Modulo centralizado para eliminar duplicacao entre routers:
  - log_audit(): Registra trilha de auditoria no AuditLog.
  - get_client_ip(): Extrai IP do cliente de forma segura.
  - sanitize_name(): Valida naming ASCII-safe para automacoes.
  - validate_script_path(): Pre-flight de existencia de script (Pilar V).
"""

import os
import re
from datetime import datetime

import pytz
from fastapi import Request
from sqlalchemy.orm import Session

from . import models

def log_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id,
    actor: str,
    details: str = None,
) -> None:
    """Registra uma entrada no AuditLog de forma centralizada com protecao de tamanho."""
    # Truncar detalhes excessivos para evitar inchaco do DB (max 20k chars)
    safe_details = details
    if details and len(details) > 20000:
        safe_details = details[:20000] + "\n... [TRUNCATED BY SYSTEM]"

    entry = models.AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        actor=actor,
        details=safe_details,
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
# Validacao V - Pilar de Validacao (Pre-flight)
# ---------------------------------------------------------------------------

# Regex permite alfanumericos, espacos, pontos, hifens e acentuacao PT-BR comum (ASCII-Safe via Unicode Range)
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9 _\-\.À-ÿ]+$")

def sanitize_name(name: str) -> bool:
    """Retorna True se o nome e seguro para uso no sistema (sem path traversal)."""
    if not name or ".." in name:
        return False
    return bool(_SAFE_NAME_RE.match(name))

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
