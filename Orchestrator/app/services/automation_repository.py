"""Acesso a dados de `Automation` e `Execution` usado pelo router de automações.

Extraído do router (achado A6 da revisão arquitetural): a camada HTTP não deve
montar consulta ORM. As funções aqui são deliberadamente puras de HTTP — devolvem
`None` ou coleções vazias e deixam a tradução para 404/409 no router, seguindo o
padrão já adotado pelos demais serviços do Orchestrator.
"""

# pylint: disable=relative-beyond-top-level

from __future__ import annotations

from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import models
from ..constants import EXECUTION_ACTIVE_STATUSES
from ..timezone import get_now_local

# Campos aceitos na ordenação da listagem paginada. O router valida contra este
# conjunto antes de chamar `paginate` — manter aqui mantém o contrato junto da query.
ALLOWED_SORT_FIELDS = frozenset(
    {
        "id",
        "name",
        "script_path",
        "test_mode",
        "priority",
        "max_runtime_minutes",
        "created_at",
        "updated_at",
    }
)


def get_by_id(db: Session, automation_id: int) -> models.Automation | None:
    """Retorna a automação pelo id, ou `None` se não existir."""
    return (
        db.query(models.Automation)
        .filter(models.Automation.id == automation_id)
        .first()
    )


def get_by_name(db: Session, name: str) -> models.Automation | None:
    """Retorna a automação pelo nome exato, ou `None` se não existir."""
    return db.query(models.Automation).filter(models.Automation.name == name).first()


def list_all_ordered(db: Session) -> list[models.Automation]:
    """Lista todas as automações ordenadas por nome."""
    return db.query(models.Automation).order_by(models.Automation.name).all()


def paginate(  # pylint: disable=too-many-arguments
    # Os cinco filtros sao keyword-only e vem diretos dos query params do
    # endpoint; agrupa-los num objeto so acrescentaria uma camada de traducao.
    db: Session,
    *,
    search: str | None,
    sort: str,
    descending: bool,
    page: int,
    per_page: int,
) -> tuple[list[models.Automation], int]:
    """Retorna a página de automações e o total de registros do filtro.

    `sort` já deve ter sido validado contra `ALLOWED_SORT_FIELDS`.
    """
    query = db.query(models.Automation)

    if search:
        query = query.filter(models.Automation.name.ilike(f"%{search}%"))

    sort_column = getattr(models.Automation, sort, models.Automation.name)
    query = query.order_by(sort_column.desc() if descending else sort_column.asc())

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def next_available_clone_name(db: Session, base_name: str) -> str:
    """Resolve um nome livre para clone, sufixando com um contador se necessário."""
    candidate = base_name
    idx = 2
    while get_by_name(db, candidate) is not None:
        candidate = f"{base_name} {idx}"
        idx += 1
    return candidate


def get_recent_executions(
    db: Session, automation_id: int, limit: int = 10
) -> list[models.Execution]:
    """Últimas execuções da automação, da mais recente para a mais antiga."""
    return (
        db.query(models.Execution)
        .filter(models.Execution.automation_id == automation_id)
        .order_by(models.Execution.started_at.desc())
        .limit(limit)
        .all()
    )


def get_active_execution(db: Session, automation_id: int) -> models.Execution | None:
    """Execução ativa da automação (proteção contra disparo duplicado)."""
    return (
        db.query(models.Execution)
        .filter(
            models.Execution.automation_id == automation_id,
            models.Execution.status.in_(EXECUTION_ACTIVE_STATUSES),
        )
        .first()
    )


def get_latest_execution(db: Session, automation_id: int) -> models.Execution | None:
    """Execução mais recente da automação, usada no cálculo de cooldown."""
    return (
        db.query(models.Execution)
        .filter(models.Execution.automation_id == automation_id)
        .order_by(desc(models.Execution.started_at))
        .first()
    )


def set_enabled_for_all(db: Session, enabled: bool) -> None:
    """Pausa (`False`) ou retoma (`True`) todas as automações. Não comita."""
    db.query(models.Automation).update({models.Automation.enabled: enabled})


def set_test_mode_for_all(db: Session, enabled: bool) -> None:
    """Aplica o Modo Teste a todas as automações. Não comita."""
    values: dict[Any, Any] = {
        models.Automation.test_mode: enabled,
        models.Automation.updated_at: get_now_local(),
    }
    db.query(models.Automation).update(values)
