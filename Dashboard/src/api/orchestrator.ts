import { api, qs } from "./client";

/* ============================================================================
   Tipos — espelham os schemas Pydantic do Orchestrator (v5).
   Datas vêm pré-formatadas em pt-BR (string) pelo backend.
   ========================================================================== */

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// ── Automações ──────────────────────────────────────────────────────────────

export interface Automation {
  id: number;
  name: string;
  description: string | null;
  script_path: string;
  schedule: string | null;
  max_runtime_minutes: number;
  max_retries: number;
  cooldown_minutes: number;
  queue_group: string | null;
  sla_minutes: number | null;
  enabled: boolean;
  test_mode: boolean;
  notification_channels: string | null;
  created_at: string;
  updated_at: string | null;
  next_run: string | null;
  last_status: string | null;
  last_execution_id: string | null;
  last_execution_started_at: string | null;
  last_execution_finished_at: string | null;
  last_execution_duration_seconds: number | null;
  last_failure_reason: string | null;
  schedule_type: string | null;
  schedule_summary: string | null;
  next_runs_preview: string[];
  active_execution_count: number;
  success_24h: number;
  failures_24h: number;
  timeouts_24h: number;
  pending_count: number;
  operational_state: string; // idle | running | blocked | ...
}

// ── Execuções ───────────────────────────────────────────────────────────────

export type OperatorSeverity = "CRITICAL" | "HIGH" | "MODERATE" | "NORMAL";

export interface ExecutionSummary {
  id: string;
  automation_id: number;
  automation_name: string | null;
  status: string;
  priority: string;
  retry_count: number;
  max_retries: number;
  queue_group: string | null;
  failure_reason: string | null;
  recovery_action: string | null;
  exit_code: number | null;
  requested_by: string | null;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  // inteligência operacional
  operator_attention_required: boolean;
  operator_severity: OperatorSeverity | null;
  operator_score: number;
  operator_reason_summary: string | null;
  operator_action_code: string | null;
  operator_action_label: string | null;
  operator_action_hint: string | null;
  requeue_allowed: boolean;
  requeue_block_reason: string | null;
  stop_allowed: boolean;
  related_execution_id: string | null;
}

export interface ExecutionDetail extends ExecutionSummary {
  logs: string | null;
  artifacts: string | null;
}

export interface QueueActionResponse {
  message: string;
  source_exec_id: string;
  queued_exec_id: string;
  automation_id: number;
  retry_count: number;
  max_retries: number;
  recovery_action: string;
}

// ── Sistema ─────────────────────────────────────────────────────────────────

export interface WorkerStatus {
  is_alive: boolean;
  pid: number | null;
  instance_id: string | null;
  host: string | null;
  last_ping: string | null;
  uptime_seconds: number | null;
  tasks_completed: number;
  tasks_failed: number;
  active_tasks: number;
  version: string;
}

export interface SystemHealth {
  status: string; // healthy | warning | critical
  timestamp: string;
  database: string;
  scheduler: string;
  worker: WorkerStatus;
  pending_tasks: number;
  disk_usage_mb: number | null;
  wal_size_mb: number | null;
  cpu_usage: number | null;
  ram_usage_percent: number | null;
}

export interface ScheduledJob {
  id: string;
  automation_id: number | null;
  automation_name: string | null;
  next_run_time: string | null;
  trigger: string;
}

export interface BaselineStatus {
  evaluated_at: string | null;
  status: "healthy" | "attention" | "incident";
  attention_count: number;
  incident_count: number;
  recommended_action: string | null;
  metrics: BaselineMetric[];
}

export interface BaselineMetric {
  code: string;
  label: string;
  status: "healthy" | "attention" | "incident";
  current_value: string | null;
  attention_threshold: string | null;
  incident_threshold: string | null;
  detail: string;
  action_code: string | null;
}

export interface SystemHistoryPoint {
  timestamp: string;
  overall_status: string;
  pending_count: number;
  running_count: number;
  oldest_pending_age_seconds: number;
  oldest_running_age_seconds: number;
  wal_size_mb: number;
  worker_last_ping_age_seconds: number | null;
  running_over_runtime_count: number;
  orphaned_running_count: number;
  baseline_status: string;
  baseline_attention_count: number;
  baseline_incident_count: number;
}

export interface SystemHistory {
  generated_at: string;
  hours: number;
  points: number;
  items: SystemHistoryPoint[];
}

export interface DailyExecutionMetric {
  date: string;
  total: number;
  success: number;
  errors: number;
  success_rate_pct: number | null;
  avg_duration_seconds: number | null;
  p95_duration_seconds: number | null;
}

export interface SystemMetricsDaily {
  generated_at: string;
  days: number;
  items: DailyExecutionMetric[];
}

