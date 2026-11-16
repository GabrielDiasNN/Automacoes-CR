"""Endpoints de PCP e OEE de Beneficiamento baseados no SQLite Histórico."""

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import schemas
from ..middleware import get_api_key
from ..runtime import ensure_beneficiamento_on_path, get_project_root
from ..services.beneficiamento_refresh import run_beneficiamento_refresh

logger = logging.getLogger("orchestrator")

router = APIRouter(prefix="/api/beneficiamento", tags=["Beneficiamento"])


# Parametros de query agrupados em dataclasses usadas via Depends(): mesmos
# nomes, tipos, defaults e validacoes que antes ficavam na assinatura do handler.
@dataclass
class _HistoricoFiltros:
    ob: Annotated[str | None, Query(description="Número da OB (busca parcial)")] = None
    alternativo: Annotated[
        str | None, Query(description="Código Alternativo ou Reduzido do produto")
    ] = None
    dt_inicio: Annotated[
        str | None,
        Query(description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    ] = None
    dt_fim: Annotated[
        str | None,
        Query(description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    ] = None
    ano_sem: Annotated[
        int | None,
        Query(description="Código do Ano + Semana ISO (ex: 202622)"),
    ] = None
    ano_mes: Annotated[
        str | None, Query(description="Código do Ano + Mês (ex: 202605)")
    ] = None
    limit: Annotated[
        int,
        Query(ge=1, le=5000, description="Limite máximo de registros retornados"),
    ] = 500


@dataclass
class _OverviewRecorte:
    dt_inicio: Annotated[
        str | None,
        Query(description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    ] = None
    dt_fim: Annotated[
        str | None,
        Query(description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    ] = None
    maquina: Annotated[str | None, Query(description="Nome da máquina para filtro")] = (
        None
    )
    fase: Annotated[str | None, Query(description="Nome da fase para filtro")] = None
    turno: Annotated[str | None, Query(description="Turno específico para filtro")] = (
        None
    )


@dataclass
class _OverviewClassificacao:
    alternativo: Annotated[
        str | None, Query(description="Código Alternativo principal do produto")
    ] = None
    q: Annotated[
        str | None, Query(description="Busca por OB, produto, artigo, cor ou código")
    ] = None
    setor: Annotated[str | None, Query(description="Setor industrial para filtro")] = (
        None
    )
    grupo_fase: Annotated[
        str | None, Query(description="Grupo de fase para filtro")
    ] = None
    tipo_maquina: Annotated[
        str | None, Query(description="Descrição do tipo de máquina para filtro")
    ] = None
    reprocesso: Annotated[
        str | None,
        Query(
            description="Filtra por reprocesso: '1' só reprocesso, '0' sem reprocesso"
        ),
    ] = None
    status: Annotated[
        str | None,
        Query(description="Filtra por status de execução: 'confirmada' ou 'planejada'"),
    ] = None


@dataclass
class _DetailRecorte:
    target_type: Annotated[
        str,
        Query(
            description=(
                "Tipo do detalhe: produto, maquina_fase, fase, turno, ob, "
                "setor, grupo_fase ou tipo_maquina"
            ),
        ),
    ]
    dt_inicio: Annotated[
        str | None,
        Query(description="Data final inicial (formato YYYY-MM-DD ou ISO)"),
    ] = None
    dt_fim: Annotated[
        str | None,
        Query(description="Data final limite (formato YYYY-MM-DD ou ISO)"),
    ] = None
    maquina: Annotated[str | None, Query(description="Nome da máquina para filtro")] = (
        None
    )
    fase: Annotated[str | None, Query(description="Nome da fase para filtro")] = None
    turno: Annotated[str | None, Query(description="Turno específico para filtro")] = (
        None
    )
    alternativo: Annotated[
        str | None, Query(description="Código Alternativo principal do produto")
    ] = None


@dataclass
class _DetailClassificacao:
    ob: Annotated[str | None, Query(description="Número da OB")] = None
    q: Annotated[
        str | None, Query(description="Busca por OB, produto, artigo, cor ou código")
    ] = None
    setor: Annotated[str | None, Query(description="Setor industrial para filtro")] = (
        None
    )
    grupo_fase: Annotated[
        str | None, Query(description="Grupo de fase para filtro")
    ] = None
    tipo_maquina: Annotated[
        str | None, Query(description="Descrição do tipo de máquina para filtro")
    ] = None
    reprocesso: Annotated[
        str | None,
        Query(
            description="Filtra por reprocesso: '1' só reprocesso, '0' sem reprocesso"
        ),
    ] = None
    status: Annotated[
        str | None,
        Query(description="Filtra por status de execução: 'confirmada' ou 'planejada'"),
    ] = None


@dataclass
class _DetailPaginacao:
    page: Annotated[int, Query(ge=1, description="Página do detalhe")] = 1
    limit: Annotated[
        int, Query(ge=1, le=200, description="Limite máximo por página")
    ] = 50
    include_raw: Annotated[
        bool, Query(description="Quando verdadeiro, devolve também o payload bruto")
    ] = False


PROJECT_ROOT = get_project_root()

# Acoplamento com o domínio Beneficiamento centralizado no runtime (achado A3).
ensure_beneficiamento_on_path()

try:
    from beneficiamento.contracts import (
        obter_detail_historico,
        obter_overview_historico,
        obter_tingimento_historico,
    )
    from beneficiamento.data import buscar_historico, buscar_produtos
    from beneficiamento.snapshot_dashboard import (
        build_dashboard_payload,
        build_health_payload,
        build_periods_payload,
        load_period_payload,
    )
except ImportError:
    # Loga a causa real: um bug de import em módulo transitivo colapsaria na mesma
    # mensagem genérica "Módulo indisponível", escondendo o diagnóstico (#30).
    logger.exception(
        "Módulos do beneficiamento indisponíveis; endpoints entram em modo degradado."
    )
    buscar_historico = None
    buscar_produtos = None
    obter_detail_historico = None
    obter_overview_historico = None
    obter_tingimento_historico = None
    build_dashboard_payload = None
    build_health_payload = None
    build_periods_payload = None
    load_period_payload = None


def _ensure_snapshot_dashboard() -> None:
    if (
        build_dashboard_payload is None
        or build_health_payload is None
        or build_periods_payload is None
        or load_period_payload is None
    ):
        raise HTTPException(
            status_code=500,
            detail="Módulo de snapshots do beneficiamento indisponível.",
        )


@router.get("/historico", response_model=schemas.BeneficiamentoHistoricoResponse)
def get_beneficiamento_historico(
    filtros_query: Annotated[_HistoricoFiltros, Depends()],
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoHistoricoResponse:
    """Realiza buscas rápidas no SQLite indexado local para rastreabilidade de OBs e produtos."""

    if buscar_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    filtros = {
        "ob": filtros_query.ob,
        "alternativo": filtros_query.alternativo,
        "dt_inicio": filtros_query.dt_inicio,
        "dt_fim": filtros_query.dt_fim,
        "ano_sem": filtros_query.ano_sem,
        "ano_mes": filtros_query.ano_mes,
    }

    try:
        records = buscar_historico(filtros, limit=filtros_query.limit)
        return schemas.BeneficiamentoHistoricoResponse(
            total_records=len(records), records=records
        )
    except Exception as exc:
        logger.error("Erro na busca de histórico SQLite: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno na busca de histórico."
        ) from exc


@router.get("/produtos", response_model=schemas.BeneficiamentoProdutosResponse)
def get_beneficiamento_produtos(
    q: str = Query(
        ..., min_length=2, description="Termo de busca (código ou nome do produto)"
    ),
    limit: int = Query(20, ge=1, le=50, description="Limite máximo de sugestões"),
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoProdutosResponse:
    """Autocomplete de produto para a busca dinâmica no Dashboard."""

    if buscar_produtos is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    try:
        items = buscar_produtos(q, limit=limit)
        return schemas.BeneficiamentoProdutosResponse(items=items)
    except Exception as exc:
        logger.error("Erro na busca de produtos: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno na busca de produtos."
        ) from exc


@router.get("/overview", response_model=schemas.BeneficiamentoOverviewResponse)
def get_beneficiamento_overview(
    recorte: Annotated[_OverviewRecorte, Depends()],
    classificacao: Annotated[_OverviewClassificacao, Depends()],
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoOverviewResponse:
    """Retorna o contrato operacional V1 do Beneficiamento a partir do SQLite local."""

    if obter_overview_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    filtros = {
        "dt_inicio": recorte.dt_inicio,
        "dt_fim": recorte.dt_fim,
        "maquina": recorte.maquina,
        "fase": recorte.fase,
        "turno": recorte.turno,
        "alternativo": classificacao.alternativo,
        "q": classificacao.q,
        "setor": classificacao.setor,
        "grupo_fase": classificacao.grupo_fase,
        "tipo_maquina": classificacao.tipo_maquina,
        "reprocesso": classificacao.reprocesso,
        "status": classificacao.status,
    }

    try:
        data = obter_overview_historico(filtros)
        return schemas.BeneficiamentoOverviewResponse.model_validate(data)
    except Exception as exc:
        logger.error("Erro no overview de beneficiamento: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno no overview de beneficiamento."
        ) from exc


@router.get("/tingimento", response_model=schemas.BeneficiamentoTingimentoResponse)
def get_beneficiamento_tingimento(
    dt_inicio: str | None = Query(
        None, description="Data final inicial (formato YYYY-MM-DD ou ISO)"
    ),
    dt_fim: str | None = Query(
        None, description="Data final limite (formato YYYY-MM-DD ou ISO)"
    ),
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoTingimentoResponse:
    """Painel dedicado de Tingimento (escopo fixo CODIGO_FASE=40), independente
    dos filtros gerais do overview."""

    if obter_tingimento_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    try:
        data = obter_tingimento_historico({"dt_inicio": dt_inicio, "dt_fim": dt_fim})
        return schemas.BeneficiamentoTingimentoResponse.model_validate(data)
    except Exception as exc:
        logger.error("Erro no painel de tingimento: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno no painel de tingimento."
        ) from exc


@router.get("/health", response_model=schemas.BeneficiamentoHealthResponse)
def get_beneficiamento_health(
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoHealthResponse:
    """Expõe a saúde operacional dos snapshots locais do Beneficiamento."""

    _ensure_snapshot_dashboard()

    try:
        data = build_health_payload()
        return schemas.BeneficiamentoHealthResponse.model_validate(data)
    except Exception as exc:
        logger.error("Erro na saúde dos snapshots: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno na saúde dos snapshots."
        ) from exc


@router.get("/periods", response_model=schemas.BeneficiamentoPeriodsResponse)
def get_beneficiamento_periods(
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoPeriodsResponse:
    """Lista os períodos disponíveis e seus metadados de snapshot."""

    _ensure_snapshot_dashboard()

    try:
        data = build_periods_payload()
        return schemas.BeneficiamentoPeriodsResponse.model_validate(data)
    except Exception as exc:
        logger.error("Erro ao listar períodos de snapshot: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno ao listar períodos."
        ) from exc


@router.get("/periods/{period}", response_model=schemas.BeneficiamentoPeriodPayload)
def get_beneficiamento_period(
    period: str,
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoPeriodPayload:
    """Retorna o snapshot consolidado de um período do Beneficiamento."""

    _ensure_snapshot_dashboard()

    try:
        data = load_period_payload(period)
        return schemas.BeneficiamentoPeriodPayload.model_validate(data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Erro ao carregar período de snapshot: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno ao carregar o período."
        ) from exc


@router.get("/dashboard", response_model=schemas.BeneficiamentoDashboardPayload)
def get_beneficiamento_dashboard(
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoDashboardPayload:
    """Agrega períodos, saúde e comparação para a home analítica da aba."""

    _ensure_snapshot_dashboard()

    try:
        data = build_dashboard_payload()
        return schemas.BeneficiamentoDashboardPayload.model_validate(data)
    except Exception as exc:
        logger.error("Erro no dashboard de snapshots: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno no dashboard de snapshots."
        ) from exc


@router.get("/detail", response_model=schemas.BeneficiamentoDetailResponse)
def get_beneficiamento_detail(
    recorte: Annotated[_DetailRecorte, Depends()],
    classificacao: Annotated[_DetailClassificacao, Depends()],
    paginacao: Annotated[_DetailPaginacao, Depends()],
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoDetailResponse:
    """Retorna o drill-down operacional do Beneficiamento a partir do SQLite local."""

    if obter_detail_historico is None:
        raise HTTPException(
            status_code=500,
            detail="Módulo de persistência histórica do beneficiamento indisponível.",
        )

    filtros = {
        "target_type": recorte.target_type,
        "dt_inicio": recorte.dt_inicio,
        "dt_fim": recorte.dt_fim,
        "maquina": recorte.maquina,
        "fase": recorte.fase,
        "turno": recorte.turno,
        "alternativo": recorte.alternativo,
        "ob": classificacao.ob,
        "q": classificacao.q,
        "setor": classificacao.setor,
        "grupo_fase": classificacao.grupo_fase,
        "tipo_maquina": classificacao.tipo_maquina,
        "reprocesso": classificacao.reprocesso,
        "status": classificacao.status,
        "page": paginacao.page,
        "limit": paginacao.limit,
        "include_raw": paginacao.include_raw,
    }

    try:
        data = obter_detail_historico(filtros)
        return schemas.BeneficiamentoDetailResponse.model_validate(data)
    except Exception as exc:
        logger.error("Erro no detalhe de beneficiamento: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Erro interno na consulta de detalhe."
        ) from exc


@router.post("/refresh", response_model=schemas.BeneficiamentoRefreshResponse)
def post_beneficiamento_refresh(
    period: str = Query(
        "diario", description="Período a atualizar ao vivo: diario ou mensal"
    ),
    _api_key: str = Depends(get_api_key),
) -> schemas.BeneficiamentoRefreshResponse:
    """Dispara um refresh on-demand ("Atualizar agora") do período informado.

    Executa o runner em subprocesso isolado (Oracle nunca é aberto no processo web),
    preservando o guardrail de que GETs do Dashboard só leem SQLite/snapshots.
    """
    if period not in ("diario", "mensal"):
        raise HTTPException(
            status_code=400, detail="Período inválido. Use 'diario' ou 'mensal'."
        )

    result = run_beneficiamento_refresh(period)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=500,
            detail=result.get("detail")
            or "Falha ao executar refresh do beneficiamento.",
        )
    return schemas.BeneficiamentoRefreshResponse.model_validate(result)
