import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { getApiKey } from "../api/client";
import { useDiagnostics } from "../hooks/useDiagnostics";
import { useWebSocket, type WsStatus } from "../hooks/useWebSocket";
import type { SystemHealth, WorkerStatus } from "../api/orchestrator";

type EventListener = (event: MessageEvent) => void;

interface LiveStatus {
  health: SystemHealth | null;
  worker: WorkerStatus | null;
  loading: boolean;
  error: string | null;
  wsStatus: WsStatus;
  /** Registra um handler para as mensagens do `/ws/events` compartilhado. Devolve o cancelamento. */
  subscribe: (fn: EventListener) => () => void;
}

const LiveStatusCtx = createContext<LiveStatus | null>(null);

/** Dono ÚNICO do polling de `health`/`worker/status` e da conexão `/ws/events`.
 *
 *  Montado uma vez no `Shell` (layout route que nunca desmonta). Antes,
 *  `StatusBar` e `MonitorPage` abriam cada um seu `useDiagnostics(10s)` e seu
 *  `useWebSocket`, então entrar em `/monitor` dobrava as chamadas a `health`/
 *  `worker/status` e abria uma segunda conexão ao mesmo event bus — o bucket de
 *  rate limit é recurso escasso e compartilhado (achado nº 15). */
export function LiveStatusProvider({ children }: { children: ReactNode }) {
  const { health, worker, loading, error } = useDiagnostics(10_000);
  const key = getApiKey();

  const listenersRef = useRef<Set<EventListener>>(new Set());
  const fanOut = useCallback((event: MessageEvent) => {
    for (const fn of listenersRef.current) fn(event);
  }, []);

  const { status: wsStatus } = useWebSocket("/ws/events", key ?? "", { onMessage: fanOut, enabled: !!key });

  const subscribe = useCallback((fn: EventListener) => {
    listenersRef.current.add(fn);
    return () => {
      listenersRef.current.delete(fn);
    };
  }, []);

  const value = useMemo<LiveStatus>(
    () => ({ health, worker, loading, error, wsStatus, subscribe }),
    [health, worker, loading, error, wsStatus, subscribe],
  );

  return <LiveStatusCtx.Provider value={value}>{children}</LiveStatusCtx.Provider>;
}

export function useLiveStatus(): LiveStatus {
  const ctx = useContext(LiveStatusCtx);
  if (!ctx) throw new Error("useLiveStatus precisa de <LiveStatusProvider>");
  return ctx;
}

/** Açúcar para consumidores que só querem reagir a eventos do event bus. */
export function useLiveEvents(handler: EventListener): void {
  const { subscribe } = useLiveStatus();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  useEffect(() => subscribe((event) => handlerRef.current(event)), [subscribe]);
}
