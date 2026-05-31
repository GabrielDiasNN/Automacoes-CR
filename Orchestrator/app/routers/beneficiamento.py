"""Endpoints snapshot-first de Beneficiamento."""
# pylint: disable=relative-beyond-top-level,unused-argument,too-many-arguments,too-many-positional-arguments,line-too-long,trailing-newlines

import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import schemas
from ..middleware import get_api_key
from ..runtime import get_project_root
from ..services.beneficiamento_dashboard import (
    build_beneficiamento_dashboard_payload,
    build_beneficiamento_health_payload,
    build_beneficiamento_period_payload,
    build_beneficiamento_periods_payload,
)

router = APIRouter(prefix="/api/beneficiamento", tags=["Beneficiamento"])

PROJECT_ROOT = get_project_root()

# Inserção portátil do diretório de sources do beneficiamento no path do runtime do FastAPI
src_dir = Path(PROJECT_ROOT).resolve() / "Produção Beneficimento" / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from beneficiamento.historico_db import buscar_historico, obter_analytics_historico  # type: ignore
except ImportError:
    buscar_historico = None
    obter_analytics_historico = None


@router.get("/dashboard", response_model=schemas.BeneficiamentoDashboardPayload)
def get_beneficiamento_dashboard(
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoDashboardPayload:
    """Consolida snapshots locais para o dashboard analítico."""

    return schemas.BeneficiamentoDashboardPayload.model_validate(
        build_beneficiamento_dashboard_payload(PROJECT_ROOT)
    )


@router.get("/health", response_model=schemas.BeneficiamentoHealthResponse)
def get_beneficiamento_health(
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoHealthResponse:
    """Expõe saúde, frescor e orçamento Oracle dos snapshots."""

    return schemas.BeneficiamentoHealthResponse.model_validate(
        build_beneficiamento_health_payload(PROJECT_ROOT)
    )


@router.get("/periods", response_model=schemas.BeneficiamentoPeriodsResponse)
def get_beneficiamento_periods(
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoPeriodsResponse:
    """Lista os períodos disponíveis a partir de snapshots locais."""

    return schemas.BeneficiamentoPeriodsResponse.model_validate(
        build_beneficiamento_periods_payload(PROJECT_ROOT)
    )


@router.get("/periods/{period}", response_model=schemas.BeneficiamentoPeriodPayload)
def get_beneficiamento_period(
    period: str,
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoPeriodPayload:
    """Retorna um período específico sem abrir conexão Oracle."""

    try:
        return schemas.BeneficiamentoPeriodPayload.model_validate(
            build_beneficiamento_period_payload(PROJECT_ROOT, period)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/historico", response_model=schemas.BeneficiamentoHistoricoResponse)
def get_beneficiamento_historico(
    ob: Optional[str] = Query(None, description="Número da OB (busca parcial)"),
    alternativo: Optional[str] = Query(None, description="Código Alternativo ou Reduzido do produto"),
    dt_inicio: Optional[str] = Query(None, description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    dt_fim: Optional[str] = Query(None, description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    ano_sem: Optional[int] = Query(None, description="Código do Ano + Semana ISO (ex: 202622)"),
    ano_mes: Optional[str] = Query(None, description="Código do Ano + Mês (ex: 202605)"),
    limit: int = Query(500, description="Limite máximo de registros retornados"),
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoHistoricoResponse:
    """Realiza buscas rápidas no SQLite indexado local para rastreabilidade de OBs e produtos."""

    if buscar_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    filtros = {
        "ob": ob,
        "alternativo": alternativo,
        "dt_inicio": dt_inicio,
        "dt_fim": dt_fim,
        "ano_sem": ano_sem,
        "ano_mes": ano_mes,
    }

    try:
        records = buscar_historico(filtros, limit=limit)
        return schemas.BeneficiamentoHistoricoResponse(
            total_records=len(records), records=records
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro na busca SQLite: {exc}") from exc


@router.get("/historico/analytics", response_model=schemas.BeneficiamentoAnalyticsResponse)
# pylint: disable=too-many-arguments,too-many-positional-arguments
def get_beneficiamento_historico_analytics(
    ob: Optional[str] = Query(None, description="Número da OB (busca parcial)"),
    alternativo: Optional[str] = Query(None, description="Código Alternativo ou Reduzido do produto"),
    dt_inicio: Optional[str] = Query(None, description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    dt_fim: Optional[str] = Query(None, description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    ano_sem: Optional[int] = Query(None, description="Código do Ano + Semana ISO (ex: 202622)"),
    ano_mes: Optional[str] = Query(None, description="Código do Ano + Mês (ex: 202605)"),
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoAnalyticsResponse:
    """Retorna KPIs agregados de OEE e PCP do histórico indexado do Beneficiamento."""

    if obter_analytics_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    filtros = {
        "ob": ob,
        "alternativo": alternativo,
        "dt_inicio": dt_inicio,
        "dt_fim": dt_fim,
        "ano_sem": ano_sem,
        "ano_mes": ano_mes,
    }

    try:
        data = obter_analytics_historico(filtros)
        return schemas.BeneficiamentoAnalyticsResponse.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro no cálculo de analytics SQLite: {exc}") from exc


