import { useState, useEffect, useCallback, useRef } from "react";
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

  // Não escreve estado depois do unmount: no React 18 já é só um no-op ruidoso,
  // mas mantém a disciplina do resto do front (usePolling faz o mesmo).
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const [health, worker] = await Promise.all([
        orchestratorApi.getHealth(),
        orchestratorApi.getWorkerStatus(),
      ]);
      if (!mountedRef.current) return;
      setState({ health, worker, loading: false, error: null, lastUpdated: new Date() });
    } catch (err) {
      if (!mountedRef.current) return;
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      }));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [refresh, intervalMs]);

  return { ...state, refresh };
}
