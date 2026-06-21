# pylint: disable=all
# mypy: ignore-errors
"""Schemas Pydantic da API de Beneficiamento."""

from typing import Any

from pydantic import BaseModel, Field


class BeneficiamentoSourceFiles(BaseModel):
    analytics: str | None = None
    profile: str | None = None


class BeneficiamentoHealthIssue(BaseModel):
    code: str
    severity: str = "warn"
    period: str | None = None
    label: str | None = None
    message: str
    action_hint: str | None = None


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
    updated_at: str | None = None
    age_seconds: int | None = None


class BeneficiamentoPeriodPayload(BaseModel):
    key: str
    label: str
    available: bool = False
    status: str = "missing"
    updated_at: str | None = None
    age_seconds: int | None = None
    stale: bool = False
    source: str = "snapshot_local"
    snapshot_state: str = "missing"
    reason_code: str = "snapshot_missing"
    reason_message: str | None = None
    recommended_action: str | None = None
    refresh_status: str | None = None
    historico_write_status: str | None = None
    quality_status: str | None = None
    issues: list[BeneficiamentoHealthIssue] = Field(default_factory=list)
    source_files: BeneficiamentoSourceFiles = Field(
        default_factory=BeneficiamentoSourceFiles
    )
    metrics: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    rankings: dict[str, Any] = Field(default_factory=dict)
    highlights: dict[str, Any] = Field(default_factory=dict)
    oracle: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)


class BeneficiamentoHealthPeriod(BaseModel):
    period: str
    status: str
    available: bool
    stale: bool = False
    updated_at: str | None = None
    age_seconds: int | None = None
    source: str = "snapshot_local"
    snapshot_state: str = "missing"
    reason_code: str = "snapshot_missing"
    reason_message: str | None = None
    recommended_action: str | None = None
    refresh_status: str | None = None
    historico_write_status: str | None = None
    quality_status: str | None = None
    oracle_elapsed_seconds: float | None = None
    oracle_timeout_ms: int | None = None
    oracle_timeout_applied: bool | None = None
    issues: list[BeneficiamentoHealthIssue] = Field(default_factory=list)
    source_files: BeneficiamentoSourceFiles = Field(
        default_factory=BeneficiamentoSourceFiles
    )


class BeneficiamentoHealthResponse(BaseModel):
    generated_at: str
    snapshot_root: str
    source: str = "snapshot_local"
    status: str
    reason_code: str = "healthy"
    recommended_action: str | None = None
    periods_total: int
    periods_loaded: int
    findings: list[str] = Field(default_factory=list)
    issues: list[BeneficiamentoHealthIssue] = Field(default_factory=list)
    summary: BeneficiamentoHealthSummary = Field(
        default_factory=BeneficiamentoHealthSummary
    )
    latest_period: BeneficiamentoLatestPeriod | None = None
    snapshot_files: dict[str, BeneficiamentoSourceFiles] = Field(default_factory=dict)
    periods: list[BeneficiamentoHealthPeriod] = Field(default_factory=list)


class BeneficiamentoPeriodsResponse(BaseModel):
    generated_at: str
    default_period: str
    periods: list[BeneficiamentoPeriodPayload] = Field(default_factory=list)


class BeneficiamentoDashboardPayload(BaseModel):
    generated_at: str
    default_period: str
    overall: dict[str, Any]
    comparison: list[dict[str, Any]] = Field(default_factory=list)
    periods: dict[str, BeneficiamentoPeriodPayload] = Field(default_factory=dict)
    health: BeneficiamentoHealthResponse


class BeneficiamentoHistoricoResponse(BaseModel):
    total_records: int
    records: list[dict[str, Any]] = Field(default_factory=list)


class BeneficiamentoOverviewResponse(BaseModel):
    generated_at: str
    filters: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    kpis: dict[str, Any] = Field(default_factory=dict)
    rankings: dict[str, Any] = Field(default_factory=dict)
    series: dict[str, Any] = Field(default_factory=dict)
    filter_options: dict[str, Any] = Field(default_factory=dict)
    turnos: list[dict[str, Any]] = Field(default_factory=list)
    tingimento: dict[str, Any] = Field(default_factory=dict)
    interaction: dict[str, Any] = Field(default_factory=dict)


class BeneficiamentoDetailResponse(BaseModel):
    generated_at: str
    filters: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    pagination: dict[str, Any] = Field(default_factory=dict)
    raw_records: list[dict[str, Any]] = Field(default_factory=list)


class BeneficiamentoRefreshResponse(BaseModel):
    status: str
    period: str
    refresh_status: str | None = None
    detail: str | None = None
