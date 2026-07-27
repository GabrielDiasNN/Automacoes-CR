import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "../hooks/usePolling";

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("busca no mount, expõe o dado e sai de loading", async () => {
    const fetcher = vi.fn().mockResolvedValue({ total: 7 });
    const { result } = renderHook(() => usePolling(fetcher, 15_000));

    expect(result.current.loading).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual({ total: 7 });
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it("refaz o fetch a cada intervalo", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() => usePolling(fetcher, 1_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("não agenda intervalo quando intervalMs <= 0", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    renderHook(() => usePolling(fetcher, 0));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("expõe a mensagem de erro do fetcher e encerra o loading", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("401 nao autorizado"));
    const { result } = renderHook(() => usePolling(fetcher, 15_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.error).toBe("401 nao autorizado");
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it("converte rejeição que não é Error em string", async () => {
    const fetcher = vi.fn().mockRejectedValue("falha crua");
    const { result } = renderHook(() => usePolling(fetcher, 15_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.error).toBe("falha crua");
  });

  it("mantém o último dado válido quando um refresh posterior falha", async () => {
    // Contrato declarado no hook: refresh não deve causar flicker nem apagar a
    // tela por causa de uma falha transitória de rede.
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce("primeiro")
      .mockRejectedValueOnce(new Error("timeout"));

    const { result } = renderHook(() => usePolling(fetcher, 1_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.data).toBe("primeiro");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(result.current.error).toBe("timeout");
    expect(result.current.data).toBe("primeiro");
  });

  it("limpa o erro quando um refresh volta a ter sucesso", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("queda"))
      .mockResolvedValueOnce("recuperado");

    const { result } = renderHook(() => usePolling(fetcher, 1_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBe("queda");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(result.current.error).toBeNull();
    expect(result.current.data).toBe("recuperado");
  });

  it("refresh manual dispara o fetcher fora do intervalo", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => usePolling(fetcher, 60_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refresh();
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("mudança em deps força refresh imediato", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    const { rerender } = renderHook(
      ({ pagina }) => usePolling(fetcher, 60_000, [pagina]),
      { initialProps: { pagina: 1 } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    rerender({ pagina: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("usa sempre o fetcher mais recente sem reiniciar o intervalo", async () => {
    // O hook guarda o fetcher num ref de propósito: trocar a identidade da função
    // a cada render não deve derrubar e recriar o setInterval.
    const primeiro = vi.fn().mockResolvedValue("A");
    const segundo = vi.fn().mockResolvedValue("B");

    const { result, rerender } = renderHook(
      ({ fn }) => usePolling(fn, 1_000),
      { initialProps: { fn: primeiro } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(primeiro).toHaveBeenCalledTimes(1);

    rerender({ fn: segundo });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(primeiro).toHaveBeenCalledTimes(1);
    expect(segundo).toHaveBeenCalledTimes(1);
    expect(result.current.data).toBe("B");
  });

  it("para de buscar após o unmount", async () => {
    const fetcher = vi.fn().mockResolvedValue("ok");
    const { unmount } = renderHook(() => usePolling(fetcher, 1_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
