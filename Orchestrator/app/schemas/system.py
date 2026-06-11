# pylint: disable=all
# mypy: ignore-errors
"""
Módulo contendo schemas Pydantic relacionados ao Sistema, Telemetria, Diagnósticos e Utilitários.
"""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import (
    BASELINE_STATUS_ATTENTION,
    BASELINE_STATUS_HEALTHY,
    BASELINE_STATUS_INCIDENT,
    DIAGNOSTIC_SEVERITIES,
    OPERATIONAL_BASELINE_STATUSES,
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
    instance_id: Optional[str] = None
    host: Optional[str] = None
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
    automation_id: Optional[int] = None
    automation_name: Optional[str] = None
    priority: Optional[str] = None
    queue_group: Optional[str] = None
    claimed_at: Optional[Any] = None
    worker_instance_id: Optional[str] = None
    worker_pid: Optional[int] = None
    orphaned: bool = False
    age_seconds: float = 0.0

    @model_validator(mode="after")
    def apply_br_format(self) -> "DiagnosticsQueueItem":
        self.claimed_at = format_dt_br(self.claimed_at)
        return self


class DiagnosticsQueue(BaseModel):
    active_count: int
    by_status: dict[str, int]
    active_by_priority: dict[str, int] = {}
    active_by_group: dict[str, int] = {}
    running_over_runtime: List[dict] = []
    orphaned_running: List[dict] = []
    retry_pressure: List[dict] = []
    timeouts_24h_by_group: List[dict] = []
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


class DiagnosticsSlo(BaseModel):
    thresholds: dict[str, int] = {}
    breaches: dict[str, bool] = {}


class DiagnosticsTrace(BaseModel):
    correlation_id: Optional[str] = None


class DiagnosticsPerformance(BaseModel):
    timings_ms: dict[str, float] = {}


class DiagnosticsTrendSummary(BaseModel):
    window_hours: int = 24
    points: int = 0
    latest_status: Optional[str] = None
    status_counts: dict[str, int] = {}
    max_pending_age_seconds: float = 0.0
    max_running_age_seconds: float = 0.0
    max_wal_size_mb: float = 0.0
    worker_offline_events: int = 0
    stale_pending_events: int = 0
    orphaned_running_events: int = 0
    baseline_attention_points: int = 0
    baseline_incident_points: int = 0
    last_snapshot_at: Optional[Any] = None

    @model_validator(mode="after")
    def apply_br_format(self) -> "DiagnosticsTrendSummary":
        self.last_snapshot_at = format_dt_br(self.last_snapshot_at)
        return self


class OperationalBaselineMetric(BaseModel):
    code: str
    label: str
    status: str
    current_value: Optional[str] = None
    attention_threshold: Optional[str] = None
    incident_threshold: Optional[str] = None
    detail: str
    action_code: Optional[str] = None

    @field_validator("status")
    @classmethod
    def v_status(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in OPERATIONAL_BASELINE_STATUSES:
            raise ValueError("Status do baseline operacional inválido.")
        return normalized


class OperationalBaselineSummary(BaseModel):
    evaluated_at: Optional[Any] = None
    status: str = BASELINE_STATUS_HEALTHY
    attention_count: int = 0
    incident_count: int = 0
    recommended_action: Optional[str] = None
    metrics: List[OperationalBaselineMetric] = []

    @field_validator("status")
    @classmethod
    def v_status(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in OPERATIONAL_BASELINE_STATUSES:
            raise ValueError("Status do baseline operacional inválido.")
        return normalized

    @model_validator(mode="after")
    def apply_br_format(self) -> "OperationalBaselineSummary":
        self.evaluated_at = format_dt_br(self.evaluated_at)
        return self


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
    slo: DiagnosticsSlo = Field(default_factory=DiagnosticsSlo)
    slo_breaches: dict[str, bool] = {}
    trend_summary: DiagnosticsTrendSummary = Field(default_factory=DiagnosticsTrendSummary)
    operational_baseline: OperationalBaselineSummary = Field(
        default_factory=OperationalBaselineSummary
    )
    performance: DiagnosticsPerformance = Field(default_factory=DiagnosticsPerformance)
    trace: DiagnosticsTrace = Field(default_factory=DiagnosticsTrace)


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


class ManagedMutationResponse(BaseModel):
    message: str
    validated: bool = True
    backup: Optional[str] = None
    backup_path: Optional[str] = None
    audit_id: Optional[int] = None


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
    description: Optional[str] = None
    script_path: Optional[str] = None
    enabled: bool
    test_mode: bool
    queue_group: Optional[str] = None
    max_runtime_minutes: Optional[int] = None
    max_retries: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    notification_channels: Optional[str] = None
    sla_minutes: Optional[int] = None
    sla_status: str = "unknown"  # ok | at_risk | violated | unknown
    sla_avg_duration_minutes: Optional[float] = None
    success_24h: int = 0
    failures_24h: int = 0
    timeouts_24h: int = 0
    avg_duration_24h_seconds: Optional[float] = None
    last_status: Optional[str] = None
    last_execution_id: Optional[str] = None
    last_execution_started_at: Optional[str] = None
    last_execution_finished_at: Optional[str] = None
    last_execution_duration_seconds: Optional[float] = None
    last_failure_reason: Optional[str] = None
    last_recovery_action: Optional[str] = None
    last_requested_by: Optional[str] = None
    next_run: Optional[str] = None
    schedule_summary: Optional[str] = None
    next_runs_preview: List[str] = []
    active_execution_count: int = 0
    pending_count: int = 0
    operational_state: str = "idle"


class SystemOverviewFailure(BaseModel):
    automation_id: int
    automation_name: str
    failures: int


class SystemOverviewPortfolio(BaseModel):
    total_items: int = 0
    governed_items: int = 0
    enabled_items: int = 0
    drift_items: int = 0
    docs_missing_items: int = 0
    sla_breached_items: int = 0
    not_registered_items: int = 0
    delete_candidate_items: int = 0
    healthy_items: int = 0
    attention_items: int = 0
    incident_items: int = 0
    status: str = BASELINE_STATUS_HEALTHY
    top_issue: Optional[str] = None
    recommended_action: Optional[str] = None

    @field_validator("status")
    @classmethod
    def v_status(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in OPERATIONAL_BASELINE_STATUSES:
            raise ValueError("Status do resumo operacional do portfólio inválido.")
        return normalized


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
    trend_summary: DiagnosticsTrendSummary = Field(default_factory=DiagnosticsTrendSummary)
    portfolio: Optional[SystemOverviewPortfolio] = None
    performance: DiagnosticsPerformance = Field(default_factory=DiagnosticsPerformance)
    diagnostics: DiagnosticsPayload


class SystemHistoryPoint(BaseModel):
    timestamp: Any
    overall_status: str
    pending_count: int = 0
    running_count: int = 0
    oldest_pending_age_seconds: float = 0.0
    oldest_running_age_seconds: float = 0.0
    wal_size_mb: float = 0.0
    worker_last_ping_age_seconds: Optional[float] = None
    running_over_runtime_count: int = 0
    orphaned_running_count: int = 0
    active_queue_groups: List[str] = []
    failure_hotspots: List[str] = []
    slo_breaches: dict[str, bool] = {}
    baseline_status: str = BASELINE_STATUS_HEALTHY
    baseline_attention_count: int = 0
    baseline_incident_count: int = 0

    @field_validator("baseline_status")
    @classmethod
    def v_baseline_status(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in OPERATIONAL_BASELINE_STATUSES:
            raise ValueError("Status do baseline operacional inválido.")
        return normalized

    @model_validator(mode="after")
    def apply_br_format(self) -> "SystemHistoryPoint":
        self.timestamp = format_dt_br(self.timestamp)
        return self


class SystemHistoryResponse(BaseModel):
    generated_at: str
    hours: int
    points: int
    trend_summary: DiagnosticsTrendSummary = Field(default_factory=DiagnosticsTrendSummary)
    items: List[SystemHistoryPoint] = []


class PortfolioDependencyStatus(BaseModel):
    oracle: str = "not_used"
    outlook: str = "not_used"
    whatsapp: str = "not_used"


class PortfolioHealthItem(BaseModel):
    catalog_id: str
    automation_id: Optional[int] = None
    name: str
    slug: str
    criticality: str
    owner_area: Optional[str] = None
    runtime: str
    enabled: bool = False
    queue_group: Optional[str] = None
    sla_minutes: Optional[int] = None
    health_status: str = "unknown"
    sla_state: str = "unknown"
    docs_status: str = "missing"
    drift_status: str = "ok"
    drift_count: int = 0
    runbook_path: Optional[str] = None
    readme_path: Optional[str] = None
    context_path: Optional[str] = None
    next_run: Any = None
    schedule_summary: Optional[str] = None
    schedule_lag_minutes: Optional[int] = None
    schedule_lag_seconds: Optional[float] = None
    last_status: Optional[str] = None
    last_success_at: Any = None
    last_failure_at: Any = None
    last_success_age_minutes: Optional[int] = None
    last_failure_age_minutes: Optional[int] = None
    last_success_age_seconds: Optional[float] = None
    last_failure_age_seconds: Optional[float] = None
    review_status: str = "active"
    review_reasons: List[str] = []
    dependency_status: PortfolioDependencyStatus = Field(
        default_factory=PortfolioDependencyStatus
    )

    @model_validator(mode="after")
    def apply_br_format(self) -> "PortfolioHealthItem":
        self.next_run = format_dt_br(self.next_run)
        self.last_success_at = format_dt_br(self.last_success_at)
        self.last_failure_at = format_dt_br(self.last_failure_at)
        return self


class PortfolioHealthSummary(SystemOverviewPortfolio):
    pass


class PortfolioHealthResponse(BaseModel):
    generated_at: str
    summary: PortfolioHealthSummary
    items: List[PortfolioHealthItem]


class PortfolioDriftIssue(BaseModel):
    code: str
    message: str
    severity: str = "WARN"
    manifest_value: Optional[str] = None
    runtime_value: Optional[str] = None


class PortfolioDriftItem(BaseModel):
    catalog_id: str
    automation_id: Optional[int] = None
    name: str
    slug: str
    issues: List[PortfolioDriftIssue] = []


class PortfolioDriftSummary(BaseModel):
    items_with_drift: int
    total_issues: int


class PortfolioDriftResponse(BaseModel):
    generated_at: str
    summary: PortfolioDriftSummary
    items: List[PortfolioDriftItem] = []


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
