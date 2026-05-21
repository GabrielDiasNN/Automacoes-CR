# pylint: disable=all
# mypy: ignore-errors
"""
Módulo contendo schemas Pydantic relacionados ao Sistema, Telemetria, Diagnósticos e Utilitários.
"""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import (
    DIAGNOSTIC_SEVERITIES,
    ORCHESTRATOR_CONTRACT_VERSION,
    ORCHESTRATOR_SCHEMA_VERSION,
    ORCHESTRATOR_VERSION,
    WORKER_VERSION,
)
from .common import format_dt_br
from .executions import ExecutionSummary


class WorkerStatus(BaseModel):
    is_alive: bool
    pid: Optional[int] = None
    last_ping: Any = None
    uptime_seconds: Optional[float] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    active_tasks: int = 0
    version: str = WORKER_VERSION

    @model_validator(mode="after")
    def apply_br_format(self) -> "WorkerStatus":
        self.last_ping = format_dt_br(self.last_ping)
        return self


class EnvContent(BaseModel):
    content: str


class FileContent(BaseModel):
    content: str


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


class DiagnosticFinding(BaseModel):
    severity: str
    component: str
    message: str
    action_hint: str
    action_code: Optional[str] = None
    action_label: Optional[str] = None
    impact: Optional[str] = None
    priority: int = 3

    @field_validator("severity")
    @classmethod
    def v_severity(cls, v: str) -> str:
        value = v.upper()
        if value not in DIAGNOSTIC_SEVERITIES:
            raise ValueError("Severidade inválida.")
        return value


class DiagnosticsDatabase(BaseModel):
    path: str
    size_mb: float
    wal_size_mb: float
    wal_risk: str
    schema_details: dict = Field(..., alias="schema")
    schema_version: str
    model_config = ConfigDict(populate_by_name=True)


class DiagnosticsScheduler(BaseModel):
    running: bool
    jobs_loaded: int
    next_runs: List[str]
    inconsistencies: List[str] = []


class DiagnosticsQueueItem(BaseModel):
    exec_id: Optional[str] = None
    age_seconds: float = 0.0


class DiagnosticsQueue(BaseModel):
    active_count: int
    by_status: dict[str, int]
    active_by_priority: dict[str, int] = {}
    active_by_group: dict[str, int] = {}
    running_over_runtime: List[dict] = []
    oldest_pending: DiagnosticsQueueItem
    oldest_running: DiagnosticsQueueItem


class DiagnosticsHeartbeat(BaseModel):
    last_ping_age_seconds: Optional[float] = None


class DiagnosticsFailureHotspot(BaseModel):
    automation_id: int
    automation_name: str
    failures_24h: int
    last_failure_at: Optional[str] = None
    notification_channels: Optional[str] = None


class DiagnosticsOperatorAction(BaseModel):
    action_code: str
    action_label: str
    severity: str
    component: str
    reason: str
    priority: int = 3


class RuntimeCheckItem(BaseModel):
    code: str
    label: str
    status: str
    detail: str
    value: Optional[str] = None


class RecoveryPlan(BaseModel):
    light_actions: List[str] = []
    strong_actions: List[str] = []
    recommended_action: Optional[str] = None


class DiagnosticsPayload(BaseModel):
    version: str = ORCHESTRATOR_VERSION
    schema_version: str = ORCHESTRATOR_SCHEMA_VERSION
    contract_version: str = ORCHESTRATOR_CONTRACT_VERSION
    timestamp: str
    overall_status: str
    findings: List[DiagnosticFinding]
    database: DiagnosticsDatabase
    scheduler: DiagnosticsScheduler
    worker: WorkerStatus
    queue: DiagnosticsQueue
    heartbeat: DiagnosticsHeartbeat
    failure_hotspots: List[DiagnosticsFailureHotspot] = []
    operator_actions: List[DiagnosticsOperatorAction] = []
    checks: List[RuntimeCheckItem] = []
    recovery: RecoveryPlan = Field(default_factory=RecoveryPlan)


class ScheduleValidationRequest(BaseModel):
    schedule: Optional[str] = None


class ScheduleValidationResponse(BaseModel):
    valid: bool
    normalized_schedule: Optional[str] = None
    summary: str
    errors: List[str] = []


class SchedulePreviewRequest(BaseModel):
    schedule: Optional[str] = None
    limit: int = Field(5, ge=1, le=20)


class SchedulePreviewResponse(BaseModel):
    valid: bool
    normalized_schedule: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_summary: Optional[str] = None
    next_runs_preview: List[str] = []
    errors: List[str] = []


class EnvValidationIssue(BaseModel):
    line: int
    code: str
    message: str


class EnvValidationResponse(BaseModel):
    valid: bool
    issue_count: int
    normalized_line_count: int
    issues: List[EnvValidationIssue]


class SystemOverviewKpis(BaseModel):
    active_automations: int
    success_24h: int
    errors_24h: int
    pending_now: int
    next_window: Optional[str] = None


class SystemOverviewScheduler(BaseModel):
    running: bool
    jobs_loaded: int


class SystemOverviewQueue(BaseModel):
    active_count: int
    by_status: dict[str, int]
    active_by_priority: dict[str, int] = {}


class SystemOverviewAutomationCard(BaseModel):
    id: int
    name: str
    enabled: bool
    test_mode: bool
    queue_group: Optional[str] = None
    sla_minutes: Optional[int] = None
    sla_status: str = "unknown"  # ok | at_risk | violated | unknown
    sla_avg_duration_minutes: Optional[float] = None
    last_status: Optional[str] = None
    next_run: Optional[str] = None


class SystemOverviewFailure(BaseModel):
    automation_id: int
    automation_name: str
    failures: int


class SystemOverviewResponse(BaseModel):
    generated_at: str
    version: str = ORCHESTRATOR_VERSION
    schema_version: str = ORCHESTRATOR_SCHEMA_VERSION
    contract_version: str = ORCHESTRATOR_CONTRACT_VERSION
    kpis: SystemOverviewKpis
    health: SystemHealth
    status_breakdown: dict[str, int]
    jobs: List[ScheduledJob]
    recent: List[ExecutionSummary]
    automations: List[SystemOverviewAutomationCard]
    top_failures: List[SystemOverviewFailure]
    scheduler: SystemOverviewScheduler
    queue: SystemOverviewQueue
    diagnostics: DiagnosticsPayload


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
    version: str = ORCHESTRATOR_VERSION
    schema_version: str = ORCHESTRATOR_SCHEMA_VERSION
    contract_version: str = ORCHESTRATOR_CONTRACT_VERSION
    python_version: str
    started_at: str
    uptime_seconds: float
    max_workers: int
    allowed_origins: List[str]


# ---------------------------------------------------------------------------
# Paginação
# ---------------------------------------------------------------------------

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int