export interface SystemKpis {
  active_automations: number;
  success_24h: number;
  errors_24h: number;
  pending_now: number;
  next_window: string | null;
}

export interface OverviewAutomationCard {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  test_mode: boolean;
  queue_group: string | null;
  sla_minutes: number | null;
  sla_status: "ok" | "at_risk" | "violated" | "unknown";
  sla_avg_duration_minutes: number | null;
  success_24h: number;
  failures_24h: number;
  timeouts_24h: number;
  avg_duration_24h_seconds: number | null;
  last_status: string | null;
  last_execution_id: string | null;
  last_execution_started_at: string | null;
  last_execution_duration_seconds: number | null;
  last_failure_reason: string | null;
  next_run: string | null;
  schedule_summary: string | null;
  active_execution_count: number;
  pending_count: number;
  operational_state: string;
}

export interface PortfolioSummary {
  total_items: number;
  governed_items: number;
  enabled_items: number;
  drift_items: number;
  docs_missing_items: number;
  sla_breached_items: number;
  healthy_items: number;
  attention_items: number;
  incident_items: number;
  status: "healthy" | "attention" | "incident";
  top_issue: string | null;
  recommended_action: string | null;
}

export interface DiagnosticFinding {
  severity: "CRITICAL" | "HIGH" | "MODERATE" | "INFO" | string;
  component: string;
  message: string;
  action_hint: string;
  action_code: string | null;
  action_label: string | null;
  impact: string | null;
  priority: number;
}

export interface QueueOverview {
  active_count: number;
  by_status: Record<string, number>;
  active_by_priority: Record<string, number>;
}

export interface SystemOverview {
  generated_at: string;
  version: string;
  kpis: SystemKpis;
  health: SystemHealth;
  status_breakdown: Record<string, number>;
  jobs: ScheduledJob[];
  recent: ExecutionSummary[];
  automations: OverviewAutomationCard[];
  top_failures: { automation_id: number; automation_name: string; failures: number }[];
  scheduler: { running: boolean; jobs_loaded: number };
  queue: QueueOverview;
  portfolio: PortfolioSummary | null;
  diagnostics: {
    overall_status: string;
    findings: DiagnosticFinding[];
    operational_baseline: BaselineStatus;
    failure_hotspots: { automation_id: number; automation_name: string; failures_24h: number }[];
  };
}

// ── Portfólio ───────────────────────────────────────────────────────────────

export interface PortfolioHealthItem {
  catalog_id: string;
  automation_id: number | null;
  name: string;
  slug: string;
  criticality: "high" | "medium" | "low" | string;
  owner_area: string | null;
  runtime: string;
  enabled: boolean;
  queue_group: string | null;
  sla_minutes: number | null;
  health_status: string;
  sla_state: string;
  docs_status: string;
  drift_status: string;
  drift_count: number;
  next_run: string | null;
  schedule_summary: string | null;
  last_status: string | null;
  review_status: string;
}

export interface PortfolioHealth {
  generated_at: string;
  summary: PortfolioSummary;
  items: PortfolioHealthItem[];
}

// ── Beneficiamento (tipagem ampliada na Fase 4) ──────────────────────────────

export interface BeneficiamentoLatestPeriod {
  period: string;
  label: string;
  status: string;
  updated_at: string | null;
}

export interface BeneficiamentoHealth {
  status: string;
  reason_code: string | null;
  recommended_action: string | null;
  findings: string[];
  latest_period: BeneficiamentoLatestPeriod | null;
  generated_at: string;
  [k: string]: unknown;
}

export interface BeneficiamentoPeriodPayload {
  key: string;
  label: string;
  available: boolean;
  status: string;
  updated_at: string | null;
  reason_message: string | null;
  recommended_action: string | null;
  metrics: Record<string, unknown>;
  quality: Record<string, unknown>;
  rankings: Record<string, unknown>;
  highlights: Record<string, unknown>;
}

export interface BeneficiamentoDashboard {
  generated_at: string;
  default_period: string;
  overall: Record<string, unknown>;
  comparison: Record<string, unknown>[];
  periods: Record<string, BeneficiamentoPeriodPayload>;
  health: BeneficiamentoHealth;
}

// ── Beneficiamento — overview/detail (filtros dinâmicos sobre SQLite histórico) ──

export interface BeneficiamentoFilterOptions {
  maquinas: string[];
  fases: string[];
  turnos: string[];
  alternativos: string[];
}

export interface BeneficiamentoEffectiveFilters {
  dt_inicio: string | null;
  dt_fim: string | null;
  maquina: string | null;
  fase: string | null;
  turno: string | null;
  alternativo: string | null;
  q: string | null;
}

