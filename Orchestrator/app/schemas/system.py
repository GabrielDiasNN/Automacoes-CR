"""
Módulo contendo schemas Pydantic relacionados ao Sistema, Telemetria, Diagnósticos e Utilitários.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import (
    BASELINE_STATUS_HEALTHY,
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
    pid: int | None = None
    instance_id: str | None = None
    host: str | None = None
    last_ping: Any = None
    uptime_seconds: float | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    active_tasks: int = 0
    pool_saturated_seconds: float = 0.0
    version: str = WORKER_VERSION

    @model_validator(mode="after")
    def apply_br_format(self) -> WorkerStatus:
        self.last_ping = format_dt_br(self.last_ping)
        return self


class EnvContent(BaseModel):
    content: str


# Teto de entradas por lote de broadcast. O flusher do Worker emite UMA entrada
# por execução ativa (as mensagens são concatenadas antes do POST), então o lote
# real é limitado por WORKER_MAX_CONCURRENCY — este teto é folgado e serve só
# para impedir um payload não-limitado de um chamador arbitrário (#42).
WS_MAX_LOG_ENTRIES = 500


class WsTokenResponse(BaseModel):
    """Token efêmero de handshake WebSocket (uso único)."""

    token: str
    expires_in_seconds: int


class WsLogEntry(BaseModel):
    """Entrada de log emitida pelo Worker para o Event Bus WebSocket.

    Campos têm default vazio de propósito: entradas incompletas são descartadas
    por LogBroadcaster.emit_entries (que exige exec_id E message), preservando o
    contrato de "ignora silenciosamente" em vez de reprovar o lote inteiro.
    """

    exec_id: str = ""
    message: str = ""


class WsLogBatch(BaseModel):
    """Lote de logs enviado pelo flusher do Worker."""

    logs: list[WsLogEntry] = Field(default_factory=list, max_length=WS_MAX_LOG_ENTRIES)


class WsEventPayload(BaseModel):
    """Evento de sistema para o WebSocket global."""

    type: str = "UNKNOWN"
    data: dict[str, Any] = Field(default_factory=dict)


class FileContent(BaseModel):
    # Limite anti-DoS: configs/código gerenciado são pequenos; 1 MB é folgado
    # mas impede escrita de payload gigante via rotas de edição de arquivo.
    content: str = Field(..., max_length=1_000_000)


class ManagedFileEntry(BaseModel):
    """Um arquivo gerenciado (config JSON ou script) listado pela Web IDE."""

    filename: str
    content: str


class SystemHealth(BaseModel):
    status: str
    timestamp: Any
    database: str
    scheduler: str
    worker: WorkerStatus
    pending_tasks: int = 0
    disk_usage_mb: float | None = None
    wal_size_mb: float | None = None
    cpu_usage: float | None = None
    ram_usage_percent: float | None = None

    @model_validator(mode="after")
    def apply_br_format(self) -> SystemHealth:
        self.timestamp = format_dt_br(self.timestamp)
        return self


class ScheduledJob(BaseModel):
    id: str
    automation_id: int | None = None
    automation_name: str | None = None
    next_run_time: Any = None
    trigger: str

    @model_validator(mode="after")
    def apply_br_format(self) -> ScheduledJob:
        self.next_run_time = format_dt_br(self.next_run_time)
        return self


class AutomationMetric(BaseModel):
    name: str
    total_success: int
    total_errors: int
    avg_duration_sec: float
    last_status: str | None = None
    last_run: Any = None
    test_mode: bool = False

    @model_validator(mode="after")
    def apply_br_format(self) -> AutomationMetric:
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
    automations: list[AutomationMetric]


class DiagnosticFinding(BaseModel):
    severity: str
    component: str
    message: str
    action_hint: str
    action_code: str | None = None
    action_label: str | None = None
    impact: str | None = None
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
    schema_details: dict[str, Any] = Field(..., alias="schema")
    schema_version: str
    model_config = ConfigDict(populate_by_name=True)


class DiagnosticsScheduler(BaseModel):
    running: bool
    jobs_loaded: int
    next_runs: list[str]
    inconsistencies: list[str] = []


class DiagnosticsQueueItem(BaseModel):
    exec_id: str | None = None
    automation_id: int | None = None
    automation_name: str | None = None
    priority: str | None = None
    queue_group: str | None = None
    claimed_at: Any | None = None
    worker_instance_id: str | None = None
    worker_pid: int | None = None
    orphaned: bool = False
    age_seconds: float = 0.0

    @model_validator(mode="after")
    def apply_br_format(self) -> DiagnosticsQueueItem:
        self.claimed_at = format_dt_br(self.claimed_at)
        return self


class DiagnosticsQueue(BaseModel):
    active_count: int
    by_status: dict[str, int]
    active_by_priority: dict[str, int] = {}
    active_by_group: dict[str, int] = {}
    running_over_runtime: list[dict[str, Any]] = []
    orphaned_running: list[dict[str, Any]] = []
    retry_pressure: list[dict[str, Any]] = []
    timeouts_24h_by_group: list[dict[str, Any]] = []
    oldest_pending: DiagnosticsQueueItem
    oldest_running: DiagnosticsQueueItem


class DiagnosticsHeartbeat(BaseModel):
    last_ping_age_seconds: float | None = None


class DiagnosticsFailureHotspot(BaseModel):
    automation_id: int
    automation_name: str
    failures_24h: int
    last_failure_at: str | None = None
    notification_channels: str | None = None


class DiagnosticsSlaBreach(BaseModel):
    automation_id: int
    automation_name: str | None = None
    exec_id: str
    duration_seconds: float
    sla_minutes: int
    finished_at: str | None = None


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
    value: str | None = None


class RecoveryPlan(BaseModel):
    light_actions: list[str] = []
    strong_actions: list[str] = []
    recommended_action: str | None = None


class DiagnosticsSlo(BaseModel):
    thresholds: dict[str, int] = {}
    breaches: dict[str, bool] = {}


class DiagnosticsTrace(BaseModel):
    correlation_id: str | None = None


class DiagnosticsPerformance(BaseModel):
    timings_ms: dict[str, float] = {}


class DiagnosticsTrendSummary(BaseModel):
    window_hours: int = 24
    points: int = 0
    latest_status: str | None = None
    status_counts: dict[str, int] = {}
    max_pending_age_seconds: float = 0.0
    max_running_age_seconds: float = 0.0
    max_wal_size_mb: float = 0.0
    worker_offline_events: int = 0
    stale_pending_events: int = 0
    orphaned_running_events: int = 0
    baseline_attention_points: int = 0
    baseline_incident_points: int = 0
    last_snapshot_at: Any | None = None

    @model_validator(mode="after")
    def apply_br_format(self) -> DiagnosticsTrendSummary:
        self.last_snapshot_at = format_dt_br(self.last_snapshot_at)
        return self


class OperationalBaselineMetric(BaseModel):
    code: str
    label: str
    status: str
    current_value: str | None = None
    attention_threshold: str | None = None
    incident_threshold: str | None = None
    detail: str
    action_code: str | None = None

    @field_validator("status")
    @classmethod
    def v_status(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in OPERATIONAL_BASELINE_STATUSES:
            raise ValueError("Status do baseline operacional inválido.")
        return normalized


class OperationalBaselineSummary(BaseModel):
    evaluated_at: Any | None = None
    status: str = BASELINE_STATUS_HEALTHY
    attention_count: int = 0
    incident_count: int = 0
    recommended_action: str | None = None
    metrics: list[OperationalBaselineMetric] = []

    @field_validator("status")
    @classmethod
    def v_status(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in OPERATIONAL_BASELINE_STATUSES:
            raise ValueError("Status do baseline operacional inválido.")
        return normalized

    @model_validator(mode="after")
    def apply_br_format(self) -> OperationalBaselineSummary:
        self.evaluated_at = format_dt_br(self.evaluated_at)
        return self


class DiagnosticsPayload(BaseModel):
    version: str = ORCHESTRATOR_VERSION
    schema_version: str = ORCHESTRATOR_SCHEMA_VERSION
    contract_version: str = ORCHESTRATOR_CONTRACT_VERSION
    timestamp: str
    overall_status: str
    findings: list[DiagnosticFinding]
    database: DiagnosticsDatabase
    scheduler: DiagnosticsScheduler
    worker: WorkerStatus
    queue: DiagnosticsQueue
    heartbeat: DiagnosticsHeartbeat
    failure_hotspots: list[DiagnosticsFailureHotspot] = []
    sla_breaches: list[DiagnosticsSlaBreach] = []
    operator_actions: list[DiagnosticsOperatorAction] = []
    checks: list[RuntimeCheckItem] = []
    recovery: RecoveryPlan = Field(default_factory=RecoveryPlan)
    slo: DiagnosticsSlo = Field(default_factory=DiagnosticsSlo)
    slo_breaches: dict[str, bool] = {}
    trend_summary: DiagnosticsTrendSummary = Field(
        default_factory=DiagnosticsTrendSummary
    )
    operational_baseline: OperationalBaselineSummary = Field(
        default_factory=OperationalBaselineSummary
    )
    performance: DiagnosticsPerformance = Field(default_factory=DiagnosticsPerformance)
    trace: DiagnosticsTrace = Field(default_factory=DiagnosticsTrace)


class ScheduleValidationRequest(BaseModel):
    schedule: str | None = None


class ScheduleValidationResponse(BaseModel):
    valid: bool
    normalized_schedule: str | None = None
    summary: str
    errors: list[str] = []


class SchedulePreviewRequest(BaseModel):
    schedule: str | None = None
    limit: int = Field(5, ge=1, le=20)


class SchedulePreviewResponse(BaseModel):
    valid: bool
    normalized_schedule: str | None = None
    schedule_type: str | None = None
    schedule_summary: str | None = None
    next_runs_preview: list[str] = []
    errors: list[str] = []


class EnvValidationIssue(BaseModel):
    line: int
    code: str
    message: str
    # "error" bloqueia a escrita; "info" é apenas informativo. MASKED_VALUE
    # passou a "info" em 31/07/2026: o placeholder é resolvido para o valor real
    # antes da gravação, em vez de reprovar o payload.
    severity: str = "error"


class EnvValidationResponse(BaseModel):
    valid: bool
    issue_count: int
    normalized_line_count: int
    issues: list[EnvValidationIssue]


class ManagedMutationResponse(BaseModel):
    message: str
    validated: bool = True
    backup: str | None = None
    backup_path: str | None = None
    audit_id: int | None = None


class SystemOverviewKpis(BaseModel):
    active_automations: int
    success_24h: int
    errors_24h: int
    pending_now: int
    next_window: str | None = None


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
    description: str | None = None
    script_path: str | None = None
    enabled: bool
    test_mode: bool
    queue_group: str | None = None
    max_runtime_minutes: int | None = None
    max_retries: int | None = None
    cooldown_minutes: int | None = None
    notification_channels: str | None = None
    sla_minutes: int | None = None
    sla_status: str = "unknown"  # ok | at_risk | violated | unknown
    sla_avg_duration_minutes: float | None = None
    success_24h: int = 0
    failures_24h: int = 0
    timeouts_24h: int = 0
    avg_duration_24h_seconds: float | None = None
    last_status: str | None = None
    last_execution_id: str | None = None
    last_execution_started_at: str | None = None
    last_execution_finished_at: str | None = None
    last_execution_duration_seconds: float | None = None
    last_failure_reason: str | None = None
    last_recovery_action: str | None = None
    last_requested_by: str | None = None
    next_run: str | None = None
    schedule_summary: str | None = None
    next_runs_preview: list[str] = []
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
    top_issue: str | None = None
    recommended_action: str | None = None

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
    jobs: list[ScheduledJob]
    recent: list[ExecutionSummary]
    automations: list[SystemOverviewAutomationCard]
    top_failures: list[SystemOverviewFailure]
    scheduler: SystemOverviewScheduler
    queue: SystemOverviewQueue
    trend_summary: DiagnosticsTrendSummary = Field(
        default_factory=DiagnosticsTrendSummary
    )
    portfolio: SystemOverviewPortfolio | None = None
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
    worker_last_ping_age_seconds: float | None = None
    running_over_runtime_count: int = 0
    orphaned_running_count: int = 0
    active_queue_groups: list[str] = []
    failure_hotspots: list[str] = []
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
    def apply_br_format(self) -> SystemHistoryPoint:
        self.timestamp = format_dt_br(self.timestamp)
        return self


class SystemHistoryResponse(BaseModel):
    generated_at: str
    hours: int
    points: int
    trend_summary: DiagnosticsTrendSummary = Field(
        default_factory=DiagnosticsTrendSummary
    )
    items: list[SystemHistoryPoint] = []


class DailyExecutionMetric(BaseModel):
    date: str
    total: int = 0
    success: int = 0
    errors: int = 0
    success_rate_pct: float | None = None
    avg_duration_seconds: float | None = None
    p95_duration_seconds: float | None = None


class SystemMetricsDailyResponse(BaseModel):
    generated_at: str
    days: int
    items: list[DailyExecutionMetric] = []


class PortfolioDependencyStatus(BaseModel):
    oracle: str = "not_used"
    outlook: str = "not_used"
    whatsapp: str = "not_used"


class PortfolioHealthItem(BaseModel):
    catalog_id: str
    automation_id: int | None = None
    name: str
    slug: str
    criticality: str
    owner_area: str | None = None
    runtime: str
    enabled: bool = False
    queue_group: str | None = None
    sla_minutes: int | None = None
    health_status: str = "unknown"
    sla_state: str = "unknown"
    docs_status: str = "missing"
    drift_status: str = "ok"
    drift_count: int = 0
    runbook_path: str | None = None
    readme_path: str | None = None
    context_path: str | None = None
    next_run: Any = None
    schedule_summary: str | None = None
    schedule_lag_minutes: int | None = None
    schedule_lag_seconds: float | None = None
    last_status: str | None = None
    last_success_at: Any = None
    last_failure_at: Any = None
    last_success_age_minutes: int | None = None
    last_failure_age_minutes: int | None = None
    last_success_age_seconds: float | None = None
    last_failure_age_seconds: float | None = None
    review_status: str = "active"
    review_reasons: list[str] = []
    dependency_status: PortfolioDependencyStatus = Field(
        default_factory=PortfolioDependencyStatus
    )

    @model_validator(mode="after")
    def apply_br_format(self) -> PortfolioHealthItem:
        self.next_run = format_dt_br(self.next_run)
        self.last_success_at = format_dt_br(self.last_success_at)
        self.last_failure_at = format_dt_br(self.last_failure_at)
        return self


class PortfolioHealthSummary(SystemOverviewPortfolio):
    pass


class PortfolioHealthResponse(BaseModel):
    generated_at: str
    summary: PortfolioHealthSummary
    items: list[PortfolioHealthItem]


class PortfolioDriftIssue(BaseModel):
    code: str
    message: str
    severity: str = "WARN"
    manifest_value: str | None = None
    runtime_value: str | None = None


class PortfolioDriftItem(BaseModel):
    catalog_id: str
    automation_id: int | None = None
    name: str
    slug: str
    issues: list[PortfolioDriftIssue] = []


class PortfolioDriftSummary(BaseModel):
    items_with_drift: int
    total_issues: int


class PortfolioDriftResponse(BaseModel):
    generated_at: str
    summary: PortfolioDriftSummary
    items: list[PortfolioDriftItem] = []


class AuditEntry(BaseModel):
    id: int
    timestamp: Any
    action: str
    entity_type: str
    entity_id: str | None = None
    actor: str | None = None
    details: str | None = None
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def apply_br_format(self) -> AuditEntry:
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
    allowed_origins: list[str]


# ---------------------------------------------------------------------------
# Paginação
# ---------------------------------------------------------------------------


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int
