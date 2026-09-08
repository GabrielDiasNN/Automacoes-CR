"""Acesso a dados de `Execution` usado pelo router de execuções.

Extraído do router (achado A6 da revisão arquitetural). Como em
`automation_repository`, as funções são puras de HTTP: devolvem `None` ou
coleções vazias e deixam a tradução para 404 na camada HTTP.
"""

# pylint: disable=relative-beyond-top-level

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func
from sqlalchemy.orm import Query, Session, joinedload

from .. import models
from ..constants import EXECUTION_ACTIVE_STATUSES


def base_query_with_automation(db: Session) -> Query[models.Execution]:
    """Query base de execuções com a automação carregada (evita N+1)."""
    return db.query(models.Execution).options(joinedload(models.Execution.automation))


def apply_filters(  # pylint: disable=R0913,R0917
    query: Query[models.Execution],
    *,
    status: str | None = None,
    priority: str | None = None,
    automation_id: int | None = None,
    queue_group: str | None = None,
    requested_by: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Query[models.Execution]:
    """Monta os predicados ORM da listagem de execuções.

    Assume valores já normalizados e validados pela camada HTTP (enum em
    maiúsculas, datas já parseadas) — quem valida e traduz erro para 422 é o
    router (`routers/executions.py`); aqui só se monta a consulta, como nas
    demais funções deste módulo (achado de aderência arquitetural: a
    montagem de query ORM não deve viver em `routers/`).
    """
    if status:
        query = query.filter(models.Execution.status == status)
    if priority:
        query = query.filter(models.Execution.priority == priority)
    if automation_id:
        query = query.filter(models.Execution.automation_id == automation_id)
    if queue_group:
        query = query.filter(models.Execution.queue_group == queue_group)
    if requested_by:
        query = query.filter(models.Execution.requested_by.ilike(f"%{requested_by}%"))
    if date_from:
        query = query.filter(models.Execution.started_at >= date_from)
    if date_to:
        query = query.filter(models.Execution.started_at <= date_to)
    return query


def count_active(db: Session) -> int:
    """Número de execuções em status ativo (PENDING/RUNNING/…).

    Usado pela rota de recuperação do worker para reportar o tamanho da fila
    presa quando o processo cai.
    """
    total = (
        db.query(func.count(models.Execution.id))  # pylint: disable=not-callable
        .filter(models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES))
        .scalar()
    )
    return int(total or 0)


def get_by_id(db: Session, exec_id: str) -> models.Execution | None:
    """Retorna a execução pelo id, sem carregar a automação."""
    return db.query(models.Execution).filter(models.Execution.id == exec_id).first()


def get_by_id_with_automation(db: Session, exec_id: str) -> models.Execution | None:
    """Retorna a execução pelo id, com a automação já carregada."""
    return base_query_with_automation(db).filter(models.Execution.id == exec_id).first()


def get_recent(db: Session, limit: int) -> list[models.Execution]:
    """Execuções mais recentes de todas as automações."""
    return (
        base_query_with_automation(db)
        .order_by(desc(models.Execution.started_at))
        .limit(limit)
        .all()
    )


def get_recent_by_automation(
    db: Session, automation_id: int, limit: int
) -> list[models.Execution]:
    """Execuções mais recentes de uma automação específica."""
    return (
        base_query_with_automation(db)
        .filter(models.Execution.automation_id == automation_id)
        .order_by(desc(models.Execution.started_at))
        .limit(limit)
        .all()
    )


def get_automation_by_name(db: Session, name: str) -> models.Automation | None:
    """Resolve a automação pelo nome (disparo externo informa nome, não id)."""
    return db.query(models.Automation).filter(models.Automation.name == name).first()