export interface BeneficiamentoKpis {
  ob_distintas: number;
  fases_concluidas: number;
  kg_total: number;
  mt_total: number;
  eficiencia_tempo_pct: number;
  reprocesso_kg_pct: number;
  desvio_tempo_min: number;
  produtividade_kg_h: number;
}

export interface BeneficiamentoGargalo {
  maquina: string;
  fase: string;
  fases_concluidas: number;
  kg_total: number;
  mt_total: number;
  desvio_min: number;
  eficiencia_tempo_pct: number;
  score: number;
}

export interface BeneficiamentoFaseCritica {
  fase: string;
  fases_concluidas: number;
  kg_total: number;
  eficiencia_tempo_pct: number;
  reprocesso_kg_pct: number;
}

export interface BeneficiamentoProdutoPrincipal {
  codigo: string;
  produto: string;
  artigo: string;
  cor: string;
  ob_distintas: number;
  fases_concluidas: number;
  kg_total: number;
  mt_total: number;
  reprocesso_kg_pct: number;
  produtividade_kg_h: number;
}

export interface BeneficiamentoTurnoRanking {
  turno_id: string | null;
  turno_label: string;
  ob_distintas: number;
  fases_concluidas: number;
  kg_total: number;
  mt_total: number;
  eficiencia_tempo_pct: number;
  reprocesso_kg_pct: number;
  produtividade_kg_h: number;
  min_real_medio: number;
  desvio_medio_min: number;
}

export interface BeneficiamentoRankings {
  gargalos: BeneficiamentoGargalo[];
  fases_criticas: BeneficiamentoFaseCritica[];
  produtos_principais: BeneficiamentoProdutoPrincipal[];
}

export interface BeneficiamentoSeriesPoint {
  date: string;
  kg_total?: number;
  eficiencia_tempo_pct?: number;
}

export interface BeneficiamentoSeries {
  volume_diario: { date: string; kg_total: number }[];
  eficiencia_diaria: { date: string; eficiencia_tempo_pct: number }[];
}

export interface BeneficiamentoOverview {
  generated_at: string;
  filters: { effective: BeneficiamentoEffectiveFilters };
  health: {
    status: string;
    source: string;
    max_data_fim: string | null;
    records: number;
    findings: string[];
  };
  kpis: BeneficiamentoKpis;
  rankings: BeneficiamentoRankings;
  series: BeneficiamentoSeries;
  filter_options: BeneficiamentoFilterOptions;
  turnos: BeneficiamentoTurnoRanking[];
  tingimento: Record<string, unknown>;
  interaction: { detail_endpoint: string; clickable_targets: string[] };
}

export type BeneficiamentoTargetType = "produto" | "maquina_fase" | "fase" | "turno" | "ob";

export interface BeneficiamentoDetailRecord {
  ob: string | null;
  seq: number | null;
  data_fim: string | null;
  fase: string | null;
  maquina: string | null;
  turno: string;
  alternativo: string | null;
  reduz: string | null;
  produto: string | null;
  artigo: string | null;
  cor: string | null;
  kg: number;
  mt: number;
  min_real: number;
  min_prev: number;
  desvio_min: number;
  reprocesso: number;
}

export interface BeneficiamentoTraceFase {
  seq: number;
  data_fim: string | null;
  fase: string | null;
  maquina: string | null;
  turno: string;
  kg: number;
  min_real: number;
  reprocesso: number;
}

export interface BeneficiamentoTraceOb {
  ob: string;
  fases: BeneficiamentoTraceFase[];
}

export interface BeneficiamentoDetailSummary {
  target_type: string;
  ob_distintas: number;
  fases_concluidas: number;
  kg_total: number;
  mt_total: number;
  eficiencia_tempo_pct: number;
  reprocesso_kg_pct: number;
  produtividade_kg_h: number;
  turnos: string[];
}

export interface BeneficiamentoDetail {
  generated_at: string;
  filters: { effective: Record<string, unknown> };
  target: { type: string; label: string };
  summary: BeneficiamentoDetailSummary;
  records: BeneficiamentoDetailRecord[];
  trace: BeneficiamentoTraceOb[];
  pagination: { page: number; limit: number; total: number; pages: number };
  raw_records: Record<string, unknown>[];
}

export interface BeneficiamentoOverviewParams {
  dt_inicio?: string;
  dt_fim?: string;
  maquina?: string;
  fase?: string;
  turno?: string;
  alternativo?: string;
  q?: string;
}

export interface BeneficiamentoDetailParams extends BeneficiamentoOverviewParams {
  target_type: BeneficiamentoTargetType;
  ob?: string;
  page?: number;
  limit?: number;
}

