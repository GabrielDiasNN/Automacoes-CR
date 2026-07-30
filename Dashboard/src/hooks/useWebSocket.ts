import { useCallback, useEffect, useRef, useState } from "react";

export type WsStatus = "connecting" | "open" | "closed" | "unauthorized";

export interface UseWebSocketOptions {
  onMessage?: (event: MessageEvent) => void;
  enabled?: boolean;
}

function wsBase(): string {
  if (typeof location === "undefined") return "";
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}`;
}

/**
 * Conecta a um endpoint WebSocket do Orchestrator.
 *
 * `path` é apenas o caminho (ex.: "/ws/events"). A API Key NÃO viaja na URL:
 * como o browser não permite header no handshake WebSocket, o hook troca a chave
 * por um token efêmero de uso único em `POST /api/system/ws-token` e apresenta
 * somente esse token no `?token=`. Assim a credencial mestra deixa de aparecer
 * em logs de acesso de servidor/proxy.
 */
export function useWebSocket(
  path: string,
  apiKey: string,
  options: UseWebSocketOptions = {},
) {
  const { onMessage, enabled = true } = options;
  const [status, setStatus] = useState<WsStatus>("closed");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(1000);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Contador de geração em vez de um booleano "ativo": no remount (troca de
  // path/apiKey) o cleanup e o novo effect rodam em sequência, então um booleano
  // já estaria de volta em `true` quando o fetch do token da geração anterior
  // resolvesse — abrindo um segundo WebSocket órfão e disparando reconexões
  // duplicadas a partir do `onclose` do cleanup. A geração invalida de vez.
  const generationRef = useRef(0);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled || !path || !apiKey) return;

    const generation = ++generationRef.current;
    const isCurrent = () => generationRef.current === generation;

    setStatus("connecting");

    const scheduleReconnect = () => {
      if (!isCurrent()) return;
      timerRef.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30_000);
        connect();
      }, reconnectDelay.current);
    };

    fetch("/api/system/ws-token", {
      method: "POST",
      headers: { "X-API-Key": apiKey },
    })
      .then((res) => {
        if (res.status === 401 || res.status === 403) {
          // Chave de API genuinamente inválida/revogada: reconectar não resolve
          // (o servidor sempre vai recusar), então para de tentar em vez de
          // repetir o POST /ws-token indefinidamente com backoff.
          throw new Error("unauthorized");
        }
        if (!res.ok) throw new Error(`ws-token ${res.status}`);
        return res.json() as Promise<{ token: string }>;
      })
      .then(({ token }) => {
        if (!isCurrent()) return;

        const ws = new WebSocket(
          `${wsBase()}${path}?token=${encodeURIComponent(token)}`,
        );
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isCurrent()) {
            ws.close();
            return;
          }
          setStatus("open");
          reconnectDelay.current = 1000; // reset backoff em sucesso (3.2)
        };

        ws.onmessage = (evt) => {
          if (!isCurrent()) return;
          onMessageRef.current?.(evt);
        };

        ws.onclose = () => {
          if (!isCurrent()) return;
          setStatus("closed");
          wsRef.current = null;
          // Diferente do fluxo antigo com API Key fixa, o 4003 aqui é
          // transitório (token de uso único já consumido ou expirado por
          // reinício do servidor), então vale reconectar com backoff. Chave
          // inválida de verdade falha antes, no POST /ws-token, e cai no catch.
          scheduleReconnect();
        };

        ws.onerror = () => {
          ws.close();
        };
      })
      .catch((err) => {
        if (!isCurrent()) return;
        if (err instanceof Error && err.message === "unauthorized") {
          setStatus("unauthorized");
          return;
        }
        // Falha transitória ao emitir o token (servidor fora do ar, rede):
        // tenta de novo com backoff exponencial até 30s.
        setStatus("closed");
        scheduleReconnect();
      });
  }, [path, apiKey, enabled]);

  useEffect(() => {
    connect();
    return () => {
      // Invalida a geração corrente: callbacks em voo (token, onclose) viram
      // no-op e não reagendam reconexão para esta instância.
      generationRef.current += 1;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
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
