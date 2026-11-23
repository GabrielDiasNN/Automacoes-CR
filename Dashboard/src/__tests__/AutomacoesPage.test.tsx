import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi, type Automation } from "../api/orchestrator";
import { ToastProvider } from "../components/ui";
import { AutomacoesPage } from "../pages/AutomacoesPage";

const AUTOS: Automation[] = [
  {
    id: 4,
    name: "OBs Paradas Fase",
    description: "Monitora OBs paradas",
    script_path: "./OBs Paradas Fase/run.ps1",
    schedule: '{"schedule_version":2,"schedule_type":"daily","times":[{"h":5,"m":30}],"timezone":"America/Sao_Paulo"}',
    max_runtime_minutes: 15,
    max_retries: 0,
    cooldown_minutes: 0,
    queue_group: "oracle",
    sla_minutes: 20,
    enabled: true,
    test_mode: false,
    notification_channels: "whatsapp",
    created_at: "2026-01-01 00:00:00",
    updated_at: null,
    next_run: "23/11/2026 05:30:00",
    last_status: "SUCCESS",
    last_execution_id: "EXEC_4",
    last_execution_started_at: null,
    last_execution_finished_at: null,
    last_execution_duration_seconds: 4,
    last_failure_reason: null,
    last_recovery_action: null,
    last_requested_by: null,
    schedule_type: "daily",
    schedule_summary: "Diário às 05:30",
    next_runs_preview: [],
    active_execution_count: 0,
    success_24h: 2,
    failures_24h: 0,
    timeouts_24h: 0,
    error_24h: 0,
    avg_duration_24h_seconds: 4,
    pending_count: 0,
    operational_state: "healthy",
    validated: true,
    backup_path: null,
    audit_id: null,
  },
];

function renderAutomacoes() {
  return render(
    <MemoryRouter initialEntries={["/automacoes"]}>
      <ToastProvider>
        <Routes>
          <Route path="/automacoes" element={<AutomacoesPage />} />
          <Route path="/pcp" element={<div>ROTA_PCP</div>} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("AutomacoesPage — controles de agenda, sandbox e disparo", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("alterna sandbox, abre editor de agenda e exige confirmação no disparo", async () => {
    vi.spyOn(orchestratorApi, "listAllAutomations").mockResolvedValue(AUTOS);
    vi.spyOn(orchestratorApi, "getPortfolioHealth").mockResolvedValue({ items: [] } as never);
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
      items: [
        {
          slug: "obs-paradas-fase",
          nome: "OBs Paradas Fase",
          titulo: "OBs Paradas Fase",
          automation_name: "OBs Paradas Fase",
          modo: "producao",
          destinos: ["dashboard"],
          has_snapshot: true,
          generated_at: null,
          age_minutes: null,
          total_rows: 10,
          excecoes_count: 10,
          kpis: {},
        },
      ],
    });
    const sandboxSpy = vi
      .spyOn(orchestratorApi, "setAutomationTestMode")
      .mockResolvedValue({ message: "Sandbox ativado" });
    const startSpy = vi
      .spyOn(orchestratorApi, "startAutomation")
      .mockResolvedValue({ message: "Enfileirada", exec_id: "EXEC_NEW_1" });

    renderAutomacoes();

    expect(await screen.findByText("Monitora OBs paradas")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Alternar modo sandbox de OBs Paradas Fase/ }));
    await waitFor(() => expect(sandboxSpy).toHaveBeenCalledWith(4, true));

    fireEvent.click(screen.getByRole("button", { name: /Configurar agenda de OBs Paradas Fase/ }));
    expect(await screen.findByText("Recorrência e Horários")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    fireEvent.click(screen.getByRole("button", { name: "Disparar OBs Paradas Fase" }));
    expect(await screen.findByText("Disparar automação")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Disparar" }));
    await waitFor(() => expect(startSpy).toHaveBeenCalledWith(4));
  });
});
