# pylint: disable=all
# mypy: ignore-errors
"""
Módulo contendo schemas Pydantic de Automações.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import (
    _validate_safe_name,
    _validate_script_path,
    _validate_schedule,
    _validate_schedule_tolerant,
    format_dt_br,
)


class AutomationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    script_path: str = Field(..., min_length=3, max_length=500)
    schedule: Optional[str] = None
    max_runtime_minutes: int = Field(30, ge=1, le=480)
    max_retries: int = Field(0, ge=0, le=10)
    cooldown_minutes: int = Field(0, ge=0, le=1440)
    queue_group: Optional[str] = Field(None, max_length=100)
    sla_minutes: Optional[int] = Field(None, ge=1, le=10080, description="SLA de recuperação em minutos (1 minuto a 7 dias).")
    enabled: bool = True
    test_mode: bool = False
    notification_channels: Optional[str] = None

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
    def v_sched(cls, v: Optional[str]) -> Optional[str]:
        return _validate_schedule(v)


class AutomationCreate(AutomationBase):
    pass


class AutomationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    script_path: Optional[str] = None
    schedule: Optional[str] = None
    max_runtime_minutes: Optional[int] = None
    max_retries: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    queue_group: Optional[str] = None
    sla_minutes: Optional[int] = None
    enabled: Optional[bool] = None
    test_mode: Optional[bool] = None
    notification_channels: Optional[str] = None

    @field_validator("script_path")
    @classmethod
    def v_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_script_path(v)

    @field_validator("schedule")
    @classmethod
    def v_sched(cls, v: Optional[str]) -> Optional[str]:
        return _validate_schedule(v)

    @field_validator("max_retries")
    @classmethod
    def v_max_retries(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v < 0 or v > 10:
            raise ValueError("max_retries deve estar entre 0 e 10.")
        return v

    @field_validator("cooldown_minutes")
    @classmethod
    def v_cooldown_minutes(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v < 0 or v > 1440:
            raise ValueError("cooldown_minutes deve estar entre 0 e 1440.")
        return v


class AutomationResponse(AutomationBase):
    id: int
    created_at: Any
    updated_at: Optional[Any] = None
    next_run: Optional[str] = None
    last_status: Optional[str] = None
    last_execution_id: Optional[str] = None
    last_execution_started_at: Optional[Any] = None
    last_execution_finished_at: Optional[Any] = None
    last_execution_duration_seconds: Optional[float] = None
    last_failure_reason: Optional[str] = None
    last_recovery_action: Optional[str] = None
    last_requested_by: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_summary: Optional[str] = None
    next_runs_preview: List[str] = []
    active_execution_count: int = 0
    success_24h: int = 0
    failures_24h: int = 0
    timeouts_24h: int = 0
    error_24h: int = 0
    pending_count: int = 0
    operational_state: str = "idle"
    model_config = ConfigDict(from_attributes=True)

    @field_validator("schedule")
    @classmethod
    def v_sched(cls, v: Optional[str]) -> Optional[str]:
        return _validate_schedule_tolerant(v)

    @model_validator(mode="after")
    def apply_br_format(self) -> "AutomationResponse":
        self.created_at = format_dt_br(self.created_at)
        self.updated_at = format_dt_br(self.updated_at)
        self.last_execution_started_at = format_dt_br(self.last_execution_started_at)
        self.last_execution_finished_at = format_dt_br(self.last_execution_finished_at)
        self.error_24h = self.failures_24h
        return self
