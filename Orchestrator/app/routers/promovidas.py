"""Endpoints snapshot-first de consultas promovidas (sem acesso direto ao Oracle)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..middleware import get_api_key
from ..runtime import get_project_root
from ..services import promovidas as promovidas_service
from ..services.domain_errors import DomainRuleError

router = APIRouter(prefix="/api/promovidas", tags=["Consultas Promovidas"])


@router.get("/", dependencies=[Depends(get_api_key)])
def list_promovidas() -> dict[str, Any]:
    """Lista todas as consultas promovidas e o resumo do snapshot mais recente."""
    root = Path(get_project_root())
    return {"items": promovidas_service.listar_promocoes(root)}


@router.get("/{slug}/latest", dependencies=[Depends(get_api_key)])
def get_promovida_latest(slug: str) -> dict[str, Any]:
    """Retorna o snapshot mais recente de uma consulta promovida."""
    root = Path(get_project_root())
    try:
        return promovidas_service.obter_ultimo_snapshot(root, slug)
    except DomainRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{slug}/history", dependencies=[Depends(get_api_key)])
def get_promovida_history(
    slug: str,
    limit: int = Query(30, ge=1, le=200),
) -> dict[str, Any]:
    """Retorna o historico resumido de snapshots de uma consulta promovida."""
    root = Path(get_project_root())
    try:
        items = promovidas_service.obter_historico(root, slug, limit=limit)
    except DomainRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"slug": slug, "items": items}
