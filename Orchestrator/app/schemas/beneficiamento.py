# pylint: disable=all
# mypy: ignore-errors
"""Schemas Pydantic da API de Beneficiamento."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BeneficiamentoSourceFiles(BaseModel):
    analytics: Optional[str] = None
    profile: Optional[str] = None


class BeneficiamentoPeriodPayload(BaseModel):
    key: str
    label: str
    available: bool = False
    status: str = "missing"
    updated_at: Optional[str] = None
    age_seconds: Optional[int] = None
    stale: bool = False
    source_files: BeneficiamentoSourceFiles = Field(
        default_factory=BeneficiamentoSourceFiles
    )
    metrics: Dict[str, Any] = Field(default_factory=dict)
    quality: Dict[str, Any] = Field(default_factory=dict)
    profile: Dict[str, Any] = Field(default_factory=dict)
    rankings: Dict[str, Any] = Field(default_factory=dict)
    highlights: Dict[str, Any] = Field(default_factory=dict)
    oracle: Dict[str, Any] = Field(default_factory=dict)
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class BeneficiamentoHealthPeriod(BaseModel):
    period: str
    status: str
    available: bool
    stale: bool = False
    updated_at: Optional[str] = None
    age_seconds: Optional[int] = None
    oracle_elapsed_seconds: Optional[float] = None
    oracle_timeout_ms: Optional[int] = None
    oracle_timeout_applied: Optional[bool] = None
    source_files: BeneficiamentoSourceFiles = Field(
        default_factory=BeneficiamentoSourceFiles
    )


class BeneficiamentoHealthResponse(BaseModel):
    generated_at: str
    snapshot_root: str
    status: str
    periods_total: int
    periods_loaded: int
    findings: List[str] = Field(default_factory=list)
    periods: List[BeneficiamentoHealthPeriod] = Field(default_factory=list)


class BeneficiamentoPeriodsResponse(BaseModel):
    generated_at: str
    default_period: str
    periods: List[BeneficiamentoPeriodPayload] = Field(default_factory=list)


class BeneficiamentoDashboardPayload(BaseModel):
    generated_at: str
    default_period: str
    overall: Dict[str, Any]
    comparison: List[Dict[str, Any]] = Field(default_factory=list)
    periods: Dict[str, BeneficiamentoPeriodPayload] = Field(default_factory=dict)
    health: BeneficiamentoHealthResponse


class BeneficiamentoHistoricoResponse(BaseModel):
    total_records: int
    records: List[Dict[str, Any]] = Field(default_factory=list)


class BeneficiamentoAnalyticsGeral(BaseModel):
    ob_distintas: int
    total_fases: int
    maquinas_distintas: int
    total_operadores: int
    kg_total: float
    mt_total: float
    min_real_total: float
    min_prev_total: float
    desvio_min_total: float
    efic_tempo_media: float
    taxa_reprocesso: float
    produtividade_kgh: float


class BeneficiamentoAnalyticsOperador(BaseModel):
    operador: str
    kg_total: float
    mt_total: float
    total_fases: int
    efic_tempo: float


class BeneficiamentoAnalyticsMaquina(BaseModel):
    maquina: str
    kg_total: float
    mt_total: float
    total_fases: int
    min_real: float
    min_setup: float
    min_processo: float


class BeneficiamentoAnalyticsProduto(BaseModel):
    reduz: str
    produto: str
    artigo: str
    kg_total: float
    mt_total: float
    taxa_reprocesso: float
    produtividade_kgh: float


class BeneficiamentoAnalyticsTurno(BaseModel):
    turno: str
    kg_total: float


class BeneficiamentoAnalyticsResponse(BaseModel):
    geral: BeneficiamentoAnalyticsGeral
    operadores: List[BeneficiamentoAnalyticsOperador] = Field(default_factory=list)
    maquinas: List[BeneficiamentoAnalyticsMaquina] = Field(default_factory=list)
    produtos: List[BeneficiamentoAnalyticsProduto] = Field(default_factory=list)
    turnos: List[BeneficiamentoAnalyticsTurno] = Field(default_factory=list)

