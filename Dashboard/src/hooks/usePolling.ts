import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { errMessage } from "../lib/errors";
import { readCache, writeCache } from "../lib/resourceCache";

export interface PollingOptions<T = unknown> {
  /** Chave de cache stale-while-revalidate. Com ela, uma remontagem semeia
   *  `data` a partir da última resposta em vez de voltar a `null` (sem
   *  `Loading` de tela cheia em `/painel → /sistema → /painel`). O fetch de
   *  revalidação ainda roda (a menos que `skipIfFresh`). */
  cacheKey?: string;
  /** TTL do cache. Generoso de propósito: como sempre revalida no mount, a
   *  janela de staleness é ~1 requisição, e `FreshnessTag` sinaliza falha. */
  cacheTtlMs?: number;
  /** Se o cache de `cacheKey` estiver fresco, USA o valor e PULA a requisição.
   *  Para dedupe entre pollers: `useDiagnostics` pula `getHealth` enquanto uma
   *  tela alimenta a chave `"health"` do payload de `getOverview` (que já
   *  carrega `health`). Auto-cura: se a outra tela some, o cache vence o TTL e
   *  a requisição real volta. */
  skipIfFresh?: boolean;
  /** Roda a cada resposta de sucesso — para derivar chaves de cache de um
   *  payload composto (ex.: `getOverview` → grava `overview.health` em
   *  `"health"`, que outro poller consome). */
  onData?: (data: T) => void;
}

const DEFAULT_CACHE_TTL_MS = 30_000;

export interface PollingState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  /** Definido quando a última tentativa levou 429 — a hora em que o polling
   *  volta a tentar de fato (ticks do intervalo entre agora e essa hora são
   *  pulados sem requisição, em vez de martelar a mesma janela bloqueada). */
  rateLimitedUntil: Date | null;
  /** `true` quando um `refresh()` foi pedido durante a janela de 429 e está
   *  enfileirado para o fim dela. Antes esse `refresh()` era um no-op
   *  silencioso — o operador dava "purge", via o toast de sucesso e a tabela
   *  não mudava. A UI usa isto para sinalizar "atualização pendente". */
  refreshQueued: boolean;
  refresh: () => Promise<void>;
}

const DEFAULT_RATE_LIMIT_BACKOFF_S = 30;

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
  options: PollingOptions<T> = {},
): PollingState<T> {
  const { cacheKey, cacheTtlMs = DEFAULT_CACHE_TTL_MS, skipIfFresh = false, onData } = options;
  // Semente lida uma única vez, no mount (initializer lazy).
  const [seeded] = useState(() =>
    cacheKey ? readCache<T>(cacheKey, cacheTtlMs) : undefined,
  );

  const [data, setData] = useState<T | null>(seeded ?? null);
  const [loading, setLoading] = useState(seeded === undefined);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [rateLimitedUntil, setRateLimitedUntil] = useState<Date | null>(null);
  const [refreshQueued, setRefreshQueued] = useState(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;
  const onDataRef = useRef(onData);
  onDataRef.current = onData;
  const skipIfFreshRef = useRef(skipIfFresh);
  skipIfFreshRef.current = skipIfFresh;
  const cacheTtlMsRef = useRef(cacheTtlMs);
  cacheTtlMsRef.current = cacheTtlMs;

  // Timer que dispara o refresh enfileirado ao fim da janela de 429. Só um por
  // vez — um pedido novo durante a janela apenas renova a intenção.
  const queuedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // `refresh` é estável (useCallback []), mas não pode se referenciar nas deps;
  // o timer de fila chama via ref.
  const refreshRef = useRef<() => Promise<void>>(() => Promise.resolve());

  // Sequência da requisição: descarta resposta que chegue fora de ordem. Sem
  // isso, trocar de página/filtro (ou um refresh manual competindo com o tick do
  // intervalo) pode fazer a resposta ANTIGA chegar depois da nova e sobrescrever
  // a tela com dados que não correspondem aos parâmetros atuais.
  const requestSeqRef = useRef(0);
  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  // Espelha `rateLimitedUntil` em ref para o `refresh` (estável entre renders)
  // poder ler o valor corrente sem entrar nas deps do useCallback.
  const blockedUntilRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      if (queuedTimerRef.current) clearTimeout(queuedTimerRef.current);
    };
  }, []);

  const refresh = useCallback(async () => {
    // Ainda dentro da janela de 429: não gera requisição nova (marteler a
    // janela só agrava o rate limit), mas ENFILEIRA a intenção para o fim da
    // janela em vez de descartá-la em silêncio — antes um `refresh()` aqui era
    // no-op e o operador via o toast de sucesso da ação sem a tabela mudar.
    const blockedFor = blockedUntilRef.current - Date.now();
    if (blockedFor > 0) {
      // O `return` abaixo pula o `finally`; sem isto, um refresh disparado já
      // dentro da janela (ex.: remonta durante backoff) deixaria `loading` preso.
      if (mountedRef.current) setLoading(false);
      setRefreshQueued(true);
      if (!queuedTimerRef.current) {
        queuedTimerRef.current = setTimeout(() => {
          queuedTimerRef.current = null;
          void refreshRef.current();
        }, blockedFor + 50);
      }
      return;
    }
    if (queuedTimerRef.current) {
      clearTimeout(queuedTimerRef.current);
      queuedTimerRef.current = null;
    }
    setRefreshQueued(false);

    // Dedupe entre pollers: se outra tela já mantém `cacheKey` fresco, usa o
    // valor e não gera requisição. Auto-cura quando essa tela some (o cache
    // vence o TTL).
    if (skipIfFreshRef.current && cacheKeyRef.current) {
      const cached = readCache<T>(cacheKeyRef.current, cacheTtlMsRef.current);
      if (cached !== undefined && mountedRef.current) {
        setData(cached);
        setError(null);
        setLastUpdated(new Date());
        setLoading(false);
        return;
      }
    }

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
      if (cacheKeyRef.current) writeCache(cacheKeyRef.current, d);
      onDataRef.current?.(d);
      setError(null);
      setRateLimitedUntil(null);
      blockedUntilRef.current = 0;
      setLastUpdated(new Date());
    } catch (e) {
      // Abortar é fluxo normal (troca de parâmetro/unmount), não erro de tela.
      if (controller.signal.aborted || (e instanceof Error && e.name === "AbortError")) {
        return;
      }
      if (!isLatest()) return;
      if (e instanceof ApiError && e.status === 429) {
        const backoffS = e.retryAfter ?? DEFAULT_RATE_LIMIT_BACKOFF_S;
        const until = new Date(Date.now() + backoffS * 1000);
        blockedUntilRef.current = until.getTime();
        setRateLimitedUntil(until);
        setError(`limite de requisições atingido — retomando em ${backoffS}s`);
      } else {
        setError(errMessage(e));
      }
    } finally {
      if (isLatest()) setLoading(false);
    }
  }, []);
  refreshRef.current = refresh;

  useEffect(() => {
    void refresh();
    if (intervalMs <= 0) return;
    const id = setInterval(() => void refresh(), intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, intervalMs, ...deps]);

  return { data, loading, error, lastUpdated, rateLimitedUntil, refreshQueued, refresh };
}
