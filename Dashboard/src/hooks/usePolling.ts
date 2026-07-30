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
 *  use para parâmetros do fetcher como página/filtro.
 *
 *  O `fetcher` recebe um `AbortSignal`: repasse-o à camada de API (`api.get`)
 *  para que a requisição anterior seja de fato cancelada quando os parâmetros
 *  mudam ou o componente desmonta. Fetchers que ignoram o argumento continuam
 *  funcionando — nesse caso a resposta obsoleta é apenas descartada, mas ainda
 *  trafega e consome bucket de rate limit. */
export function usePolling<T>(
  fetcher: (signal?: AbortSignal) => Promise<T>,
  intervalMs = 15_000,
  deps: unknown[] = [],
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // Sequência da requisição: descarta resposta que chegue fora de ordem. Sem
  // isso, trocar de página/filtro (ou um refresh manual competindo com o tick do
  // intervalo) pode fazer a resposta ANTIGA chegar depois da nova e sobrescrever
  // a tela com dados que não correspondem aos parâmetros atuais.
  const requestSeqRef = useRef(0);
  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const refresh = useCallback(async () => {
    const seq = ++requestSeqRef.current;
    const isLatest = () => mountedRef.current && requestSeqRef.current === seq;

    // Cancela o fetch anterior: a resposta dele já seria descartada, então
    // deixá-lo em voo só desperdiça conexão e bucket de rate limit.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const d = await fetcherRef.current(controller.signal);
      if (!isLatest()) return;
      setData(d);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      // Abortar é fluxo normal (troca de parâmetro/unmount), não erro de tela.
      if (controller.signal.aborted || (e instanceof Error && e.name === "AbortError")) {
        return;
      }
      if (!isLatest()) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (isLatest()) setLoading(false);
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
