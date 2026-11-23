import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi, type ExecutionSummary } from "../api/orchestrator";
import { AlertsBellPopover } from "../components/AlertsBellPopover";

function LocationDisplay() {
  const loc = useLocation();
  return <div data-testid="current-location">{`${loc.pathname}${loc.search}`}</div>;
}

function makeExec(overrides: Partial<ExecutionSummary>): ExecutionSummary {
  return {
    id: "exec-1",
    automation_id: 10,
    automation_name: "Automação Alpha",
    status: "SUCCESS",
    priority: "normal",
    retry_count: 0,
    max_retries: 2,
    queue_group: null,
    failure_reason: null,
    recovery_action: null,
    exit_code: 0,
    requested_by: "scheduler",
    started_at: "2026-11-22 10:00:00",
    finished_at: "2026-11-22 10:01:00",
    duration_seconds: 60,
    operator_attention_required: false,
    operator_severity: "NORMAL",
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
    ...overrides,
  };
}

function mockOverview(options?: {
  recent?: ExecutionSummary[];
  healthStatus?: "healthy" | "degraded" | "unhealthy" | "ok";
  baselineStatus?: "healthy" | "attention" | "incident";
}) {
  const payload = {
    generated_at: "2026-11-22 10:05:00",
    version: "5.0.0",
    health: {
      status: options?.healthStatus ?? "healthy",
    },
    recent: options?.recent ?? [],
    diagnostics: {
      overall_status: options?.healthStatus ?? "healthy",
      findings: [],
      operational_baseline: {
        evaluated_at: "2026-11-22 10:05:00",
        status: options?.baselineStatus ?? "healthy",
        attention_count: options?.baselineStatus === "attention" ? 1 : 0,
        incident_count: options?.baselineStatus === "incident" ? 1 : 0,
        recommended_action: options?.baselineStatus && options.baselineStatus !== "healthy" ? "Verificar fila" : null,
        metrics: [],
      },
      failure_hotspots: [],
    },
  };
  return vi
    .spyOn(orchestratorApi, "getOverview")
    .mockResolvedValue(payload as unknown as Awaited<ReturnType<typeof orchestratorApi.getOverview>>);
}

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={["/painel"]}>
      <Routes>
        <Route
          path="*"
          element={
            <div>
              <AlertsBellPopover />
              <LocationDisplay />
            </div>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AlertsBellPopover — Central de Alertas na Topbar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("exibe badge numérico, agrupa alertas de falhas, PCP e saúde/baseline e navega ao clicar", async () => {
    mockOverview({
      healthStatus: "degraded",
      baselineStatus: "attention",
      recent: [
        makeExec({ id: "exec-ok", status: "SUCCESS", automation_name: "Sem Alerta" }),
        makeExec({ id: "exec-err", status: "ERROR", automation_name: "ETL Falha", failure_reason: "ORA-01017" }),
        makeExec({
          id: "exec-att",
          status: "PARTIAL",
          automation_name: "Carga Parcial",
          operator_attention_required: true,
          operator_reason_summary: "Atenção do operador",
        }),
      ],
    });
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
      items: [
        {
          slug: "rama-risco-atraso",
          codigo: "CP-01",
          nome: "Risco Atraso Ramas",
          titulo: "Risco Atraso Ramas",
          setor: "Acabamento",
          modo: "producao",
          destinos: ["dashboard"],
          has_snapshot: true,
          generated_at: null,
          age_minutes: 5,
          total_rows: 10,
          excecoes_count: 3,
          kpis: {},
        },
        {
          slug: "sem-excecoes",
          codigo: "CP-02",
          nome: "Limpa",
          titulo: "Limpa",
          modo: "producao",
          destinos: ["dashboard"],
          has_snapshot: true,
          generated_at: null,
          age_minutes: 5,
          total_rows: 10,
          excecoes_count: 0,
          kpis: {},
        },
      ],
    });

    renderWithRouter();

    const trigger = screen.getByRole("button", { name: "Central de alertas" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");

    // 2 falhas + 1 PCP + 2 sistema (health + baseline) = 5 alertas
    expect(await screen.findByTestId("alerts-bell-badge")).toHaveTextContent("5");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const dialog = screen.getByRole("dialog", { name: "Central de alertas" });
    expect(dialog).toBeInTheDocument();

    // Não deve conter botões aninhados (a11y)
    expect(dialog.querySelectorAll("button button")).toHaveLength(0);

    // Navega para /execucoes?exec_id=exec-err e fecha o popover
    fireEvent.click(screen.getByRole("button", { name: /ETL Falha/i }));
    expect(screen.queryByRole("dialog", { name: "Central de alertas" })).not.toBeInTheDocument();
    expect(screen.getByTestId("current-location")).toHaveTextContent("/execucoes?exec_id=exec-err");

    // Reabre e navega para /pcp?slug=rama-risco-atraso
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole("button", { name: /CP-01 · Risco Atraso Ramas/i }));
    expect(screen.queryByRole("dialog", { name: "Central de alertas" })).not.toBeInTheDocument();
    expect(screen.getByTestId("current-location")).toHaveTextContent("/pcp?slug=rama-risco-atraso");

    // Reabre e navega para /sistema
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole("button", { name: /Saúde do sistema: degraded/i }));
    expect(screen.queryByRole("dialog", { name: "Central de alertas" })).not.toBeInTheDocument();
    expect(screen.getByTestId("current-location")).toHaveTextContent("/sistema");
  });

  it("fecha o popover com Escape e clique fora", async () => {
    mockOverview();
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({ items: [] });

    renderWithRouter();
    const trigger = screen.getByRole("button", { name: "Central de alertas" });

    // Sem alertas: não exibe badge
    await waitFor(() => {
      expect(screen.queryByTestId("alerts-bell-badge")).not.toBeInTheDocument();
    });

    // Abre e fecha com Escape
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Central de alertas" })).toBeInTheDocument();
    expect(await screen.findByText("Nenhum alerta ativo no momento.")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Central de alertas" })).not.toBeInTheDocument();

    // Abre e fecha com clique fora
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Central de alertas" })).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog", { name: "Central de alertas" })).not.toBeInTheDocument();
  });

  it("preserva alertas ativos já conhecidos em falha transitória parcial ou total da API", async () => {
    const overviewSpy = mockOverview({
      recent: [makeExec({ id: "exec-err", status: "ERROR", automation_name: "ETL Persistente" })],
    });
    const promovidasSpy = vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
      items: [
        {
          slug: "pcp-persistente",
          codigo: "CP-99",
          nome: "PCP Persistente",
          titulo: "PCP Persistente",
          modo: "producao",
          destinos: ["dashboard"],
          has_snapshot: true,
          generated_at: null,
          age_minutes: 2,
          total_rows: 5,
          excecoes_count: 1,
          kpis: {},
        },
      ],
    });

    renderWithRouter();
    expect(await screen.findByTestId("alerts-bell-badge")).toHaveTextContent("2");

    // Simula falha transitória total ao reabrir o popover
    overviewSpy.mockRejectedValueOnce(new Error("503 Service Unavailable"));
    promovidasSpy.mockRejectedValueOnce(new Error("timeout"));

    const trigger = screen.getByRole("button", { name: "Central de alertas" });
    fireEvent.click(trigger);

    expect(await screen.findByRole("button", { name: /ETL Persistente/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /CP-99 · PCP Persistente/i })).toBeInTheDocument();
    expect(screen.getByTestId("alerts-bell-badge")).toHaveTextContent("2");
  });
});
