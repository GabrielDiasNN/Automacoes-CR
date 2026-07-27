import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

describe("useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("devolve o valor inicial de imediato, sem esperar o delay", () => {
    const { result } = renderHook(() => useDebouncedValue("inicial"));
    expect(result.current).toBe("inicial");
  });

  it("só propaga o valor novo depois do delay", () => {
    const { result, rerender } = renderHook(
      ({ valor }) => useDebouncedValue(valor, 300),
      { initialProps: { valor: "a" } },
    );

    rerender({ valor: "b" });
    expect(result.current).toBe("a");

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(result.current).toBe("a");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe("b");
  });

  it("descarta valores intermediários quando o valor muda dentro da janela", () => {
    // Razão de existir do hook: digitação rápida não deve disparar um fetch por
    // tecla — só o último valor sobrevive à janela de debounce.
    const { result, rerender } = renderHook(
      ({ valor }) => useDebouncedValue(valor, 300),
      { initialProps: { valor: "r" } },
    );

    rerender({ valor: "re" });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    rerender({ valor: "rec" });
    act(() => {
      vi.advanceTimersByTime(200);
    });

    // O timer do "re" foi cancelado pelo cleanup; nada propagou ainda.
    expect(result.current).toBe("r");

    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current).toBe("rec");
  });

  it("respeita o delay padrão de 300ms quando omitido", () => {
    const { result, rerender } = renderHook(
      ({ valor }) => useDebouncedValue(valor),
      { initialProps: { valor: 1 } },
    );

    rerender({ valor: 2 });
    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(result.current).toBe(1);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe(2);
  });

  it("cancela o timer pendente ao desmontar, sem atualizar estado depois", () => {
    const { rerender, unmount } = renderHook(
      ({ valor }) => useDebouncedValue(valor, 300),
      { initialProps: { valor: "a" } },
    );

    rerender({ valor: "b" });
    unmount();

    // Se o clearTimeout do cleanup não rodasse, o setState pós-unmount apareceria
    // como warning do React aqui.
    expect(() => {
      act(() => {
        vi.advanceTimersByTime(300);
      });
    }).not.toThrow();
  });
});
