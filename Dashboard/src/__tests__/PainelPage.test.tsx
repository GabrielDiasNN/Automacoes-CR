import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi } from "../api/orchestrator";
import { ToastProvider } from "../components/ui";
import { PainelPage } from "../pages/PainelPage";

const OVERVIEW_MOCK = {
  generated_at: "22/11/2026 17:00:00",
  version: "1.0.0",
  kpis: {
    active_automations: 6,
    success_24h: 12,
    errors_24h: 0,
    pending_now: 1,
    next_window: "22/11/2026 18:00:00",
  },
  health: {
    status: "healthy",
    timestamp: "22/11/2026 17:00:00",
    database: "online",
    scheduler: "executando",
    worker: {
      is_alive: true,
      pid: 1234,
      instance_id: "w-1",
      host: "localhost",
      last_ping: "22/11/2026 17:00:00",
      uptime_seconds: 3600,
      tasks_completed: 12,
      tasks_failed: 0,
      active_tasks: 0,
      pool_saturated_seconds: 0,
      version: "1.0.0",
    },
    pending_tasks: 1,
    disk_usage_mb: 100,
    wal_size_mb: 0.5,
    cpu_usage: 12,
    ram_usage_percent: 45,
  },
  status_breakdown: {},
  jobs: [],
  recent: [
    {
      id: "EXEC_99",
      automation_id: 4,
      automation_name: "OBs Paradas Fase",
      status: "SUCCESS" as const,
      priority: "HIGH",
      retry_count: 0,
      max_retries: 2,
      queue_group: "oracle",
      failure_reason: null,
      recovery_action: null,
      exit_code: 0,
      requested_by: "SCHEDULER",
      started_at: "22/11/2026 14:00:00",
      finished_at: "22/11/2026 14:00:05",
      duration_seconds: 5,
      operator_attention_required: false,
      operator_severity: null,
      operator_score: 0,
      operator_reason_summary: null,
      operator_action_code: null,
      operator_action_label: null,
      operator_action_hint: null,
      requeue_allowed: false,
      requeue_block_reason: null,
      stop_allowed: false,
      related_execution_id: null,
      related_execution_status: null,
      related_queue_group: null,
    },
  ],
  automations: [],
  top_failures: [],
  scheduler: { running: true, jobs_loaded: 6 },
  queue: { active_count: 0, by_status: {}, active_by_priority: {} },
  portfolio: null,
  diagnostics: {
    overall_status: "healthy",
    findings: [],
    operational_baseline: {
      evaluated_at: "22/11/2026 17:00:00",
      status: "healthy" as const,
      attention_count: 0,
      incident_count: 0,
      recommended_action: null,
      metrics: [],
    },
    failure_hotspots: [],
  },
};

function renderPainel() {
  return render(
    <MemoryRouter initialEntries={["/painel"]}>
      <ToastProvider>
        <Routes>
          <Route path="/painel" element={<PainelPage />} />
          <Route path="/pcp" element={<div>DESTINO_PCP</div>} />
          <Route path="/execucoes" element={<div>DESTINO_EXECUCOES</div>} />
          <Route path="/beneficiamento" element={<div>DESTINO_BENEFICIAMENTO</div>} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("PainelPage — Visão Geral Command Center", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("exibe KPIs de produção, radar de PCP e navega ao clicar nos itens", async () => {
    vi.spyOn(orchestratorApi, "getOverview").mockResolvedValue(OVERVIEW_MOCK as never);
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
      items: [
        {
          slug: "obs-paradas-fase",
          codigo: "OBP-04",
          nome: "OBs Paradas Fase",
          titulo: "OBs Paradas por Fase",
          setor: "Beneficiamento & Fases",
          modo: "producao",
          destinos: ["whatsapp", "dashboard"],
          has_snapshot: true,
          generated_at: "2026-11-22T14:00:00Z",
          age_minutes: 30,
          total_rows: 250,
          excecoes_count: 250,
          cards_count: 17,
          kpis: {},
        },
      ],
    });
    vi.spyOn(orchestratorApi, "getBeneficiamentoOverview").mockResolvedValue({
      health: { status: "healthy" },
      kpis: {
        kg_total: 125000,
        ob_distintas: 420,
        eficiencia_tempo_pct: 78.4,
        reprocesso_kg_pct: 1.5,
        produtividade_kg_h: 512,
      },
    } as never);

    renderPainel();

    expect(await screen.findByText("125.000")).toBeInTheDocument();
    expect(screen.getByText("17 cards")).toBeInTheDocument();
    expect(screen.getByText("250 exceções")).toBeInTheDocument();
    expect(screen.getByText("Sucesso")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Somente alertas" }));
    expect(screen.getByRole("button", { name: "Mostrar todos" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar todos" }));

    fireEvent.click(screen.getByText("17 cards"));
    expect(await screen.findByText("DESTINO_PCP")).toBeInTheDocument();
  });
});
