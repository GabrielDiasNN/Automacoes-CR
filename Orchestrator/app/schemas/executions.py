# pylint: disable=all
# mypy: ignore-errors
"""
Módulo contendo schemas Pydantic de Execuções.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import EXECUTION_ALLOWED_PRIORITIES, EXECUTION_ALLOWED_STATUSES
from .common import format_dt_br


class ExecutionBase(BaseModel):
    id: str
    automation_id: int
    status: str
    priority: str = "NORMAL"
    retry_count: int = 0
    max_retries: int = 0
    queue_group: str | None = None
    failure_reason: str | None = None
    recovery_action: str | None = None
    exit_code: int | None = None
    requested_by: str | None = "SYSTEM"
    started_at: Any
    claimed_at: Any | None = None
    worker_instance_id: str | None = None
    worker_pid: int | None = None
    finished_at: Any | None = None
    duration_seconds: float | None = None

    @field_validator("status")
    @classmethod
    def v_exec_status(cls, v: str) -> str:
        value = v.upper()
        if value not in EXECUTION_ALLOWED_STATUSES:
            raise ValueError("Status de execução inválido.")
        return value

    @field_validator("priority")
    @classmethod
    def v_exec_priority(cls, v: str) -> str:
        value = v.upper()
        if value not in EXECUTION_ALLOWED_PRIORITIES:
            raise ValueError("Prioridade inválida.")
        return value

    @model_validator(mode="after")
    def apply_br_format(self) -> "ExecutionBase":
        self.started_at = format_dt_br(self.started_at)
        self.claimed_at = format_dt_br(self.claimed_at)
        self.finished_at = format_dt_br(self.finished_at)
        return self


class ExecutionResponse(ExecutionBase):
    logs: str | None = None
    artifacts: str | None = None
    automation_name: str | None = None
    operator_attention_required: bool = False
    operator_severity: str | None = None
    operator_score: int = 0
    operator_reason_summary: str | None = None
    operator_action_code: str | None = None
    operator_action_label: str | None = None
    operator_action_hint: str | None = None
    requeue_allowed: bool = False
    requeue_block_reason: str | None = None
    stop_allowed: bool = False
    related_execution_id: str | None = None
    related_execution_status: str | None = None
    related_queue_group: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ExecutionSummary(BaseModel):
    id: str
    automation_id: int
    automation_name: str | None = None
    status: str
    priority: str = "NORMAL"
    retry_count: int = 0
    max_retries: int = 0
    queue_group: str | None = None
    failure_reason: str | None = None
    recovery_action: str | None = None
    exit_code: int | None = None
    requested_by: str | None = None
    started_at: Any
    finished_at: Any | None = None
    duration_seconds: float | None = None
    artifacts: str | None = None
    operator_attention_required: bool = False
    operator_severity: str | None = None
    operator_score: int = 0
    operator_reason_summary: str | None = None
    operator_action_code: str | None = None
    operator_action_label: str | None = None
    operator_action_hint: str | None = None
    requeue_allowed: bool = False
    requeue_block_reason: str | None = None
    stop_allowed: bool = False
    related_execution_id: str | None = None
    related_execution_status: str | None = None
    related_queue_group: str | None = None
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def apply_br_format(self) -> "ExecutionSummary":
        self.started_at = format_dt_br(self.started_at)
        self.finished_at = format_dt_br(self.finished_at)
        return self


class ExecutionTelemetryStart(BaseModel):
    automation_name: str


class ExecutionTelemetryEnd(BaseModel):
    status: str
    exit_code: int | None = None
    logs: str | None = None
    artifacts: str | None = None


class ExecutionQueueActionRequest(BaseModel):
    reason: str | None = Field(None, max_length=200)
    requested_by: str | None = Field(None, max_length=100)
    priority: str | None = None

    @field_validator("priority")
    @classmethod
    def v_priority(cls, v: str | None) -> str | None:
        if v is None:
            return v
        value = v.upper()
        if value not in EXECUTION_ALLOWED_PRIORITIES:
            raise ValueError("Prioridade inválida.")
        return value


class ExecutionQueueActionResponse(BaseModel):
    message: str
    source_exec_id: str
    queued_exec_id: str
    automation_id: int
    retry_count: int
    max_retries: int
    recovery_action: str
