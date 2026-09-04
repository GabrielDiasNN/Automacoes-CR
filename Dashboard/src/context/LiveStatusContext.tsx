import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { getApiKey } from "../api/client";
import { useDiagnostics } from "../hooks/useDiagnostics";
import { useWebSocket, type WsStatus } from "../hooks/useWebSocket";
import type { SystemHealth, WorkerStatus } from "../api/orchestrator";

type EventListener = (event: MessageEvent) => void;

/** Dados ao vivo — muda a cada tick de polling (10s). */
interface LiveData {
  health: SystemHealth | null;
  worker: WorkerStatus | null;
  wsStatus: WsStatus;
}

/** Só o `subscribe` do event bus — valor ESTÁVEL entre renders. Separado de
 *  `LiveData` para que `useLiveEvents` (que só quer `subscribe`) não
 *  re-renderize a cada tick de 10s do polling de saúde. */
interface LiveEvents {
  subscribe: (fn: EventListener) => () => void;
}

const LiveDataCtx = createContext<LiveData | null>(null);
const LiveEventsCtx = createContext<LiveEvents | null>(null);

/** Dono ÚNICO do polling de `health` e da conexão `/ws/events`.
 *
 *  Montado uma vez no `Shell` (layout route que nunca desmonta). Antes,
 *  `StatusBar` e `MonitorPage` abriam cada um seu polling e seu `useWebSocket`,
 *  então entrar em `/monitor` dobrava as chamadas e abria uma segunda conexão
 *  ao mesmo event bus — o bucket de rate limit é recurso escasso e
 *  compartilhado (achado nº 15). */
export function LiveStatusProvider({ children }: { children: ReactNode }) {
  const { health, worker } = useDiagnostics(10_000);
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

  const dataValue = useMemo<LiveData>(
    () => ({ health, worker, wsStatus }),
    [health, worker, wsStatus],
  );
  // `subscribe` é estável (useCallback []), então este value nunca muda —
  // consumidores só de eventos não re-renderizam no tick de saúde.
  const eventsValue = useMemo<LiveEvents>(() => ({ subscribe }), [subscribe]);

  return (
    <LiveEventsCtx.Provider value={eventsValue}>
      <LiveDataCtx.Provider value={dataValue}>{children}</LiveDataCtx.Provider>
    </LiveEventsCtx.Provider>
  );
}

export function useLiveStatus(): LiveData {
  const ctx = useContext(LiveDataCtx);
  if (!ctx) throw new Error("useLiveStatus precisa de <LiveStatusProvider>");
  return ctx;
}

/** Açúcar para consumidores que só querem reagir a eventos do event bus. */
export function useLiveEvents(handler: EventListener): void {
  const ctx = useContext(LiveEventsCtx);
  if (!ctx) throw new Error("useLiveEvents precisa de <LiveStatusProvider>");
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  useEffect(() => ctx.subscribe((event) => handlerRef.current(event)), [ctx]);
}
