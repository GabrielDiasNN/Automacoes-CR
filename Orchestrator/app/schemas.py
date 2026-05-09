"""
Schemas Pydantic do Orchestrator Hub Soberano v5.0.

Validacao rigorosa de inputs com field_validators para:
  - script_path: anti-path-traversal, ASCII-safe
  - schedule: JSON estruturado obrigatorio
  - name: caracteres seguros
"""

import json
import re
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Validadores reutilizaveis
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9 _\-]{2,100}$")
_DANGEROUS_PATH_PATTERNS = ["..", "//", "\\\\", "%", "\x00"]


def _validate_safe_name(v: str) -> str:
    """Garante que o nome nao contem caracteres perigosos."""
    if not _SAFE_NAME_RE.match(v):
        raise ValueError(
            "Nome deve conter apenas letras, numeros, espacos, hifens e underscores (2-100 chars)."
        )
    return v.strip()


def _validate_script_path(v: str) -> str:
    """Anti-path-traversal: rejeita caminhos suspeitos."""
    for pattern in _DANGEROUS_PATH_PATTERNS:
        if pattern in v:
            raise ValueError(f"Caminho contem padrao proibido: '{pattern}'")
    # Deve comecar com ./ ou .\ (caminho relativo ao projeto) ou ser absoluto dentro de C:\Automacoes
    if not (v.startswith("./") or v.startswith(".\\")):
        if not v.upper().startswith("C:\\AUTOMACOES"):
            raise ValueError(
                "Caminho deve ser relativo ao projeto (./) ou absoluto dentro de C:\\Automacoes."
            )
    return v


def _validate_schedule(v: Optional[str]) -> Optional[str]:
    """Valida que o schedule e um JSON estruturado valido."""
    if v is None or v == "":
        return None
    try:
        obj = json.loads(v)
    except json.JSONDecodeError:
        # Tentar converter formato Python dict (aspas simples)
        try:
            cleaned = v.replace("'", '"')
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(
                "Schedule deve ser JSON valido. Ex: {\"daysOfWeek\": [0,1,2], \"hours\": [9], \"minutes\": [30]}"
            )
    # Validar estrutura minima
    if not isinstance(obj, dict):
        raise ValueError("Schedule deve ser um objeto JSON.")
    return json.dumps(obj)  # Normaliza para JSON limpo


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
    def validate_name(cls, v: str) -> str:
        return _validate_safe_name(v)

    @field_validator("script_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return _validate_script_path(v)

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, v: Optional[str]) -> Optional[str]:
        return _validate_schedule(v)


class AutomationCreate(AutomationBase):
    pass


class AutomationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    script_path: Optional[str] = Field(None, min_length=3, max_length=500)
    schedule: Optional[str] = None
    max_runtime_minutes: Optional[int] = Field(None, ge=1, le=480)
    enabled: Optional[bool] = None
    test_mode: Optional[bool] = None
    notification_channels: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_safe_name(v)
        return v

    @field_validator("script_path")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_script_path(v)
        return v

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_schedule(v)
        return v


class AutomationResponse(AutomationBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    next_run: Optional[str] = None
    last_status: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Schemas de Execution
# ---------------------------------------------------------------------------

class ExecutionBase(BaseModel):
    id: str
    automation_id: int
    status: str
    priority: str = "NORMAL"  # HIGH | NORMAL | LOW
    exit_code: Optional[int] = None
    requested_by: Optional[str] = "SYSTEM"
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class ExecutionResponse(ExecutionBase):
    logs: Optional[str] = None
    artifacts: Optional[str] = None
    automation_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ExecutionSummary(BaseModel):
    """Versao leve da execucao (sem logs completos) para listagens."""
    id: str
    automation_id: int
    automation_name: Optional[str] = None
    status: str
    priority: str = "NORMAL"
    exit_code: Optional[int] = None
    requested_by: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    artifacts: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Schemas de Sistema
# ---------------------------------------------------------------------------

class WorkerStatus(BaseModel):
    is_alive: bool
    pid: Optional[int] = None
    last_ping: Optional[datetime] = None
    uptime_seconds: Optional[float] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    active_tasks: int = 0
    version: str = "5.0.0"


class SystemHealth(BaseModel):
    status: str  # healthy, degraded, unhealthy
    timestamp: datetime
    database: str
    scheduler: str
    worker: WorkerStatus
    pending_tasks: int = 0
    disk_usage_mb: Optional[float] = None
    wal_size_mb: Optional[float] = None   # Indicador de checkpoint pendente


class SystemVersion(BaseModel):
    """Informacoes de versao e build do Orchestrator."""
    version: str
    python_version: str
    started_at: str
    uptime_seconds: float
    max_workers: int
    allowed_origins: List[str]


class MetricsSummary(BaseModel):
    total_executions: int
    success_count: int
    error_count: int
    success_rate: float
    pending_count: int
    avg_duration_sec: float


class AutomationMetric(BaseModel):
    name: str
    total_success: int
    total_errors: int
    avg_duration_sec: float
    last_status: Optional[str] = None
    last_run: Optional[datetime] = None


class MetricsResponse(BaseModel):
    summary: MetricsSummary
    automations: List[AutomationMetric]


class AuditEntry(BaseModel):
    id: int
    timestamp: datetime
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    actor: Optional[str] = None
    details: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Schema Generico de Paginacao
# ---------------------------------------------------------------------------

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int
