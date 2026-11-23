import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi, type Automation } from "../api/orchestrator";
import { ToastProvider } from "../components/ui";
import { ScheduleEditorDrawer } from "../components/ScheduleEditorDrawer";

const BASE_AUTO: Automation = {
  id: 4,
  name: "OBs Paradas Fase",
  description: "Monitora OBs paradas",
  script_path: "./OBs Paradas Fase/run.ps1",
  schedule: JSON.stringify({
    schedule_version: 2,
    schedule_type: "daily",
    times: [
      { h: 5, m: 30 },
      { h: 14, m: 0 },
    ],
    timezone: "America/Sao_Paulo",
  }),
  max_runtime_minutes: 15,
  max_retries: 1,
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
  last_execution_id: "EXEC_1",
  last_execution_started_at: null,
  last_execution_finished_at: null,
  last_execution_duration_seconds: 5,
  last_failure_reason: null,
  last_recovery_action: null,
  last_requested_by: null,
  schedule_type: "daily",
  schedule_summary: "Diário às 05:30, 14:00",
  next_runs_preview: [],
  active_execution_count: 0,
  success_24h: 2,
  failures_24h: 0,
  timeouts_24h: 0,
  error_24h: 0,
  avg_duration_24h_seconds: 5,
  pending_count: 0,
  operational_state: "healthy",
  validated: true,
  backup_path: null,
  audit_id: null,
};

describe("ScheduleEditorDrawer", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("decodifica times [{h,m}] sem [object Object], simula e salva no formato do backend", async () => {
    const previewSpy = vi.spyOn(orchestratorApi, "previewSchedule").mockResolvedValue({
      valid: true,
      normalized_schedule: "{}",
      schedule_type: "daily",
      schedule_summary: "Diário às 05:30, 14:00",
      next_runs_preview: ["23/11/2026 05:30:00", "23/11/2026 14:00:00"],
      errors: [],
    });
    const updateSpy = vi.spyOn(orchestratorApi, "updateAutomation").mockResolvedValue(BASE_AUTO);
    const onSaved = vi.fn();
    const onClose = vi.fn();

    render(
      <ToastProvider>
        <ScheduleEditorDrawer automation={BASE_AUTO} onClose={onClose} onSaved={onSaved} />
      </ToastProvider>,
    );

    const timesInput = screen.getByLabelText<HTMLInputElement>("Horários de execução");
    expect(timesInput.value).toBe("05:30, 14:00");

    fireEvent.click(screen.getByRole("button", { name: /Simular próximas execuções/ }));
    expect(await screen.findByText("23/11/2026 05:30:00")).toBeInTheDocument();
    expect(previewSpy).toHaveBeenCalledWith(
      JSON.stringify({
        schedule_version: 2,
        schedule_type: "daily",
        times: [
          { h: 5, m: 30 },
          { h: 14, m: 0 },
        ],
        timezone: "America/Sao_Paulo",
      }),
      5,
    );

    fireEvent.click(screen.getByRole("button", { name: /Salvar alterações/ }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledTimes(1));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("preserva e edita agenda cron sem rebaixar para manual", async () => {
    const cronAuto: Automation = {
      ...BASE_AUTO,
      schedule_type: "cron",
      schedule: JSON.stringify({
        schedule_version: 2,
        schedule_type: "cron",
        cron_expression: ["0 5-19/2 * * 1-5", "0 5-13/2 * * 6"],
        timezone: "America/Sao_Paulo",
      }),
    };
    const updateSpy = vi.spyOn(orchestratorApi, "updateAutomation").mockResolvedValue(cronAuto);
    const onSaved = vi.fn();
    const onClose = vi.fn();

    render(
      <ToastProvider>
        <ScheduleEditorDrawer automation={cronAuto} onClose={onClose} onSaved={onSaved} />
      </ToastProvider>,
    );

    const cronInput = screen.getByLabelText<HTMLInputElement>("Expressões cron");
    expect(cronInput.value).toBe("0 5-19/2 * * 1-5; 0 5-13/2 * * 6");

    fireEvent.click(screen.getByRole("button", { name: /Salvar alterações/ }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledTimes(1));
    const payload = updateSpy.mock.calls[0]![1];
    expect(payload.schedule).toBe(
      JSON.stringify({
        schedule_version: 2,
        schedule_type: "cron",
        cron_expression: ["0 5-19/2 * * 1-5", "0 5-13/2 * * 6"],
        timezone: "America/Sao_Paulo",
      }),
    );
  });

  it("preserva agenda avançada (monthly) sem sobrescrever schedule ao salvar SLA", async () => {
    const monthlyAuto: Automation = {
      ...BASE_AUTO,
      schedule_type: "monthly",
      schedule_summary: "Mensal dia(s) 1 às 08:00",
      schedule: JSON.stringify({
        schedule_version: 2,
        schedule_type: "monthly",
        days_of_month: [1],
        times: [{ h: 8, m: 0 }],
        timezone: "America/Sao_Paulo",
      }),
    };
    const updateSpy = vi.spyOn(orchestratorApi, "updateAutomation").mockResolvedValue(monthlyAuto);

    render(
      <ToastProvider>
        <ScheduleEditorDrawer automation={monthlyAuto} onClose={vi.fn()} onSaved={vi.fn()} />
      </ToastProvider>,
    );

    expect(screen.getByText(/será preservada inalterada/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Salvar alterações/ }));
    await waitFor(() => expect(updateSpy).toHaveBeenCalledTimes(1));
    const payload = updateSpy.mock.calls[0]![1];
    expect("schedule" in payload).toBe(false);
  });
});
