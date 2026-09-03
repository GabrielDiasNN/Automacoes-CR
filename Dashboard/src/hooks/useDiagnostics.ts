import { orchestratorApi, type SystemHealth, type WorkerStatus } from "../api/orchestrator";
import { usePolling } from "./usePolling";

export interface DiagnosticsState {
  health: SystemHealth | null;
  worker: WorkerStatus | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
}

/** Polling de saúde do sistema para o `LiveStatusProvider`.
 *
 *  Antes era um hook próprio com `Promise.all` e sem `AbortController` nem
 *  guarda de sequência — o único do app nessa condição, e o que roda em TODA
 *  aba aberta (tick de 10s). Uma resposta atrasada sobrescrevia uma mais nova.
 *  Agora é `usePolling` puro: herda aborto, guarda de sequência e backoff de
 *  429, e a semente de cache evita o flash ao remontar o Shell.
 *
 *  `worker` sai de `health.worker` (`SystemHealth` já o carrega) — a chamada
 *  separada a `getWorkerStatus()` era um terço do tráfego fixo, desperdiçado
 *  contra o teto de 120 req/min por IP.
 *
 *  `skipIfFresh`: `getOverview` (Painel/Sistema) já traz `health` no payload e
 *  o grava na chave `"health"`. Enquanto uma dessas telas está aberta,
 *  `useDiagnostics` usa esse valor e NÃO faz a própria requisição — numa aba
 *  parada em `/painel`, o tráfego fixo cai de 12 para 6 req/min. Fora dessas
 *  telas o cache vence o TTL e a requisição real volta. */
export function useDiagnostics(intervalMs = 15_000): DiagnosticsState {
  const { data, loading, error, lastUpdated, refresh } = usePolling<SystemHealth>(
    (signal) => orchestratorApi.getHealth(signal),
    intervalMs,
    [],
    { cacheKey: "health", cacheTtlMs: 15_000, skipIfFresh: true },
  );

  return {
    health: data,
    worker: data?.worker ?? null,
    loading,
    error,
    lastUpdated,
    refresh,
  };
}
