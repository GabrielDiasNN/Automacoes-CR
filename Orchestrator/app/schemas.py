# pylint: disable=all
# mypy: ignore-errors
"""
Schemas Pydantic do Orchestrator Central de Automacoes v5.1.

Padronizado para o Padrao Ouro Brasileiro: DD/MM/YYYY HH:MM:SS
"""

import json
import re
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

# ---------------------------------------------------------------------------
# Validadores e Utilitarios
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(
    r"^[a-zA-Z0-9 \u00E0-\u00FA\u00C0-\u00DA\u00E7\u00C7_\-\[\]\(\)\.]{2,100}$"
)
_DANGEROUS_PATH_PATTERNS = ["..", "//", "\\\\", "%", "\x00"]


def format_dt_br(val: Any) -> Any:
    """Converte qualquer formato de data para o padrao brasileiro (DD/MM/YYYY HH:MM:SS)."""
    from .timezone import to_br_timezone
    if val is None:
        return None
    
    # Se for datetime, garante que seja naive BRT antes de formatar
    if isinstance(val, datetime):
        dt = to_br_timezone(val)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    
    if isinstance(val, str):
        try:
            # ISO format (ex: 2023-01-01T12:00:00Z ou 2023-01-01T12:00:00)
            if "T" in val:
                # Remove Z se existir para evitar que fromisoformat force UTC aware
                clean_val = val.replace("Z", "")
                dt = datetime.fromisoformat(clean_val)
                # Se for aware, converte para naive BRT
                if dt.tzinfo is not None:
                    dt = to_br_timezone(dt)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            
            # SQLite format (ex: 2023-01-01 12:00:00)
            dt = datetime.strptime(val.split(".")[0], "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except (ValueError, TypeError, AttributeError):
            return val
    return val


def _validate_safe_name(v: str) -> str:
    if not _SAFE_NAME_RE.match(v):
        raise ValueError("Nome inv\u00e1lido (2-100 chars, caracteres seguros).")
    return v.strip()


def _validate_script_path(v: str) -> str:
    for pattern in _DANGEROUS_PATH_PATTERNS:
        if pattern in v:
            raise ValueError(f"Caminho proibido: '{pattern}'")
    return v


def _validate_schedule(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    try:
        obj = json.loads(v.replace("'", '"'))
        return json.dumps(obj)
    except:
        raise ValueError("Schedule deve ser JSON v\u00e1lido.")


# ---------------------------------------------------------------------------
# Schemas de Automation
# ---------------------------------------------------------------------------


class AutomationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    script_path: str = Field(..., min_length=3, max_length=500)
    schedule: Optional[str] = None
    max_runtime_minutes: int = Field(30, ge=1, le=480)
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
    enabled: Optional[bool] = None
    test_mode: Optional[bool] = None
    notification_channels: Optional[str] = None


class AutomationResponse(AutomationBase):
    id: int
    created_at: Any
    updated_at: Optional[Any] = None
    next_run: Optional[str] = None
    last_status: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def apply_br_format(self) -> "AutomationResponse":
        self.created_at = format_dt_br(self.created_at)
        self.updated_at = format_dt_br(self.updated_at)
        return self


# ---------------------------------------------------------------------------
# Schemas de Execution
# ---------------------------------------------------------------------------


class ExecutionBase(BaseModel):
    id: str
    automation_id: int
    status: str
    priority: str = "NORMAL"
    exit_code: Optional[int] = None
    requested_by: Optional[str] = "SYSTEM"
    started_at: Any
    finished_at: Optional[Any] = None
    duration_seconds: Optional[float] = None

    @model_validator(mode="after")
    def apply_br_format(self) -> "ExecutionBase":
        self.started_at = format_dt_br(self.started_at)
        self.finished_at = format_dt_br(self.finished_at)
        return self


class ExecutionResponse(ExecutionBase):
    logs: Optional[str] = None
    artifacts: Optional[str] = None
    automation_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ExecutionSummary(BaseModel):
    id: str
    automation_id: int
    automation_name: Optional[str] = None
    status: str
    priority: str = "NORMAL"
    exit_code: Optional[int] = None
    requested_by: Optional[str] = None
    started_at: Any
    finished_at: Optional[Any] = None
    duration_seconds: Optional[float] = None
    artifacts: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def apply_br_format(self) -> "ExecutionSummary":
        self.started_at = format_dt_br(self.started_at)
        self.finished_at = format_dt_br(self.finished_at)
        return self


# ---------------------------------------------------------------------------
# Schemas de Sistema
# ---------------------------------------------------------------------------


class WorkerStatus(BaseModel):
    is_alive: bool
    pid: Optional[int] = None
    last_ping: Any = None
    uptime_seconds: Optional[float] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    active_tasks: int = 0
    version: str = "5.2.0"

    @model_validator(mode="after")
    def apply_br_format(self) -> "WorkerStatus":
        from .timezone import get_now_local; self.last_ping = format_dt_br(self.last_ping)
        return self


class SystemHealth(BaseModel):
    status: str
    timestamp: Any
    database: str
    scheduler: str
    worker: WorkerStatus
    pending_tasks: int = 0
    disk_usage_mb: Optional[float] = None
    wal_size_mb: Optional[float] = None
    cpu_usage: Optional[float] = None
    ram_usage_percent: Optional[float] = None

    @model_validator(mode="after")
    def apply_br_format(self) -> "SystemHealth":
        self.timestamp = format_dt_br(self.timestamp)
        return self


class ScheduledJob(BaseModel):
    id: str
    automation_id: Optional[int] = None
    automation_name: Optional[str] = None
    next_run_time: Any = None
    trigger: str

    @model_validator(mode="after")
    def apply_br_format(self) -> "ScheduledJob":
        self.next_run_time = format_dt_br(self.next_run_time)
        return self


class AutomationMetric(BaseModel):
    name: str
    total_success: int
    total_errors: int
    avg_duration_sec: float
    last_status: Optional[str] = None
    last_run: Any = None
    test_mode: bool = False

    @model_validator(mode="after")
    def apply_br_format(self) -> "AutomationMetric":
        self.last_run = format_dt_br(self.last_run)
        return self


class MetricsSummary(BaseModel):
    total_executions: int
    success_count: int
    error_count: int
    success_rate: float
    pending_count: int
    avg_duration_sec: float


class MetricsResponse(BaseModel):
    summary: MetricsSummary
    automations: List[AutomationMetric]


class AuditEntry(BaseModel):
    id: int
    timestamp: Any
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    actor: Optional[str] = None
    details: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def apply_br_format(self) -> "AuditEntry":
        self.timestamp = format_dt_br(self.timestamp)
        return self


class SystemVersion(BaseModel):
    version: str = "5.2.0"
    python_version: str
    started_at: str
    uptime_seconds: float
    max_workers: int
    allowed_origins: List[str]


# ---------------------------------------------------------------------------
# Paginacao
# ---------------------------------------------------------------------------

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int
