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

  it("reconecta com backoff exponencial em quedas consecutivas sem sucesso (achado nº 7)", async () => {
    renderHook(() => useWebSocket("/ws/events", "chave"));

    // 1ª conexão abre e cai com o hook ainda montado.
    await act(async () => {
      resolvers[0](okToken("t1"));
      await vi.advanceTimersByTimeAsync(0);
      FakeWebSocket.instances[0].onopen?.();
      FakeWebSocket.instances[0].onclose?.();
    });

    // 1ª reconexão: delay inicial de 1000ms.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(999);
    });
    expect(resolvers).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(resolvers).toHaveLength(2);

    // A tentativa de reconexão também cai, sem nunca abrir (onopen não é chamado,
    // então o backoff NÃO reseta) → próximo delay dobra para 2000ms.
    await act(async () => {
      resolvers[1](okToken("t2"));
      await vi.advanceTimersByTimeAsync(0);
      FakeWebSocket.instances[1].onclose?.();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1999);
    });
    expect(resolvers).toHaveLength(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(resolvers).toHaveLength(3);
  });

  it("reseta o backoff após uma reconexão bem-sucedida", async () => {
    renderHook(() => useWebSocket("/ws/events", "chave"));

    await act(async () => {
      resolvers[0](okToken("t1"));
      await vi.advanceTimersByTimeAsync(0);
      FakeWebSocket.instances[0].onopen?.();
    });

    // 1ª queda → reconecta em 1000ms.
    await act(async () => {
      FakeWebSocket.instances[0].onclose?.();
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(resolvers).toHaveLength(2);

    // Reconexão bem-sucedida: onopen zera o delay.
    await act(async () => {
      resolvers[1](okToken("t2"));
      await vi.advanceTimersByTimeAsync(0);
      FakeWebSocket.instances[1].onopen?.();
    });

    // Nova queda → volta a 1000ms (não 2000ms).
    await act(async () => {
      FakeWebSocket.instances[1].onclose?.();
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(resolvers).toHaveLength(3);
  });

  it("send() escreve no socket só quando ele está aberto", async () => {
    const { result } = renderHook(() => useWebSocket("/ws/events", "chave"));

    result.current.send("antes de abrir");
    await act(async () => {
      resolvers[0](okToken("t1"));
      await vi.advanceTimersByTimeAsync(0);
    });
    // readyState ainda 0 (não abriu): send é no-op.
    result.current.send("ainda fechado");
    expect(FakeWebSocket.instances[0].sent).toEqual([]);

    await act(async () => {
      FakeWebSocket.instances[0].readyState = FakeWebSocket.OPEN;
      FakeWebSocket.instances[0].onopen?.();
    });
    result.current.send("agora vai");
    result.current.send({ tipo: "ping" });
    expect(FakeWebSocket.instances[0].sent).toEqual(["agora vai", '{"tipo":"ping"}']);
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
