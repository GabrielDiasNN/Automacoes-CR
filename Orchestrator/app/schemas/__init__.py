# pylint: disable=all
# mypy: ignore-errors
"""
Pacote contendo schemas Pydantic do Orchestrator Central de Automações v5.1.

Este __init__.py reexporta todas as entidades dos submódulos comuns,
automations, executions e system para manter retrocompatibilidade absoluta
com as diretivas de importação 'from .schemas import ...'.
"""

from .common import (
    format_dt_br,
    _validate_safe_name,
    _validate_script_path,
    _validate_schedule,
    normalize_schedule_payload,
    parse_schedule,
    describe_schedule_payload,
    preview_next_runs,
)

from .automations import (
    AutomationBase,
    AutomationCreate,
    AutomationUpdate,
    AutomationResponse,
)

from .executions import (
    ExecutionBase,
    ExecutionResponse,
    ExecutionSummary,
    ExecutionTelemetryStart,
    ExecutionTelemetryEnd,
    ExecutionQueueActionRequest,
    ExecutionQueueActionResponse,
)

from .system import (
    WorkerStatus,
    EnvContent,
    FileContent,
    SystemHealth,
    ScheduledJob,
    AutomationMetric,
    MetricsSummary,
    MetricsResponse,
    DiagnosticFinding,
    DiagnosticsDatabase,
    DiagnosticsScheduler,
    DiagnosticsQueueItem,
    DiagnosticsQueue,
    DiagnosticsHeartbeat,
    DiagnosticsFailureHotspot,
    DiagnosticsOperatorAction,
    RuntimeCheckItem,
    RecoveryPlan,
    DiagnosticsPayload,
    ScheduleValidationRequest,
    ScheduleValidationResponse,
    SchedulePreviewRequest,
    SchedulePreviewResponse,
    EnvValidationIssue,
    EnvValidationResponse,
    SystemOverviewKpis,
    SystemOverviewScheduler,
    SystemOverviewQueue,
    SystemOverviewAutomationCard,
    SystemOverviewFailure,
    SystemOverviewResponse,
    AuditEntry,
    SystemVersion,
    PaginatedResponse,
)

__all__ = [
    # Common
    "format_dt_br",
    "_validate_safe_name",
    "_validate_script_path",
    "_validate_schedule",
    "normalize_schedule_payload",
    "parse_schedule",
    "describe_schedule_payload",
    "preview_next_runs",
    # Automations
    "AutomationBase",
    "AutomationCreate",
    "AutomationUpdate",
    "AutomationResponse",
    # Executions
    "ExecutionBase",
    "ExecutionResponse",
    "ExecutionSummary",
    "ExecutionTelemetryStart",
    "ExecutionTelemetryEnd",
    "ExecutionQueueActionRequest",
    "ExecutionQueueActionResponse",
    # System
    "WorkerStatus",
    "EnvContent",
    "FileContent",
    "SystemHealth",
    "ScheduledJob",
    "AutomationMetric",
    "MetricsSummary",
    "MetricsResponse",
    "DiagnosticFinding",
    "DiagnosticsDatabase",
    "DiagnosticsScheduler",
    "DiagnosticsQueueItem",
    "DiagnosticsQueue",
    "DiagnosticsHeartbeat",
    "DiagnosticsFailureHotspot",
    "DiagnosticsOperatorAction",
    "RuntimeCheckItem",
    "RecoveryPlan",
    "DiagnosticsPayload",
    "ScheduleValidationRequest",
    "ScheduleValidationResponse",
    "SchedulePreviewRequest",
    "SchedulePreviewResponse",
    "EnvValidationIssue",
    "EnvValidationResponse",
    "SystemOverviewKpis",
    "SystemOverviewScheduler",
    "SystemOverviewQueue",
    "SystemOverviewAutomationCard",
    "SystemOverviewFailure",
    "SystemOverviewResponse",
    "AuditEntry",
    "SystemVersion",
    "PaginatedResponse",
]
