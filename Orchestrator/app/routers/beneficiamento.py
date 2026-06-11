"""Endpoints de PCP e OEE de Beneficiamento baseados no SQLite Histórico."""
# pylint: disable=relative-beyond-top-level,unused-argument,too-many-arguments,too-many-positional-arguments,line-too-long,trailing-newlines

import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import schemas
from ..middleware import get_api_key
from ..runtime import get_project_root

router = APIRouter(prefix="/api/beneficiamento", tags=["Beneficiamento"])

PROJECT_ROOT = get_project_root()

# Inserção portátil do diretório de sources do beneficiamento no path do runtime do FastAPI
src_dir = Path(PROJECT_ROOT).resolve() / "Produção Beneficimento" / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from beneficiamento.historico_db import buscar_historico  # type: ignore
    from beneficiamento.overview_v1 import obter_analytics_historico, obter_detail_historico, obter_overview_historico  # type: ignore
    from beneficiamento.snapshot_dashboard import build_dashboard_payload, build_health_payload, build_periods_payload, load_period_payload  # type: ignore
except ImportError:
    buscar_historico = None
    obter_analytics_historico = None
    obter_detail_historico = None
    obter_overview_historico = None
    build_dashboard_payload = None
    build_health_payload = None
    build_periods_payload = None
    load_period_payload = None


def _ensure_snapshot_dashboard() -> None:
    if build_dashboard_payload is None or build_health_payload is None or build_periods_payload is None or load_period_payload is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de snapshots do beneficiamento indisponível.",
        )


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


@router.get("/overview", response_model=schemas.BeneficiamentoOverviewResponse)
def get_beneficiamento_overview(
    dt_inicio: Optional[str] = Query(None, description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    dt_fim: Optional[str] = Query(None, description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    maquina: Optional[str] = Query(None, description="Nome da máquina para filtro"),
    fase: Optional[str] = Query(None, description="Nome da fase para filtro"),
    turno: Optional[str] = Query(None, description="Turno específico para filtro"),
    alternativo: Optional[str] = Query(None, description="Código Alternativo principal do produto"),
    q: Optional[str] = Query(None, description="Busca por OB, produto, artigo, cor ou código"),
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoOverviewResponse:
    """Retorna o contrato operacional V1 do Beneficiamento a partir do SQLite local."""

    if obter_overview_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    filtros = {
        "dt_inicio": dt_inicio,
        "dt_fim": dt_fim,
        "maquina": maquina,
        "fase": fase,
        "turno": turno,
        "alternativo": alternativo,
        "q": q,
    }

    try:
        data = obter_overview_historico(filtros)
        return schemas.BeneficiamentoOverviewResponse.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro no overview SQLite: {exc}") from exc


@router.get("/health", response_model=schemas.BeneficiamentoHealthResponse)
def get_beneficiamento_health(
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoHealthResponse:
    """Expõe a saúde operacional dos snapshots locais do Beneficiamento."""

    _ensure_snapshot_dashboard()

    try:
        data = build_health_payload()
        return schemas.BeneficiamentoHealthResponse.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro na saúde dos snapshots: {exc}") from exc


@router.get("/periods", response_model=schemas.BeneficiamentoPeriodsResponse)
def get_beneficiamento_periods(
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoPeriodsResponse:
    """Lista os períodos disponíveis e seus metadados de snapshot."""

    _ensure_snapshot_dashboard()

    try:
        data = build_periods_payload()
        return schemas.BeneficiamentoPeriodsResponse.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao listar períodos: {exc}") from exc


@router.get("/periods/{period}", response_model=schemas.BeneficiamentoPeriodPayload)
def get_beneficiamento_period(
    period: str,
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoPeriodPayload:
    """Retorna o snapshot consolidado de um período do Beneficiamento."""

    _ensure_snapshot_dashboard()

    try:
        data = load_period_payload(period)
        return schemas.BeneficiamentoPeriodPayload.model_validate(data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar período: {exc}") from exc


@router.get("/dashboard", response_model=schemas.BeneficiamentoDashboardPayload)
def get_beneficiamento_dashboard(
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoDashboardPayload:
    """Agrega períodos, saúde e comparação para a home analítica da aba."""

    _ensure_snapshot_dashboard()

    try:
        data = build_dashboard_payload()
        return schemas.BeneficiamentoDashboardPayload.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro no dashboard de snapshots: {exc}") from exc


@router.get("/detail", response_model=schemas.BeneficiamentoDetailResponse)
# pylint: disable=too-many-locals
def get_beneficiamento_detail(
    target_type: str = Query(..., description="Tipo do detalhe: produto, maquina_fase, fase, turno ou ob"),
    dt_inicio: Optional[str] = Query(None, description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    dt_fim: Optional[str] = Query(None, description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    maquina: Optional[str] = Query(None, description="Nome da máquina para filtro"),
    fase: Optional[str] = Query(None, description="Nome da fase para filtro"),
    turno: Optional[str] = Query(None, description="Turno específico para filtro"),
    alternativo: Optional[str] = Query(None, description="Código Alternativo principal do produto"),
    ob: Optional[str] = Query(None, description="Número da OB"),
    q: Optional[str] = Query(None, description="Busca por OB, produto, artigo, cor ou código"),
    page: int = Query(1, description="Página do detalhe"),
    limit: int = Query(50, description="Limite máximo por página"),
    include_raw: bool = Query(False, description="Quando verdadeiro, devolve também o payload bruto"),
    api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoDetailResponse:
    """Retorna o drill-down operacional do Beneficiamento a partir do SQLite local."""

    if obter_detail_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    filtros = {
        "target_type": target_type,
        "dt_inicio": dt_inicio,
        "dt_fim": dt_fim,
        "maquina": maquina,
        "fase": fase,
        "turno": turno,
        "alternativo": alternativo,
        "ob": ob,
        "q": q,
        "page": page,
        "limit": limit,
        "include_raw": include_raw,
    }

    try:
        data = obter_detail_historico(filtros)
        return schemas.BeneficiamentoDetailResponse.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro no detalhe SQLite: {exc}") from exc


@router.get("/historico/analytics", response_model=schemas.BeneficiamentoAnalyticsResponse)
# pylint: disable=too-many-arguments,too-many-positional-arguments
def get_beneficiamento_historico_analytics(
    ob: Optional[str] = Query(None, description="Número da OB (busca parcial)"),
    alternativo: Optional[str] = Query(None, description="Código Alternativo ou Reduzido do produto"),
    dt_inicio: Optional[str] = Query(None, description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    dt_fim: Optional[str] = Query(None, description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    ano_sem: Optional[int] = Query(None, description="Código do Ano + Semana ISO (ex: 202622)"),
    ano_mes: Optional[str] = Query(None, description="Código do Ano + Mês (ex: 202605)"),
    busca: Optional[str] = Query(None, description="Termo de busca textual para produto/artigo"),
    maquina: Optional[str] = Query(None, description="Nome da máquina para filtro"),
    fase: Optional[str] = Query(None, description="Nome da fase para filtro"),
    turno: Optional[str] = Query(None, description="Turno específico para filtro"),
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
        "busca": busca,
        "maquina": maquina,
        "fase": fase,
        "turno": turno,
    }

    try:
        data = obter_analytics_historico(filtros)
        return schemas.BeneficiamentoAnalyticsResponse.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro no cálculo de analytics SQLite: {exc}") from exc
