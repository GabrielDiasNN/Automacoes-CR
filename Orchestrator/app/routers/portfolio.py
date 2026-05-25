# pylint: disable=all
"""Endpoints de portfólio governado e drift entre catálogo e runtime."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..middleware import get_api_key
from ..runtime import get_project_root
from ..services.portfolio_catalog import (
    build_portfolio_drift_response,
    build_portfolio_health_response,
    read_portfolio_runbook,
)

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])

PROJECT_ROOT = get_project_root()


@router.get("/health", response_model=schemas.PortfolioHealthResponse)
def get_portfolio_health(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> schemas.PortfolioHealthResponse:
    """Cruza catálogo versionado, cadastro do Orchestrator e execução recente."""
    return build_portfolio_health_response(db, PROJECT_ROOT)


@router.get("/drift", response_model=schemas.PortfolioDriftResponse)
def get_portfolio_drift(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
) -> schemas.PortfolioDriftResponse:
    """Expõe divergências objetivas entre manifesto, documentação e runtime."""
    return build_portfolio_drift_response(db, PROJECT_ROOT)


@router.get("/runbook/{catalog_id}", response_class=PlainTextResponse)
def open_portfolio_runbook(
    catalog_id: str,
    api_key: str = Depends(get_api_key),
) -> str:
    """Retorna o Markdown bruto do runbook para visualização rápida na UI."""
    try:
        _path, content = read_portfolio_runbook(PROJECT_ROOT, catalog_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return content
