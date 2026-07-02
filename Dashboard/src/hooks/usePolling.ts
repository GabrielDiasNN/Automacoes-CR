import { useCallback, useEffect, useRef, useState } from "react";

export interface PollingState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
}

/** Faz polling de um endpoint com intervalo configurável.
 *  Mantém o último dado válido durante refresh (sem flicker).
 *  `deps` força um refresh imediato (reiniciando o intervalo) quando muda —
 *  use para parâmetros do fetcher como página/filtro. */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs = 15_000,
  deps: unknown[] = [],
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    try {
      const d = await fetcherRef.current();
      setData(d);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    if (intervalMs <= 0) return;
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, intervalMs, ...deps]);

  return { data, loading, error, lastUpdated, refresh };
}
