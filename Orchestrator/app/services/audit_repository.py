"""Acesso a dados de `AuditLog` usado pelo router de sistema.

Mesma disciplina de `automation_repository` / `execution_repository` (achado A6
da revisão arquitetural e nº 6 da revisão Orchestrator/Dashboard): a camada HTTP
não monta consulta ORM. `AuditLog` não tinha repositório dedicado — a rota
`/api/system/audit` era o único ponto que ainda consultava o modelo direto.
"""

# pylint: disable=relative-beyond-top-level

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import models


def list_recent(
    db: Session, *, limit: int, action: str | None = None
) -> list[models.AuditLog]:
    """Entradas de auditoria mais recentes, opcionalmente filtradas por ação.

    `limit` já deve vir validado pelo `Query(ge=, le=)` do endpoint.
    """
    query = db.query(models.AuditLog)
    if action:
        query = query.filter(models.AuditLog.action == action.upper())
    return query.order_by(desc(models.AuditLog.timestamp)).limit(limit).all()
