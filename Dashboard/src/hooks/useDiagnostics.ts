import { useState, useEffect, useCallback } from "react";
import { orchestratorApi, type SystemHealth, type WorkerStatus } from "../api/orchestrator";

export interface DiagnosticsState {
  health: SystemHealth | null;
  worker: WorkerStatus | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
}

export function useDiagnostics(intervalMs = 15_000) {
  const [state, setState] = useState<DiagnosticsState>({
    health: null,
    worker: null,
    loading: true,
    error: null,
    lastUpdated: null,
  });

  const refresh = useCallback(async () => {
    try {
      const [health, worker] = await Promise.all([
        orchestratorApi.getHealth(),
        orchestratorApi.getWorkerStatus(),
      ]);
      setState({ health, worker, loading: false, error: null, lastUpdated: new Date() });
    } catch (err) {
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      }));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { ...state, refresh };
}
