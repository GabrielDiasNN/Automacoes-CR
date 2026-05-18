# pylint: disable=all
# mypy: ignore-errors
"""
Schemas Pydantic do Orchestrator Central de Automacoes v5.1.

Padronizado para o Padrao Ouro Brasileiro: DD/MM/YYYY HH:MM:SS
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

from .constants import (DIAGNOSTIC_SEVERITIES, EXECUTION_ALLOWED_PRIORITIES,
                        EXECUTION_ALLOWED_STATUSES, ORCHESTRATOR_VERSION,
                        ORCHESTRATOR_SCHEMA_VERSION, ORCHESTRATOR_CONTRACT_VERSION,
                        WORKER_VERSION)

# ---------------------------------------------------------------------------
# Validadores e Utilitarios
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(
    r"^[a-zA-Z0-9 à-úÀ-ÚçÇ_\-\[\]\(\)\.]{2,100}$"
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
        raise ValueError("Nome inválido (2-100 chars, caracteres seguros).")
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
    except Exception:
        raise ValueError("Schedule deve ser JSON válido.")

    if not isinstance(obj, dict):
        raise ValueError("Schedule deve ser um objeto JSON.")

    normalized = normalize_schedule_payload(obj)
    return json.dumps(normalized, separators=(",", ":"))

def _normalized_time_list(times: list[dict]) -> list[dict]:
    items = []
    for item in times:
        if not isinstance(item, dict):
            raise ValueError("Cada item de times deve ser objeto com h e m.")
        hour = item.get("h")
        minute = item.get("m")
        if not isinstance(hour, int) or hour < 0 or hour > 23:
            raise ValueError("times[].h deve estar entre 0 e 23.")
        if not isinstance(minute, int) or minute < 0 or minute > 59:
            raise ValueError("times[].m deve estar entre 0 e 59.")
        items.append({"h": hour, "m": minute})
    items.sort(key=lambda x: (x["h"], x["m"]))
    uniq = []
    seen = set()
    for item in items:
        key = (item["h"], item["m"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq

def _normalize_days(days: Optional[list]) -> list[int]:
    if days is None:
        return []
    if not isinstance(days, list):
        raise ValueError("daysOfWeek deve ser uma lista.")
    norm = sorted(set(days))
    if any(not isinstance(day, int) or day < 0 or day > 6 for day in norm):
        raise ValueError("daysOfWeek deve conter inteiros entre 0 e 6.")
    return norm

def _ui_day_to_python_weekday(day: int) -> int:
    # Contrato UI/legado: 0=Dom, 1=Seg ... 6=Sáb
    # datetime.weekday(): 0=Seg ... 6=Dom
    return (day + 6) % 7

def normalize_schedule_payload(obj: dict) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("Schedule deve ser um objeto JSON.")
    # Legado: daysOfWeek + times/hours/minutes
    if "schedule_type" not in obj and "scheduleType" not in obj:
        days = _normalize_days(obj.get("daysOfWeek", []))
        times = obj.get("times")
        if times is not None:
            norm_times = _normalized_time_list(times)
        else:
            hours = obj.get("hours", [])
            minutes = obj.get("minutes", [0])
            if not isinstance(hours, list) or not isinstance(minutes, list):
                raise ValueError("hours e minutes devem ser listas.")
            raw_times = []
            for hour in hours:
                for minute in minutes:
                    raw_times.append({"h": hour, "m": minute})
            norm_times = _normalized_time_list(raw_times)
        if not norm_times:
            raise ValueError("times deve conter ao menos um horário válido.")
        return {
            "schedule_version": 2,
            "schedule_type": "weekly",
            "timezone": "America/Sao_Paulo",
            "days_of_week": days,
            "times": norm_times,
        }

    schedule_type = str(obj.get("schedule_type") or obj.get("scheduleType") or "").lower().strip()
    valid_types = {"manual", "daily", "weekly", "monthly", "interval", "once"}
    if schedule_type not in valid_types:
        raise ValueError("schedule_type inválido.")

    timezone_name = str(obj.get("timezone") or "America/Sao_Paulo")
    base = {
        "schedule_version": 2,
        "schedule_type": schedule_type,
        "timezone": timezone_name,
    }

    if schedule_type == "manual":
        return base
    if schedule_type == "interval":
        val = obj.get("interval_minutes")
        if not isinstance(val, int) or val < 1 or val > 1440:
            raise ValueError("interval_minutes deve estar entre 1 e 1440.")
        base["interval_minutes"] = val
        return base
    if schedule_type == "once":
        run_at = obj.get("run_at")
        if not isinstance(run_at, str) or not run_at.strip():
            raise ValueError("run_at é obrigatório para schedule_type=once.")
        base["run_at"] = run_at.strip()
        return base

    times = _normalized_time_list(obj.get("times") or [])
    if not times:
        raise ValueError("times deve conter ao menos um horário.")
    base["times"] = times

    if schedule_type == "daily":
        return base
    if schedule_type == "weekly":
        days = _normalize_days(obj.get("days_of_week"))
        if not days:
            raise ValueError("days_of_week é obrigatório para schedule_type=weekly.")
        base["days_of_week"] = days
        return base

    days_of_month = obj.get("days_of_month")
    if not isinstance(days_of_month, list) or not days_of_month:
        raise ValueError("days_of_month é obrigatório para schedule_type=monthly.")
    norm_month = sorted(set(days_of_month))
    if any(not isinstance(day, int) or day < 1 or day > 31 for day in norm_month):
        raise ValueError("days_of_month deve conter inteiros entre 1 e 31.")
    base["days_of_month"] = norm_month
    return base

def parse_schedule(v: Optional[str]) -> Optional[dict]:
    if not v:
        return None
    obj = json.loads(v.replace("'", '"'))
    return normalize_schedule_payload(obj)

def describe_schedule_payload(schedule: Optional[dict]) -> str:
    if not schedule:
        return "Manual"
    stype = schedule.get("schedule_type")
    if stype == "manual":
        return "Manual"
    if stype == "daily":
        times = schedule.get("times", [])
        return "Diário às " + ", ".join(f"{t['h']:02d}:{t['m']:02d}" for t in times)
    if stype == "weekly":
        day_names = {0: "Dom", 1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb"}
        days = schedule.get("days_of_week", [])
        times = schedule.get("times", [])
        day_label = ", ".join(day_names.get(d, str(d)) for d in days) if days else "Todos os dias"
        time_label = ", ".join(f"{t['h']:02d}:{t['m']:02d}" for t in times)
        return f"Semanal: {day_label} às {time_label}"
    if stype == "monthly":
        days = schedule.get("days_of_month", [])
        times = schedule.get("times", [])
        return (
            f"Mensal dia(s) {', '.join(str(d) for d in days)} às "
            + ", ".join(f"{t['h']:02d}:{t['m']:02d}" for t in times)
        )
    if stype == "interval":
        return f"A cada {schedule.get('interval_minutes', 0)} min"
    if stype == "once":
        return f"Execução única em {schedule.get('run_at', '-')}"
    return "Configurada"

def preview_next_runs(schedule: Optional[dict], count: int = 5) -> list[str]:
    if not schedule:
        return []
    from .timezone import get_now_local
    now = get_now_local().replace(second=0, microsecond=0)
    out = []
    stype = schedule.get("schedule_type")
    if stype == "interval":
        step = int(schedule.get("interval_minutes", 1))
        start = now + timedelta(minutes=step)
        for idx in range(count):
            out.append(format_dt_br(start + timedelta(minutes=idx * step)))
        return out
    if stype == "once":
        run_at = schedule.get("run_at")
        try:
            dt = datetime.fromisoformat(str(run_at).replace("Z", ""))
            if dt >= now:
                out.append(format_dt_br(dt))
        except Exception:
            pass
        return out
    # Para cadências baseadas em horário, buscar próxima semana/mês por varredura simples.
    candidate = now
    max_scan_days = 62
    while len(out) < count and max_scan_days > 0:
        candidate += timedelta(minutes=1)
        max_scan_days -= 1 if candidate.hour == 0 and candidate.minute == 0 else 0
        times = schedule.get("times", [])
        hm = {(t["h"], t["m"]) for t in times}
        if (candidate.hour, candidate.minute) not in hm:
            continue
        if stype == "daily":
            out.append(format_dt_br(candidate))
            continue
        if stype == "weekly":
            days = set(schedule.get("days_of_week", []))
            py_days = {_ui_day_to_python_weekday(int(day)) for day in days}
            if candidate.weekday() in py_days:
                out.append(format_dt_br(candidate))
            continue
        if stype == "monthly":
            days = set(schedule.get("days_of_month", []))
            if candidate.day in days:
                out.append(format_dt_br(candidate))
    return out

# ---------------------------------------------------------------------------
# Schemas de Automation
# ---------------------------------------------------------------------------

class AutomationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    script_path: str = Field(..., min_length=3, max_length=500)
    schedule: Optional[str] = None
    max_runtime_minutes: int = Field(30, ge=1, le=480)
    max_retries: int = Field(0, ge=0, le=10)
    cooldown_minutes: int = Field(0, ge=0, le=1440)
    queue_group: Optional[str] = Field(None, max_length=100)
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
    schedule_type: Optional[str] = None
    schedule_summary: Optional[str] = None
    next_runs_preview: List[str] = []
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
    retry_count: int = 0
    max_retries: int = 0
    queue_group: Optional[str] = None
    failure_reason: Optional[str] = None
    recovery_action: Optional[str] = None
    exit_code: Optional[int] = None
    requested_by: Optional[str] = "SYSTEM"
    started_at: Any
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
    version: str = WORKER_VERSION

    @model_validator(mode="after")
    def apply_br_format(self) -> "WorkerStatus":
        from .timezone import get_now_local; self.last_ping = format_dt_br(self.last_ping)
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

class SystemOverviewAutomationCard(BaseModel):
    id: int
    name: str
    enabled: bool
    test_mode: bool
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
# Paginacao
# ---------------------------------------------------------------------------

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int
