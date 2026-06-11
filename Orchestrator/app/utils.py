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

import json
import logging
import os
import re
from datetime import datetime

import pytz
from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .middleware import request_id_var

logger = logging.getLogger("orchestrator")

_AUDIT_DETAILS_MAX_CHARS = 20000


def _build_safe_details(details, correlation_id: str) -> str:
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
        except Exception:
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


def log_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id,
    actor: str,
    details: str = None,
) -> models.AuditLog:
    """Registra uma entrada no AuditLog de forma centralizada com protecao de tamanho.

    Best-effort: falhas na auditoria nao derrubam a operacao principal — a entry
    e sempre retornada (persistida ou nao) para os callers que leem entry.id.
    """
    correlation_id = request_id_var.get("SYSTEM")
    try:
        safe_details = _build_safe_details(details, correlation_id)
    except Exception as exc:
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
    except Exception as exc:
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
