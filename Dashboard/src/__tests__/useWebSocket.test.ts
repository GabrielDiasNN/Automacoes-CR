import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWebSocket } from "../hooks/useWebSocket";

type TokenResolver = (value: unknown) => void;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static readonly OPEN = 1;

  url: string;
  readyState = 0;
  closed = false;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((evt: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
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

describe("useWebSocket", () => {
  let resolvers: TokenResolver[];

  beforeEach(() => {
    vi.useFakeTimers();
    resolvers = [];
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise((resolve) => resolvers.push(resolve))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("abre uma conexão após trocar o token pela API Key", async () => {
    const { result } = renderHook(() => useWebSocket("/ws/events", "chave"));

    expect(resolvers).toHaveLength(1);

    await act(async () => {
      resolvers[0](okToken("t1"));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain("token=t1");

    await act(async () => {
      FakeWebSocket.instances[0].onopen?.();
    });
    expect(result.current.status).toBe("open");
  });

  it("ignora o token em voo da geração anterior ao remontar", async () => {
    // O effect é recriado quando apiKey/path mudam: cleanup e novo connect
    // rodam em sequência. Se o fetch de token da geração anterior resolver
    // depois disso, ele NÃO pode abrir um segundo socket órfão.
    const { rerender } = renderHook(
      ({ chave }) => useWebSocket("/ws/events", chave),
      { initialProps: { chave: "A" } },
    );

    expect(resolvers).toHaveLength(1);

    rerender({ chave: "B" });
    expect(resolvers).toHaveLength(2);

    await act(async () => {
      // A resposta da geração obsoleta chega DEPOIS da atual.
      resolvers[1](okToken("token-novo"));
      await vi.advanceTimersByTimeAsync(0);
      resolvers[0](okToken("token-antigo"));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain("token-novo");
  });

  it("não reconecta quando o close vem do cleanup do unmount", async () => {
    const { unmount } = renderHook(() => useWebSocket("/ws/events", "chave"));

    await act(async () => {
      resolvers[0](okToken("t1"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);

    unmount();
    expect(FakeWebSocket.instances[0].closed).toBe(true);

    // O backoff máximo é 30s: nenhum novo token deve ser pedido nessa janela.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(resolvers).toHaveLength(1);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("para de tentar quando a API Key é recusada", async () => {
    const { result } = renderHook(() => useWebSocket("/ws/events", "ruim"));

    await act(async () => {
      resolvers[0]({ ok: false, status: 403, json: () => Promise.resolve({}) });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.status).toBe("unauthorized");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(resolvers).toHaveLength(1);
  });
});
