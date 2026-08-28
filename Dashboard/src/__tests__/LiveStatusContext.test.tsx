import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const diagnosticsSpy = vi.fn(() => ({
  health: { status: "ok" },
  worker: { is_alive: true },
  loading: false,
  error: null,
}));
let capturedWsOptions: { onMessage?: (e: MessageEvent) => void } = {};
const webSocketSpy = vi.fn((_path: string, _key: string, opts: { onMessage?: (e: MessageEvent) => void }) => {
  capturedWsOptions = opts;
  return { status: "open" as const, send: vi.fn() };
});

vi.mock("../hooks/useDiagnostics", () => ({ useDiagnostics: () => diagnosticsSpy() }));
vi.mock("../hooks/useWebSocket", () => ({
  useWebSocket: (path: string, key: string, opts: Record<string, unknown>) => webSocketSpy(path, key, opts),
}));
vi.mock("../api/client", () => ({ getApiKey: () => "chave-de-teste" }));

import { LiveStatusProvider, useLiveEvents, useLiveStatus } from "../context/LiveStatusContext";

afterEach(() => {
  vi.clearAllMocks();
  capturedWsOptions = {};
});

describe("LiveStatusProvider (achado nº 15)", () => {
  it("instancia UM polling e UMA conexão, não importa quantos consumidores", () => {
    function Consumer() {
      const { health, wsStatus } = useLiveStatus();
      return (
        <span>
          {health?.status}:{wsStatus}
        </span>
      );
    }

    const { getAllByText } = render(
      <LiveStatusProvider>
        <Consumer />
        <Consumer />
        <Consumer />
      </LiveStatusProvider>,
    );

    expect(diagnosticsSpy).toHaveBeenCalledTimes(1);
    expect(webSocketSpy).toHaveBeenCalledTimes(1);
    expect(webSocketSpy).toHaveBeenCalledWith("/ws/events", "chave-de-teste", expect.any(Object));
    expect(getAllByText("ok:open")).toHaveLength(3);
  });

  it("faz fan-out das mensagens do event bus para todos os inscritos", () => {
    const recebidasA: string[] = [];
    const recebidasB: string[] = [];

    function A() {
      useLiveEvents((e) => recebidasA.push(e.data as string));
      return null;
    }
    function B() {
      useLiveEvents((e) => recebidasB.push(e.data as string));
      return null;
    }

    render(
      <LiveStatusProvider>
        <A />
        <B />
      </LiveStatusProvider>,
    );

    act(() => {
      capturedWsOptions.onMessage?.({ data: "evento-1" } as MessageEvent);
      capturedWsOptions.onMessage?.({ data: "evento-2" } as MessageEvent);
    });

    expect(recebidasA).toEqual(["evento-1", "evento-2"]);
    expect(recebidasB).toEqual(["evento-1", "evento-2"]);
  });

  it("cancela a inscrição ao desmontar o consumidor", () => {
    const recebidas: string[] = [];
    function Efêmero() {
      useLiveEvents((e) => recebidas.push(e.data as string));
      return null;
    }

    const { unmount } = render(
      <LiveStatusProvider>
        <Efêmero />
      </LiveStatusProvider>,
    );

    act(() => capturedWsOptions.onMessage?.({ data: "antes" } as MessageEvent));
    unmount();
    act(() => capturedWsOptions.onMessage?.({ data: "depois" } as MessageEvent));

    expect(recebidas).toEqual(["antes"]);
  });
});
