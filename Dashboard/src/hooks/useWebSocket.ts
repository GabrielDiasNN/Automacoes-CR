import { useEffect, useRef, useState, useCallback } from "react";

export type WsStatus = "connecting" | "open" | "closed";

export interface UseWebSocketOptions {
  onMessage?: (event: MessageEvent) => void;
  enabled?: boolean;
}

export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
  const { onMessage, enabled = true } = options;
  const [status, setStatus] = useState<WsStatus>("closed");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(1000);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled || !url) return;

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("open");
      reconnectDelay.current = 1000; // reset backoff em sucesso (3.2)
    };

    ws.onmessage = (evt) => {
      onMessageRef.current?.(evt);
    };

    ws.onclose = (evt) => {
      setStatus("closed");
      wsRef.current = null;
      // code 4003 = auth recusada pelo servidor — não reconectar
      if (evt.code === 4003) return;
      // backoff exponencial até 30s (3.2)
      timerRef.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30_000);
        connect();
      }, reconnectDelay.current);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [url, enabled]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((data: string | object) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }, []);

  return { status, send };
}
