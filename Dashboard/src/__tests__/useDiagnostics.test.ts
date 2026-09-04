import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDiagnostics } from "../hooks/useDiagnostics";
import { orchestratorApi } from "../api/orchestrator";
import { _clearCache } from "../lib/resourceCache";

const health = (over: Record<string, unknown> = {}) => ({
  status: "healthy",
  timestamp: "2026-09-03 10:00:00",
  database: "online",
  scheduler: "executando",
  worker: { is_alive: true, active_tasks: 2, pid: 42 },
  pending_tasks: 0,
  ...over,
});

describe("useDiagnostics", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    _clearCache();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("deriva worker de health.worker e NÃO chama getWorkerStatus", async () => {
    const getHealth = vi.spyOn(orchestratorApi, "getHealth").mockResolvedValue(health() as never);
    const getWorkerStatus = vi.spyOn(orchestratorApi, "getWorkerStatus");

    const { result } = renderHook(() => useDiagnostics(10_000));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(getHealth).toHaveBeenCalledTimes(1);
    expect(getWorkerStatus).not.toHaveBeenCalled();
    expect(result.current.health?.status).toBe("healthy");
    expect(result.current.worker).toEqual({ is_alive: true, active_tasks: 2, pid: 42 });
    expect(result.current.loading).toBe(false);
  });

  it("resposta atrasada de um tick anterior não sobrescreve a mais nova", async () => {
    // tick 1: resolve devagar com active_tasks=1
    // tick 2: resolve na hora com active_tasks=9  <- deve prevalecer
    vi.spyOn(orchestratorApi, "getHealth")
      .mockImplementationOnce(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve(health({ worker: { is_alive: true, active_tasks: 1 } }) as never), 5_000),
          ),
      )
      .mockResolvedValueOnce(health({ worker: { is_alive: true, active_tasks: 9 } }) as never);

    const { result } = renderHook(() => useDiagnostics(1_000));

    // dispara o tick 1 (lento) e o tick 2 (rápido)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_100);
    });
    expect(result.current.worker?.active_tasks).toBe(9);

    // a resposta lenta do tick 1 chega agora — deve ser descartada
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(result.current.worker?.active_tasks).toBe(9);
  });

  it("propaga o erro do polling", async () => {
    vi.spyOn(orchestratorApi, "getHealth").mockRejectedValue(new Error("500 fora do ar"));
    const { result } = renderHook(() => useDiagnostics(10_000));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBe("500 fora do ar");
    expect(result.current.worker).toBeNull();
  });
});
