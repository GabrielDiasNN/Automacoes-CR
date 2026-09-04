import { describe, expect, it } from "vitest";
import type { Automation, PortfolioHealthItem } from "../api/orchestrator";
import { attentionRank } from "../pages/AutomacoesPage";

function makeAutomation(overrides: Partial<Automation> = {}): Automation {
  return {
    id: 1,
    name: "Automação de teste",
    description: null,
    script_path: "run.ps1",
    schedule: null,
    max_runtime_minutes: 30,
    max_retries: 3,
    cooldown_minutes: 5,
    queue_group: null,
    sla_minutes: 60,
    enabled: true,
    test_mode: false,
    notification_channels: null,
    created_at: "2026-01-01T00:00:00",
    updated_at: null,
    next_run: null,
    last_status: null,
    last_execution_id: null,
    last_execution_started_at: null,
    last_execution_finished_at: null,
    last_execution_duration_seconds: null,
    last_failure_reason: null,
    last_recovery_action: null,
    last_requested_by: null,
    schedule_type: null,
    schedule_summary: null,
    next_runs_preview: [],
    active_execution_count: 0,
    success_24h: 0,
    failures_24h: 0,
    timeouts_24h: 0,
    error_24h: 0,
    avg_duration_24h_seconds: null,
    pending_count: 0,
    operational_state: "healthy",
    validated: true,
    backup_path: null,
    audit_id: null,
    ...overrides,
  };
}

function makePortfolioItem(overrides: Partial<PortfolioHealthItem> = {}): PortfolioHealthItem {
  return {
    catalog_id: "cat-1",
    automation_id: 1,
    name: "Automação de teste",
    slug: "automacao-teste",
    criticality: "low",
    owner_area: null,
    runtime: "powershell",
    enabled: true,
    queue_group: null,
    sla_minutes: 60,
    health_status: "healthy",
    sla_state: "ok",
    docs_status: "ok",
    drift_status: "ok",
    drift_count: 0,
    runbook_path: null,
    readme_path: null,
    context_path: null,
    next_run: null,
    schedule_summary: null,
    schedule_lag_minutes: null,
    schedule_lag_seconds: null,
    last_status: null,
    last_success_at: null,
    last_failure_at: null,
    last_success_age_minutes: null,
    last_failure_age_minutes: null,
    last_success_age_seconds: null,
    last_failure_age_seconds: null,
    review_status: "ok",
    review_reasons: [],
    dependency_status: { oracle: "ok", outlook: "ok", whatsapp: "ok" },
    ...overrides,
  };
}

// Achado nº 4 do handoff de 04/09/2026: `attentionRank` removeu as comparações
// mortas (`sla_state === "violated"/"at_risk"`, valores que o backend nunca
// emite) mas não as substituiu pelos valores reais (`breached`/`recovering`),
// deixando o SLA de fora da ordenação. Ordem fixada pelo supervisor:
// attention > breached > high > recovering > medium > resto.
describe("attentionRank (achado nº 4 — SLA fora da ordenação)", () => {
  it("estado operacional 'attention' vem antes de tudo, inclusive SLA breached", () => {
    const attention = attentionRank(makeAutomation({ operational_state: "attention" }), makePortfolioItem({ sla_state: "breached" }));
    const breached = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "breached" }));
    expect(attention).toBeLessThan(breached);
  });

  it("SLA breached vem antes de criticidade high (sem attention)", () => {
    const breached = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "breached", criticality: "low" }));
    const high = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "ok", criticality: "high" }));
    expect(breached).toBeLessThan(high);
  });

  it("criticidade high vem antes de SLA recovering", () => {
    const high = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "ok", criticality: "high" }));
    const recovering = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "recovering", criticality: "low" }));
    expect(high).toBeLessThan(recovering);
  });

  it("SLA recovering vem antes de criticidade medium", () => {
    const recovering = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "recovering", criticality: "low" }));
    const medium = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "ok", criticality: "medium" }));
    expect(recovering).toBeLessThan(medium);
  });

  it("criticidade medium vem antes do resto (sla ok, criticidade low)", () => {
    const medium = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "ok", criticality: "medium" }));
    const resto = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "ok", criticality: "low" }));
    expect(medium).toBeLessThan(resto);
  });

  it("sem dado de portfólio (undefined) cai no rank mais baixo", () => {
    const semPortfolio = attentionRank(makeAutomation(), undefined);
    const resto = attentionRank(makeAutomation(), makePortfolioItem({ sla_state: "ok", criticality: "low" }));
    expect(semPortfolio).toBe(resto);
  });
});
