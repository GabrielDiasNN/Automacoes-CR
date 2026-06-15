# pylint: disable=all
# mypy: ignore-errors
"""Schemas Pydantic da API de Beneficiamento."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BeneficiamentoSourceFiles(BaseModel):
    analytics: Optional[str] = None
    profile: Optional[str] = None


class BeneficiamentoHealthIssue(BaseModel):
    code: str
    severity: str = "warn"
    period: Optional[str] = None
    label: Optional[str] = None
    message: str
    action_hint: Optional[str] = None


class BeneficiamentoHealthSummary(BaseModel):
    available_periods: int = 0
    healthy_periods: int = 0
    attention_periods: int = 0
    missing_periods: int = 0
    no_data_periods: int = 0
    stale_periods: int = 0
    invalid_periods: int = 0
    timeout_unapplied_periods: int = 0
    partial_failure_periods: int = 0


class BeneficiamentoLatestPeriod(BaseModel):
    period: str
    label: str
    status: str
    updated_at: Optional[str] = None
    age_seconds: Optional[int] = None


class BeneficiamentoPeriodPayload(BaseModel):
    key: str
    label: str
    available: bool = False
    status: str = "missing"
    updated_at: Optional[str] = None
    age_seconds: Optional[int] = None
    stale: bool = False
    source: str = "snapshot_local"
    snapshot_state: str = "missing"
    reason_code: str = "snapshot_missing"
    reason_message: Optional[str] = None
    recommended_action: Optional[str] = None
    refresh_status: Optional[str] = None
    historico_write_status: Optional[str] = None
    quality_status: Optional[str] = None
    issues: List[BeneficiamentoHealthIssue] = Field(default_factory=list)
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
    source: str = "snapshot_local"
    snapshot_state: str = "missing"
    reason_code: str = "snapshot_missing"
    reason_message: Optional[str] = None
    recommended_action: Optional[str] = None
    refresh_status: Optional[str] = None
    historico_write_status: Optional[str] = None
    quality_status: Optional[str] = None
    oracle_elapsed_seconds: Optional[float] = None
    oracle_timeout_ms: Optional[int] = None
    oracle_timeout_applied: Optional[bool] = None
    issues: List[BeneficiamentoHealthIssue] = Field(default_factory=list)
    source_files: BeneficiamentoSourceFiles = Field(
        default_factory=BeneficiamentoSourceFiles
    )


class BeneficiamentoHealthResponse(BaseModel):
    generated_at: str
    snapshot_root: str
    source: str = "snapshot_local"
    status: str
    reason_code: str = "healthy"
    recommended_action: Optional[str] = None
    periods_total: int
    periods_loaded: int
    findings: List[str] = Field(default_factory=list)
    issues: List[BeneficiamentoHealthIssue] = Field(default_factory=list)
    summary: BeneficiamentoHealthSummary = Field(
        default_factory=BeneficiamentoHealthSummary
    )
    latest_period: Optional[BeneficiamentoLatestPeriod] = None
    snapshot_files: Dict[str, BeneficiamentoSourceFiles] = Field(default_factory=dict)
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


class BeneficiamentoOverviewResponse(BaseModel):
    generated_at: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    health: Dict[str, Any] = Field(default_factory=dict)
    kpis: Dict[str, Any] = Field(default_factory=dict)
    rankings: Dict[str, Any] = Field(default_factory=dict)
    series: Dict[str, Any] = Field(default_factory=dict)
    filter_options: Dict[str, Any] = Field(default_factory=dict)
    turnos: List[Dict[str, Any]] = Field(default_factory=list)
    tingimento: Dict[str, Any] = Field(default_factory=dict)
    interaction: Dict[str, Any] = Field(default_factory=dict)


class BeneficiamentoDetailResponse(BaseModel):
    generated_at: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    target: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    records: List[Dict[str, Any]] = Field(default_factory=list)
    trace: List[Dict[str, Any]] = Field(default_factory=list)
    pagination: Dict[str, Any] = Field(default_factory=dict)
    raw_records: List[Dict[str, Any]] = Field(default_factory=list)


class BeneficiamentoRefreshResponse(BaseModel):
    status: str
    period: str
    refresh_status: Optional[str] = None
    detail: Optional[str] = None
