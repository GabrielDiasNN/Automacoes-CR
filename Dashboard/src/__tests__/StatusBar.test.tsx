import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusBar } from "../components/StatusBar";
import * as LiveStatusCtx from "../context/LiveStatusContext";

describe("StatusBar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });
  const workerMock = {
    is_alive: true,
    pid: 101,
    instance_id: "w-1",
    host: "localhost",
    last_ping: "22/11/2026 18:00:00",
    uptime_seconds: 120,
    tasks_completed: 5,
    tasks_failed: 0,
    active_tasks: 2,
    pool_saturated_seconds: 0,
    version: "1.0.0",
  };

  it("exibe estado saudável com worker ativo e WebSocket conectado", () => {
    vi.spyOn(LiveStatusCtx, "useLiveStatus").mockReturnValue({
      health: {
        status: "healthy",
        timestamp: "22/11/2026 18:00:00",
        database: "online",
        scheduler: "executando",
        worker: workerMock,
        pending_tasks: 3,
        disk_usage_mb: 100,
        wal_size_mb: 0.2,
        cpu_usage: 10,
        ram_usage_percent: 40,
      },
      worker: workerMock,
      wsStatus: "open",
    });

    render(<StatusBar />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("worker")).toBeInTheDocument();
    expect(screen.getByText("sinal")).toBeInTheDocument();
  });

  it("exibe worker offline e sem sinal quando WebSocket está fechado", () => {
    vi.spyOn(LiveStatusCtx, "useLiveStatus").mockReturnValue({
      health: {
        status: "unhealthy",
        timestamp: "22/11/2026 18:00:00",
        database: "online",
        scheduler: "parado",
        worker: { ...workerMock, is_alive: false, active_tasks: 0 },
        pending_tasks: 0,
        disk_usage_mb: 100,
        wal_size_mb: 0.2,
        cpu_usage: 10,
        ram_usage_percent: 40,
      },
      worker: null,
      wsStatus: "closed",
    });

    render(<StatusBar />);
    expect(screen.getByText("offline")).toBeInTheDocument();
    expect(screen.getByText("sem sinal")).toBeInTheDocument();
  });
});