/* ============================================================================
   API — rotas reconciliadas com os routers reais do Orchestrator.
   ========================================================================== */

export const orchestratorApi = {
  // ── Automações ──
  listAutomations: (params?: { page?: number; per_page?: number; search?: string; sort?: string; order?: string }) =>
    api.get<Paginated<Automation>>(`/api/automations${qs({ ...params })}`).then((r) => r.items),
  listAllAutomations: () => api.get<Automation[]>("/api/automations/all"),
  getAutomation: (id: number) => api.get<Automation>(`/api/automations/${id}`),
  getAutomationOverview: (id: number) =>
    api.get<{ automation: Automation; metrics_24h: Record<string, number>; recent_executions: ExecutionSummary[] }>(
      `/api/automations/${id}/overview`,
    ),
  startAutomation: (id: number) => api.post<{ message: string; exec_id: string }>(`/api/automations/${id}/start`),
  pauseAutomation: (id: number) => api.post<{ message: string }>(`/api/automations/${id}/pause`),
  resumeAutomation: (id: number) => api.post<{ message: string }>(`/api/automations/${id}/resume`),
  setAutomationTestMode: (id: number, enabled: boolean) =>
    api.post<{ message: string }>(`/api/automations/${id}/test-mode${qs({ enabled })}`),
  setGlobalTestMode: (enabled: boolean) =>
    api.post<{ message: string }>(`/api/automations/test-mode/global${qs({ enabled })}`),
  pauseAll: () => api.post<{ message: string }>("/api/automations/control/pause-all"),
  resumeAll: () => api.post<{ message: string }>("/api/automations/control/resume-all"),

  // ── Execuções ──
  listExecutions: (params?: { page?: number; per_page?: number; status?: string; automation_id?: number }) =>
    api.get<Paginated<ExecutionSummary>>(`/api/executions${qs({ ...params })}`),
  recentExecutions: (limit = 10) =>
    api.get<ExecutionSummary[]>(`/api/executions/recent${qs({ limit })}`),
  getExecution: (id: string) => api.get<ExecutionDetail>(`/api/executions/${id}`),
  getExecutionLogs: (id: string, params?: { offset?: number; limit?: number }) =>
    api.get<{ lines: string[]; total_lines: number; offset: number; [k: string]: unknown }>(
      `/api/executions/${id}/logs${qs({ ...params })}`,
    ),
  stopExecution: (id: string) => api.post<{ message: string }>(`/api/executions/${id}/stop`),
  requeueExecution: (id: string, body?: { reason?: string; priority?: string }) =>
    api.post<QueueActionResponse>(`/api/executions/${id}/requeue`, body ?? {}),

  // ── Sistema ──
  getHealth: () => api.get<SystemHealth>("/api/system/health"),
  getWorkerStatus: () => api.get<WorkerStatus>("/api/system/worker/status"),
  getOverview: () => api.get<SystemOverview>("/api/system/overview"),
  getBaseline: () => api.get<BaselineStatus>("/api/system/baseline"),
  getHistory: (hours = 24) => api.get<SystemHistory>(`/api/system/history${qs({ hours })}`),
  getSystemMetricsDaily: (days = 14) =>
    api.get<SystemMetricsDaily>(`/api/system/metrics/daily${qs({ days })}`),
  getScheduledJobs: () => api.get<ScheduledJob[]>("/api/system/scheduler/jobs"),
  runCheckpoint: () => api.post<{ message: string }>("/api/system/checkpoint"),
  runPurge: () => api.post<{ message: string }>("/api/system/purge"),
  recoverWorker: () => api.post<{ message: string }>("/api/system/worker/recover"),
  reloadScheduler: () => api.post<{ message: string }>("/api/system/scheduler/reload"),

  // ── Portfólio ──
  getPortfolioHealth: () => api.get<PortfolioHealth>("/api/portfolio/health"),

  // ── Beneficiamento ──
  getBeneficiamentoDashboard: () => api.get<BeneficiamentoDashboard>("/api/beneficiamento/dashboard"),
  getBeneficiamentoHealth: () => api.get<BeneficiamentoHealth>("/api/beneficiamento/health"),
  getBeneficiamentoOverview: (params?: BeneficiamentoOverviewParams) =>
    api.get<BeneficiamentoOverview>(`/api/beneficiamento/overview${qs({ ...params })}`),
  getBeneficiamentoDetail: (params: BeneficiamentoDetailParams) =>
    api.get<BeneficiamentoDetail>(`/api/beneficiamento/detail${qs({ ...params })}`),
  refreshBeneficiamento: (period: string) =>
    api.post<Record<string, unknown>>(`/api/beneficiamento/refresh${qs({ period })}`),
};
