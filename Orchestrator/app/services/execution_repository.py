"""Acesso a dados de `Execution` usado pelo router de execuções.

Extraído do router (achado A6 da revisão arquitetural). Como em
`automation_repository`, as funções são puras de HTTP: devolvem `None` ou
coleções vazias e deixam a tradução para 404 na camada HTTP.
"""

# pylint: disable=relative-beyond-top-level

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Query, Session, joinedload

from .. import models


def base_query_with_automation(db: Session) -> Query[models.Execution]:
    """Query base de execuções com a automação carregada (evita N+1)."""
    return db.query(models.Execution).options(joinedload(models.Execution.automation))


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
