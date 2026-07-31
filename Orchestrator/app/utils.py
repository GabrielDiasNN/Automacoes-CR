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
from .path_safety import is_contained
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
    """Registra uma entrada no AuditLog de forma centralizada, com truncamento.

    ATENÇÃO — a entry é ATÔMICA com a operação de negócio, não best-effort. O
    `db.commit()` que a persiste é o do router, na mesma transação da mutação:
    mudança sem trilha não é um desfecho aceitável para CREATE/UPDATE/DELETE de
    automação, UPDATE_ENV ou REQUEUE.

    A docstring anterior prometia "best-effort: falhas na auditoria nao derrubam
    a operacao principal", mas o `try/except` cobre apenas o `db.add` — que põe
    o objeto na sessão e praticamente não falha. A escrita real, e portanto
    qualquer erro de flush, acontecia fora da proteção. A garantia era o oposto
    da documentada. Em vez de mover a auditoria para sessão própria (o que
    permitiria mutação registrada sem trilha e invalidaria os `audit_id` que os
    routers já devolvem), os campos passaram a ser truncados na origem,
    eliminando a causa realista de falha de flush.
    """
    correlation_id = request_id_var.get("SYSTEM")
    try:
        safe_details = _build_safe_details(details, correlation_id)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Falha ao serializar detalhes de auditoria: %s", exc)
        safe_details = json.dumps(
            {"correlation_id": correlation_id, "details_error": True}
        )

    # Truncamento defensivo. A entry participa da MESMA transação da mutação de
    # negócio (o `db.commit()` é do router), então um erro de flush aqui —
    # `details` acima do limite da coluna, `actor` longo demais — abortaria a
    # transação inteira e devolveria 500 para uma operação já validada. O
    # `try/except` abaixo não protege contra isso: ele cobre apenas o `db.add`,
    # que praticamente não falha por só pôr o objeto na sessão.
    entry = models.AuditLog(
        action=str(action)[:_MAX_AUDIT_ACTION_LENGTH],
        entity_type=str(entity_type)[:_MAX_AUDIT_ENTITY_TYPE_LENGTH],
        entity_id=(
            str(entity_id)[:_MAX_AUDIT_ENTITY_ID_LENGTH]
            if entity_id is not None
            else None
        ),
        actor=str(actor)[:_MAX_ACTOR_LENGTH],
        # `details` NÃO é truncado aqui: `_build_safe_details` já o limita
        # produzindo JSON válido (com a marca `truncated: true`). Cortar a
        # string crua neste ponto partiria o JSON no meio.
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


# Limite do valor gravado como `AuditLog.actor` / `Execution.requested_by`.
# `String(100)` não é imposto pelo SQLite, então sem truncamento explícito cabia
# conteúdo arbitrário na trilha de auditoria.
_MAX_ACTOR_LENGTH = 45  # comporta um IPv6 completo (39) com folga

# Limites das colunas de `AuditLog` (models.py). Aplicados na origem porque a
# entry participa da transação da mutação: um erro de flush aqui aborta a
# operação de negócio inteira.
_MAX_AUDIT_ACTION_LENGTH = 50
_MAX_AUDIT_ENTITY_TYPE_LENGTH = 50
_MAX_AUDIT_ENTITY_ID_LENGTH = 50


def _trusted_proxies() -> set[str]:
    """IPs de proxy reverso confiáveis, de `ORCHESTRATOR_TRUSTED_PROXIES`.

    Vazio por padrão: o deploy atual sobe uvicorn direto em 127.0.0.1, sem
    proxy nenhum (`Start-Orchestrator.ps1`).
    """
    raw = os.environ.get("ORCHESTRATOR_TRUSTED_PROXIES", "")
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def get_client_ip(request: Request) -> str:
    """IP do cliente, confiando em `X-Forwarded-For` apenas atrás de proxy conhecido.

    Até 31/07/2026 esta função retornava incondicionalmente o primeiro elemento
    de `X-Forwarded-For` quando o header existia, sem lista de proxies
    confiáveis — e o valor é gravado como `AuditLog.actor`, o artefato de
    não-repúdio, e como `Execution.requested_by`. Qualquer cliente com a API Key
    podia forjar o autor de CREATE/UPDATE/DELETE de automação, UPDATE_ENV,
    UPDATE_SCRIPT, STOP e REQUEUE mandando o header.

    O `RateLimitMiddleware` e a detecção de brute-force já usavam
    deliberadamente `request.client.host` por esse motivo; a trilha de auditoria
    ficara de fora dessa decisão. O suporte a proxy continua disponível, agora
    explícito: declare os IPs em `ORCHESTRATOR_TRUSTED_PROXIES`.
    """
    socket_ip = request.client.host if request.client else "unknown"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and socket_ip in _trusted_proxies():
        return forwarded.split(",")[0].strip()[:_MAX_ACTOR_LENGTH]
    return socket_ip[:_MAX_ACTOR_LENGTH]


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

    # Anti path-traversal: o caminho resolvido deve estar dentro do project_root.
    # Era `abs_path.startswith(...)` até 31/07/2026 — prefixo de string não
    # respeita fronteira de diretório, então `C:\Automacoes_bkp\qualquer.ps1`
    # passava como "dentro do projeto" e o worker executaria esse script.
    if not is_contained(project_root, abs_path):
        return False, f"script_path fora do diretório permitido: {abs_path}"

    if not os.path.isfile(abs_path):
        return False, f"Script não encontrado: {abs_path}"

    return True, abs_path
