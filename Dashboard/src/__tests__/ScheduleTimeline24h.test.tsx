import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Automation } from "../api/orchestrator";
import { ScheduleTimeline24h } from "../components/ScheduleTimeline24h";

function makeAutomation(overrides: Partial<Automation> & { id: number; name: string }): Automation {
  return {
    description: null,
    script_path: "./run.ps1",
    schedule: null,
    max_runtime_minutes: 15,
    max_retries: 0,
    cooldown_minutes: 0,
    queue_group: "oracle",
    sla_minutes: 20,
    enabled: true,
    test_mode: false,
    notification_channels: null,
    created_at: "2026-01-01 00:00:00",
    updated_at: null,
    next_run: null,
    last_status: "SUCCESS",
    last_execution_id: null,
    last_execution_started_at: null,
    last_execution_finished_at: null,
    last_execution_duration_seconds: null,
    last_failure_reason: null,
    last_recovery_action: null,
    last_requested_by: null,
    schedule_type: "daily",
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

describe("ScheduleTimeline24h", () => {
  it("renderiza horários nos formatos {h,m} e HH:MM na régua 00h..23h ignorando pausadas", () => {
    const autos: Automation[] = [
      makeAutomation({
        id: 1,
        name: "OBs Paradas Fase",
        schedule: JSON.stringify({
          schedule_version: 2,
          schedule_type: "daily",
          times: [{ h: 5, m: 30 }, { h: 14, m: 0 }],
        }),
      }),
      makeAutomation({
        id: 2,
        name: "Estoque Crítico",
        schedule: JSON.stringify({
          schedule_version: 2,
          schedule_type: "daily",
          times: ["08:15"],
        }),
      }),
      makeAutomation({
        id: 3,
        name: "Pausada Ignorada",
        enabled: false,
        schedule: JSON.stringify({
          schedule_version: 2,
          schedule_type: "daily",
          times: [{ h: 5, m: 45 }],
        }),
      }),
    ];

    render(<ScheduleTimeline24h automations={autos} onSelectAutomation={vi.fn()} />);

    expect(screen.getByText("00h")).toBeInTheDocument();
    expect(screen.getByText("23h")).toBeInTheDocument();
    expect(screen.getByText("3 disparos ativos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de OBs Paradas Fase às 05:30" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de OBs Paradas Fase às 14:00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de Estoque Crítico às 08:15" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pausada Ignorada/ })).not.toBeInTheDocument();
  });

  it("detecta e destaca janela congestionada quando há >= 2 disparos na mesma hora", () => {
    const autos: Automation[] = [
      makeAutomation({
        id: 1,
        name: "Auto A",
        schedule: JSON.stringify({ schedule_type: "daily", times: [{ h: 7, m: 0 }] }),
      }),
      makeAutomation({
        id: 2,
        name: "Auto B",
        schedule: JSON.stringify({ schedule_type: "daily", times: [{ h: 7, m: 30 }] }),
      }),
      makeAutomation({
        id: 3,
        name: "Auto C",
        schedule: JSON.stringify({ schedule_type: "daily", times: ["10:00"] }),
      }),
    ];

    const { container } = render(<ScheduleTimeline24h automations={autos} onSelectAutomation={vi.fn()} />);

    expect(screen.getByText("1 hora congestionada (≥ 2 disparos)")).toBeInTheDocument();
    const hour7 = container.querySelector('[data-hour="7"]');
    const hour10 = container.querySelector('[data-hour="10"]');
    expect(hour7).toHaveAttribute("data-congested", "true");
    expect(hour10).toHaveAttribute("data-congested", "false");
  });

  it("dispara onSelectAutomation ao clicar em um item da timeline", () => {
    const onSelect = vi.fn();
    const target = makeAutomation({
      id: 9,
      name: "Carteira PCP",
      schedule: JSON.stringify({ schedule_type: "daily", times: [{ h: 6, m: 45 }] }),
    });

    render(<ScheduleTimeline24h automations={[target]} onSelectAutomation={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Editar agenda de Carteira PCP às 06:45" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(target);
  });

  it("exibe estado vazio e ignora schedules malformados sem gerar 00:00 fantasma", () => {
    const autos: Automation[] = [
      makeAutomation({ id: 10, name: "Schedule Null String", schedule: "null" }),
      makeAutomation({ id: 11, name: "JSON Invalido", schedule: "{quebrado" }),
      makeAutomation({
        id: 12,
        name: "Entradas Coerciveis",
        schedule: JSON.stringify({
          schedule_type: "daily",
          times: [{ h: null, m: null }, { h: "", m: "" }, { h: false, m: true }],
        }),
      }),
    ];

    render(<ScheduleTimeline24h automations={autos} onSelectAutomation={vi.fn()} />);

    expect(screen.getByText("0 disparos ativos")).toBeInTheDocument();
    expect(screen.getByText("Nenhum disparo com horário fixo ativo nas 24h.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("extrai horários de agendas cron (string/array) e interval com janela", () => {
    const autos: Automation[] = [
      makeAutomation({
        id: 20,
        name: "Quimicos Atributo 4",
        schedule_type: "cron",
        schedule: JSON.stringify({
          schedule_version: 2,
          schedule_type: "cron",
          cron_expression: ["0 7,11 * * 1-5", "30 14 * * 1-5"],
          timezone: "America/Sao_Paulo",
        }),
      }),
      makeAutomation({
        id: 21,
        name: "Sentinela Intervalo",
        schedule_type: "interval",
        schedule: JSON.stringify({
          schedule_version: 2,
          schedule_type: "interval",
          interval_minutes: 120,
          start_time: "08:00",
          end_time: "12:00",
        }),
      }),
    ];

    render(<ScheduleTimeline24h automations={autos} onSelectAutomation={vi.fn()} />);

    expect(screen.getByText("6 disparos ativos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de Quimicos Atributo 4 às 07:00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de Quimicos Atributo 4 às 11:00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de Quimicos Atributo 4 às 14:30" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de Sentinela Intervalo às 08:00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de Sentinela Intervalo às 10:00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar agenda de Sentinela Intervalo às 12:00" })).toBeInTheDocument();
  });
});
