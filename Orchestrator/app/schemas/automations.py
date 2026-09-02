"""
Módulo contendo schemas Pydantic de Automações.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import (
    _validate_safe_name,
    _validate_schedule,
    _validate_schedule_tolerant,
    _validate_script_path,
    format_dt_br,
)
from .executions import ExecutionSummary


def _normalize_queue_group(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_notification_channels(value: str | None) -> str | None:
    if value is None:
        return None
    allowed_order = ["email", "whatsapp"]
    seen: list[str] = []
    for raw in value.split(","):
        channel = raw.strip().lower()
        if not channel:
            continue
        if channel not in allowed_order:
            raise ValueError("notification_channels aceita apenas: email, whatsapp.")
        if channel not in seen:
            seen.append(channel)
    if not seen:
        return None
    return ",".join([channel for channel in allowed_order if channel in seen])


class AutomationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    script_path: str = Field(..., min_length=3, max_length=500)
    schedule: str | None = None
    max_runtime_minutes: int = Field(30, ge=1, le=480)
    max_retries: int = Field(0, ge=0, le=10)
    cooldown_minutes: int = Field(0, ge=0, le=1440)
    queue_group: str | None = Field(None, max_length=100)
    sla_minutes: int | None = Field(
        None,
        ge=1,
        le=10080,
        description="SLA de recuperação em minutos (1 minuto a 7 dias).",
    )
    enabled: bool = True
    test_mode: bool = False
    notification_channels: str | None = None

    @field_validator("name")
    @classmethod
    def v_name(cls, v: str) -> str:
        return _validate_safe_name(v)

    @field_validator("script_path")
    @classmethod
    def v_path(cls, v: str) -> str:
        return _validate_script_path(v)

    @field_validator("schedule")
    @classmethod
    def v_sched(cls, v: str | None) -> str | None:
        return _validate_schedule(v)

    @field_validator("queue_group")
    @classmethod
    def v_queue_group(cls, v: str | None) -> str | None:
        return _normalize_queue_group(v)

    @field_validator("notification_channels")
    @classmethod
    def v_notification_channels(cls, v: str | None) -> str | None:
        return _normalize_notification_channels(v)


class AutomationCreate(AutomationBase):
    pass


class AutomationPreflightRequest(AutomationBase):
    pass


class AutomationPreflightIssue(BaseModel):
    code: str
    message: str
    severity: str = "WARN"


class AutomationPreflightGovernance(BaseModel):
    manifest_present: bool = False
    manifest_path: str | None = None
    catalog_id: str | None = None
    status: str = "healthy"
    top_issue: str | None = None
    recommended_action: str | None = None
    blocking_issues: list[AutomationPreflightIssue] = []
    warnings: list[AutomationPreflightIssue] = []


class TestModeRequest(BaseModel):
    """Corpo de POST .../test-mode e .../test-mode/global — antes `enabled`
    viajava como query param cru, único caso de mutação da API sem corpo
    Pydantic tipado (achado #20)."""

    enabled: bool


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    script_path: str | None = None
    schedule: str | None = None
    max_runtime_minutes: int | None = None
    max_retries: int | None = None
    cooldown_minutes: int | None = None
    queue_group: str | None = None
    sla_minutes: int | None = None
    enabled: bool | None = None
    test_mode: bool | None = None
    notification_channels: str | None = None

    @field_validator("script_path")
    @classmethod
    def v_path(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_script_path(v)

    @field_validator("schedule")
    @classmethod
    def v_sched(cls, v: str | None) -> str | None:
        return _validate_schedule(v)

    @field_validator("max_retries")
    @classmethod
    def v_max_retries(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 0 or v > 10:
            raise ValueError("max_retries deve estar entre 0 e 10.")
        return v

    @field_validator("cooldown_minutes")
    @classmethod
    def v_cooldown_minutes(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 0 or v > 1440:
            raise ValueError("cooldown_minutes deve estar entre 0 e 1440.")
        return v

    @field_validator("queue_group")
    @classmethod
    def v_queue_group(cls, v: str | None) -> str | None:
        return _normalize_queue_group(v)

    @field_validator("notification_channels")
    @classmethod
    def v_notification_channels(cls, v: str | None) -> str | None:
        return _normalize_notification_channels(v)


class AutomationPreflightResponse(BaseModel):
    valid: bool = True
    validated: bool = True
    normalized_payload: dict[str, Any]
    resolved_script_path: str
    automation_dir: str
    normalized_notification_channels: str | None = None
    schedule_summary: str
    next_runs_preview: list[str] = []
    warnings: list[str] = []
    governance: AutomationPreflightGovernance = Field(
        default_factory=AutomationPreflightGovernance
    )


class AutomationResponse(AutomationBase):
    id: int
    created_at: Any
    updated_at: Any | None = None
    next_run: str | None = None
    last_status: str | None = None
    last_execution_id: str | None = None
    last_execution_started_at: Any | None = None
    last_execution_finished_at: Any | None = None
    last_execution_duration_seconds: float | None = None
    last_failure_reason: str | None = None
    last_recovery_action: str | None = None
    last_requested_by: str | None = None
    schedule_type: str | None = None
    schedule_summary: str | None = None
    next_runs_preview: list[str] = []
    active_execution_count: int = 0
    success_24h: int = 0
    failures_24h: int = 0
    timeouts_24h: int = 0
    error_24h: int = 0
    # Já calculado em metrics_queries.get_automation_metrics_24h (AVG SQL) e
    # descartado antes desta linha — expõe sem custo adicional de query.
    avg_duration_24h_seconds: float | None = None
    pending_count: int = 0
    operational_state: str = "idle"
    validated: bool = True
    backup_path: str | None = None
    audit_id: int | None = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("schedule")
    @classmethod
    def v_sched(cls, v: str | None) -> str | None:
        return _validate_schedule_tolerant(v)

    @model_validator(mode="after")
    def apply_br_format(self) -> "AutomationResponse":
        self.created_at = format_dt_br(self.created_at)
        self.updated_at = format_dt_br(self.updated_at)
        self.last_execution_started_at = format_dt_br(self.last_execution_started_at)
        self.last_execution_finished_at = format_dt_br(self.last_execution_finished_at)
        self.error_24h = self.failures_24h
        return self


class AutomationOverviewMetrics24h(BaseModel):
    success_count: int = 0
    error_count: int = 0
    pending_count: int = 0


class AutomationOverviewResponse(BaseModel):
    automation: AutomationResponse
    metrics_24h: AutomationOverviewMetrics24h
    recent_executions: list[ExecutionSummary] = []
