import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWebSocket } from "../hooks/useWebSocket";

type TokenResolver = (value: unknown) => void;
type TokenRejecter = (reason?: unknown) => void;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly OPEN = 1;

  url: string;
  readyState = 0;
  closed = false;
  closeCalls = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((evt: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
    this.closeCalls += 1;
    this.readyState = 3;
    this.onclose?.();
  }
}

function okToken(token: string) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve({ token }),
  };
}

describe("useWebSocket (edge cases)", () => {
  let resolvers: TokenResolver[];
  let rejecters: TokenRejecter[];

  beforeEach(() => {
    vi.useFakeTimers();
    resolvers = [];
    rejecters = [];
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((resolve, reject) => {
            resolvers.push(resolve);
            rejecters.push(reject);
          }),
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("não conecta quando enabled=false, path vazio ou apiKey vazia", () => {
    const { result: r1 } = renderHook(() =>
      useWebSocket("/ws/events", "chave", { enabled: false }),
    );
    const { result: r2 } = renderHook(() => useWebSocket("", "chave"));
    const { result: r3 } = renderHook(() => useWebSocket("/ws/events", ""));

    expect(r1.current.status).toBe("closed");
    expect(r2.current.status).toBe("closed");
    expect(r3.current.status).toBe("closed");
    expect(resolvers).toHaveLength(0);
  });

  it("entrega mensagens ao callback onMessage e ignora eventos de geração obsoleta", async () => {
    const onMessage = vi.fn();
    const { unmount } = renderHook(() =>
      useWebSocket("/ws/events", "chave", { onMessage }),
    );

    await act(async () => {
      resolvers[0]!(okToken("t1"));
      await vi.advanceTimersByTimeAsync(0);
    });

    const ws = FakeWebSocket.instances[0]!;
    const msg = new MessageEvent("message", { data: '{"ok":true}' });
    act(() => {
      ws.onmessage?.(msg);
    });
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledWith(msg);

    // Após unmount, a geração é invalidada: onmessage e onopen tardios são no-op
    unmount();
    act(() => {
      ws.onmessage?.(new MessageEvent("message", { data: "tardio" }));
      ws.onopen?.();
    });
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(ws.closeCalls).toBe(2); // 1 no unmount + 1 no onopen obsoleto
  });

  it("fecha o socket e agenda reconexão quando ws.onerror dispara", async () => {
    const { result } = renderHook(() => useWebSocket("/ws/events", "chave"));

    await act(async () => {
      resolvers[0]!(okToken("t1"));
      await vi.advanceTimersByTimeAsync(0);
      FakeWebSocket.instances[0]!.onopen?.();
    });
    expect(result.current.status).toBe("open");

    await act(async () => {
      FakeWebSocket.instances[0]!.onerror?.();
    });

    expect(FakeWebSocket.instances[0]!.closed).toBe(true);
    expect(result.current.status).toBe("closed");

    // Reconexão agendada após 1000ms
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(resolvers).toHaveLength(2);
  });

  it("agenda reconexão com backoff em falha transitória ao obter ws-token (erro de rede / 500)", async () => {
    const { result } = renderHook(() => useWebSocket("/ws/events", "chave"));

    await act(async () => {
      rejecters[0]!(new Error("network down"));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe("closed");

    // 1ª reconexão em 1000ms
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(resolvers).toHaveLength(2);

    // 2ª falha (500) → status closed e próximo delay dobra para 2000ms
    await act(async () => {
      resolvers[1]!({ ok: false, status: 500, json: () => Promise.resolve({}) });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe("closed");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1999);
    });
    expect(resolvers).toHaveLength(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(resolvers).toHaveLength(3);
  });

  it("marca unauthorized em 401 e cancela timer pendente no unmount", async () => {
    const { result, unmount } = renderHook(() => useWebSocket("/ws/events", "chave"));

    // Simula erro transitório para agendar um timer de reconexão pendente
    await act(async () => {
      rejecters[0]!(new Error("timeout"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe("closed");

    // Desmonta antes do timer disparar → clearTimeout evita nova requisição
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(resolvers).toHaveLength(1);

    // Nova montagem com 401 → unauthorized sem reconectar
    const { result: r401 } = renderHook(() => useWebSocket("/ws/events", "expirada"));
    await act(async () => {
      resolvers[1]!({ ok: false, status: 401, json: () => Promise.resolve({}) });
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(r401.current.status).toBe("unauthorized");
  });
});
