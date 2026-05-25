# pylint: disable=all
# mypy: ignore-errors
"""
Módulo contendo schemas Pydantic de Execuções.
"""

from typing import Any, Optional
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
    queue_group: Optional[str] = None
    failure_reason: Optional[str] = None
    recovery_action: Optional[str] = None
    exit_code: Optional[int] = None
    requested_by: Optional[str] = "SYSTEM"
    started_at: Any
    claimed_at: Optional[Any] = None
    worker_instance_id: Optional[str] = None
    worker_pid: Optional[int] = None
    finished_at: Optional[Any] = None
    duration_seconds: Optional[float] = None

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
    logs: Optional[str] = None
    artifacts: Optional[str] = None
    automation_name: Optional[str] = None
    operator_attention_required: bool = False
    operator_severity: Optional[str] = None
    operator_score: int = 0
    operator_reason_summary: Optional[str] = None
    operator_action_code: Optional[str] = None
    operator_action_label: Optional[str] = None
    operator_action_hint: Optional[str] = None
    requeue_allowed: bool = False
    requeue_block_reason: Optional[str] = None
    stop_allowed: bool = False
    related_execution_id: Optional[str] = None
    related_execution_status: Optional[str] = None
    related_queue_group: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ExecutionSummary(BaseModel):
    id: str
    automation_id: int
    automation_name: Optional[str] = None
    status: str
    priority: str = "NORMAL"
    retry_count: int = 0
    max_retries: int = 0
    queue_group: Optional[str] = None
    failure_reason: Optional[str] = None
    recovery_action: Optional[str] = None
    exit_code: Optional[int] = None
    requested_by: Optional[str] = None
    started_at: Any
    finished_at: Optional[Any] = None
    duration_seconds: Optional[float] = None
    artifacts: Optional[str] = None
    operator_attention_required: bool = False
    operator_severity: Optional[str] = None
    operator_score: int = 0
    operator_reason_summary: Optional[str] = None
    operator_action_code: Optional[str] = None
    operator_action_label: Optional[str] = None
    operator_action_hint: Optional[str] = None
    requeue_allowed: bool = False
    requeue_block_reason: Optional[str] = None
    stop_allowed: bool = False
    related_execution_id: Optional[str] = None
    related_execution_status: Optional[str] = None
    related_queue_group: Optional[str] = None
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
    exit_code: Optional[int] = None
    logs: Optional[str] = None
    artifacts: Optional[str] = None


class ExecutionQueueActionRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=200)
    requested_by: Optional[str] = Field(None, max_length=100)
    priority: Optional[str] = None

    @field_validator("priority")
    @classmethod
    def v_priority(cls, v: Optional[str]) -> Optional[str]:
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
