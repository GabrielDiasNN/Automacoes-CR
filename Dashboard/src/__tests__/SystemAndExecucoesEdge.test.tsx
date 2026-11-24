import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.hoisted(() => {
  if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});
import {
  orchestratorApi,
  type ExecutionSummary,
  type Paginated,
} from "../api/orchestrator";
import { ToastProvider } from "../components/ui";
import { TableDensityProvider } from "../context/TableDensityContext";
import { _clearCache } from "../lib/resourceCache";
import { ExecucoesPage } from "../pages/ExecucoesPage";
import { SystemPage } from "../pages/SystemPage";
import executionsPageFixture from "./fixtures/executions-page.json";
import systemOverviewFixture from "./fixtures/system-overview.json";

type SystemOverview = Awaited<ReturnType<typeof orchestratorApi.getOverview>>;
const SYSTEM_OVERVIEW = systemOverviewFixture as unknown as SystemOverview;
const EXECUTIONS_PAGE = executionsPageFixture as unknown as Paginated<ExecutionSummary>;

const EMPTY_HISTORY = {
  generated_at: "2026-11-22 18:00:00",
  hours: 24,
  points: 0,
  items: [],
};

const VERSION_MOCK = {
  version: "1.0.0",
  schema_version: "1",
  contract_version: "1",
  python_version: "3.12",
  uptime_seconds: 100,
  started_at: "2026-11-22 00:00:00",
  max_workers: 4,
  allowed_origins: [] as string[],
};

function renderSystem() {
  return render(
    <MemoryRouter initialEntries={["/sistema"]}>
      <TableDensityProvider>
        <ToastProvider>
          <Routes>
            <Route path="/sistema" element={<SystemPage />} />
          </Routes>
        </ToastProvider>
      </TableDensityProvider>
    </MemoryRouter>,
  );
}

function renderExecucoes() {
  return render(
    <MemoryRouter initialEntries={["/execucoes"]}>
      <TableDensityProvider>
        <ToastProvider>
          <Routes>
            <Route path="/execucoes" element={<ExecucoesPage />} />
          </Routes>
        </ToastProvider>
      </TableDensityProvider>
    </MemoryRouter>,
  );
}

describe("SystemPage — bordas (WAL Checkpoint e ErrorState)", () => {
  afterEach(() => {
    _clearCache();
    vi.restoreAllMocks();
  });

  it("exibe ErrorState quando getOverview falha", async () => {
    vi.spyOn(orchestratorApi, "getOverview").mockRejectedValue(new Error("Falha ao carregar overview"));
    vi.spyOn(orchestratorApi, "getHistory").mockResolvedValue(EMPTY_HISTORY);
    vi.spyOn(orchestratorApi, "getVersion").mockResolvedValue(VERSION_MOCK);
    vi.spyOn(orchestratorApi, "getUptime").mockResolvedValue({
      uptime_seconds: 100,
      uptime_human: "1m",
      started_at: "2026-11-22 00:00:00",
    });
    vi.spyOn(orchestratorApi, "getDrift").mockResolvedValue({
      summary: { total_items: 0, items_with_drift: 0 },
      items: [],
    } as never);
    vi.spyOn(orchestratorApi, "getAuditLog").mockResolvedValue([]);

    renderSystem();

    expect(await screen.findByText("Falha ao carregar overview")).toBeInTheDocument();
  });

  it("chama runCheckpoint ao clicar em WAL Checkpoint", async () => {
    vi.spyOn(orchestratorApi, "getOverview").mockResolvedValue(SYSTEM_OVERVIEW);
    vi.spyOn(orchestratorApi, "getHistory").mockResolvedValue(EMPTY_HISTORY);
    vi.spyOn(orchestratorApi, "getVersion").mockResolvedValue(VERSION_MOCK);
    vi.spyOn(orchestratorApi, "getUptime").mockResolvedValue({
      uptime_seconds: 100,
      uptime_human: "1m",
      started_at: "2026-11-22 00:00:00",
    });
    vi.spyOn(orchestratorApi, "getDrift").mockResolvedValue({
      summary: { total_items: 0, items_with_drift: 0 },
      items: [],
    } as never);
    vi.spyOn(orchestratorApi, "getAuditLog").mockResolvedValue([]);
    const checkpointSpy = vi
      .spyOn(orchestratorApi, "runCheckpoint")
      .mockResolvedValue({ message: "Checkpoint concluído" });

    renderSystem();

    const btn = await screen.findByRole("button", { name: /WAL Checkpoint/i });
    fireEvent.click(btn);

    await waitFor(() => expect(checkpointSpy).toHaveBeenCalledTimes(1));
  });
});

describe("ExecucoesPage — bordas (ErrorState, Pager e Parar execução RUNNING)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("exibe ErrorState quando listExecutions falha", async () => {
    vi.spyOn(orchestratorApi, "listExecutions").mockRejectedValue(
      new Error("Erro ao listar execuções"),
    );

    renderExecucoes();

    expect(await screen.findByText("Erro ao listar execuções")).toBeInTheDocument();
  });

  it("avança para a próxima página ao clicar em Próxima no Pager", async () => {
    const listSpy = vi
      .spyOn(orchestratorApi, "listExecutions")
      .mockResolvedValue({
        ...EXECUTIONS_PAGE,
        page: 1,
        pages: 3,
        total: 60,
      });

    renderExecucoes();

    expect((await screen.findAllByText("Montagem de Terceirizados")).length).toBeGreaterThan(0);

    const nextBtn = screen.getByRole("button", { name: /Próxima/i });
    fireEvent.click(nextBtn);

    await waitFor(() =>
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2, per_page: 25 }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("exige confirmação e chama stopExecution ao parar execução RUNNING", async () => {
    const runningExec: ExecutionSummary = {
      ...EXECUTIONS_PAGE.items[0]!,
      id: "RUN_42_ABCDEF",
      automation_name: "Pipeline Em Execução",
      status: "RUNNING",
      stop_allowed: true,
      requeue_allowed: false,
    };

    vi.spyOn(orchestratorApi, "listExecutions").mockResolvedValue({
      items: [runningExec],
      total: 1,
      page: 1,
      per_page: 25,
      pages: 1,
    });
    const stopSpy = vi
      .spyOn(orchestratorApi, "stopExecution")
      .mockResolvedValue({ message: "Parada solicitada" });

    renderExecucoes();

    const stopRowBtn = await screen.findByRole("button", { name: /Parar execução RUN_42_ABCDEF/i });
    fireEvent.click(stopRowBtn);

    expect(await screen.findByText(/Solicitar término da execução/i)).toBeInTheDocument();
    const confirmBtn = screen.getByRole("button", { name: "Parar execução" });
    fireEvent.click(confirmBtn);

    await waitFor(() => expect(stopSpy).toHaveBeenCalledWith("RUN_42_ABCDEF"));
  });
});
