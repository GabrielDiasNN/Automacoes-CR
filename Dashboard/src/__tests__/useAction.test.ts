import { act, renderHook, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createElement, type ReactNode } from "react";
import { useAction } from "../hooks/useAction";
// Direto do módulo fonte (não do barrel `components/ui`) — o barrel também
// exporta TimeSeries, que importa `uplot` e quebra em jsdom sem
// `matchMedia`. useAction só precisa do ToastProvider.
import { ToastProvider } from "../components/ui/Toast";

// useAction usa useToast() por baixo — precisa do provider no contexto. O
// jeito de inspecionar a mensagem é ler o toast realmente renderizado (o
// hook não expõe estado próprio de mensagem), igual um consumidor real veria.
function wrapper({ children }: { children: ReactNode }) {
  return createElement(ToastProvider, null, children);
}

describe("useAction", () => {
  // cleanup() automático entre testes vem de setupFiles (vitest.config.ts) —
  // sem ele, o toast de um teste permanecia no DOM quando o próximo rodava,
  // e screen.getByText pegava o elemento errado (achado que motivou o
  // afterEach manual que existia aqui antes do setupFiles ser configurado).

  it("usa a mensagem do backend (r.message) como sucesso por padrão", async () => {
    const { result } = renderHook(() => useAction<string>(), { wrapper });
    await act(async () => {
      await result.current.run("x", () => Promise.resolve({ message: "feito pelo backend" }));
    });
    expect(screen.getByText("feito pelo backend")).toBeTruthy();
  });

  it("overrideMessage tem prioridade sobre r.message", async () => {
    const { result } = renderHook(() => useAction<string>(), { wrapper });
    await act(async () => {
      await result.current.run("x", () => Promise.resolve({ message: "genérica" }), {
        overrideMessage: "mensagem específica do chamador",
      });
    });
    expect(screen.queryByText("genérica")).toBeNull();
    expect(screen.getByText("mensagem específica do chamador")).toBeTruthy();
  });

  it("fallbackMessage só é usado quando r.message vem vazio", async () => {
    const { result } = renderHook(() => useAction<string>(), { wrapper });
    await act(async () => {
      await result.current.run("x", () => Promise.resolve({ message: "" }), {
        fallbackMessage: "automação pausada",
      });
    });
    expect(screen.getByText("automação pausada")).toBeTruthy();
  });

  it("erro vira toast (tom vermelho, texto da exceção) e não chama onDone", async () => {
    const onDone = vi.fn();
    const { result } = renderHook(() => useAction<string>(), { wrapper });
    await act(async () => {
      await result.current.run("x", () => Promise.reject(new Error("falhou de verdade")), { onDone });
    });
    expect(screen.getByText("falhou de verdade")).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("busyKey reflete a ação em andamento e volta a null ao terminar", async () => {
    let resolveFn: (() => void) | undefined;
    const pending = new Promise<{ message: string }>((resolve) => {
      resolveFn = () => resolve({ message: "ok" });
    });
    const { result } = renderHook(() => useAction<number>(), { wrapper });

    let runPromise!: Promise<void>;
    act(() => {
      runPromise = result.current.run(42, () => pending);
    });
    expect(result.current.busyKey).toBe(42);
    expect(result.current.isBusy(42)).toBe(true);

    await act(async () => {
      resolveFn?.();
      await runPromise;
    });
    expect(result.current.busyKey).toBeNull();
  });

  it("onDone roda após o sucesso", async () => {
    const onDone = vi.fn();
    const { result } = renderHook(() => useAction<string>(), { wrapper });
    await act(async () => {
      await result.current.run("x", () => Promise.resolve({ message: "ok" }), { onDone });
    });
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
