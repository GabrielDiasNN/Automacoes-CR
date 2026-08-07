"""
Módulo contendo schemas Pydantic de Execuções.
"""

import json
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


class ExecutionOperatorFields(BaseModel):
    """Decoração operacional (attention score, ações de fila, execução relacionada).

    Idêntica em `ExecutionResponse` e `ExecutionSummary` — ambas expõem a
    mesma view de operador, só variando os campos "brutos" da execução em
    volta dela. Extraída para as duas herdarem em vez de declarar duas
    cópias independentes que podiam divergir silenciosamente.
    """

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


class ExecutionResponse(ExecutionBase, ExecutionOperatorFields):
    logs: str | None = None
    artifacts: str | None = None
    automation_name: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ExecutionSummary(ExecutionOperatorFields):
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

    @field_validator("artifacts")
    @classmethod
    def v_artifacts(cls, v: str | None) -> str | None:
        """Grava direto em `Execution.artifacts` (ver models.py), lido depois
        por GET /executions/{exec_id}/artifacts com response_model=list[str].
        Sem essa checagem aqui, telemetria externa malformada (dict, lista com
        não-string) entrava no banco sem erro e só quebrava — com 500 — na
        leitura, quando o FastAPI falhasse a validação do response_model.
        Rejeitar na escrita devolve 422 imediato e evita o dado inválido."""
        if v is None:
            return v
        try:
            parsed = json.loads(v)
        except (ValueError, TypeError) as exc:
            raise ValueError("artifacts deve ser um JSON válido.") from exc
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise ValueError("artifacts deve ser uma lista JSON de strings.")
        return v


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


class ExecutionLogsResponse(BaseModel):
    exec_id: str
    total_lines: int
    offset: int
    limit: int
    lines: list[str]


class ExecutionArtifactsResponse(BaseModel):
    exec_id: str
    artifacts: list[str] = []
