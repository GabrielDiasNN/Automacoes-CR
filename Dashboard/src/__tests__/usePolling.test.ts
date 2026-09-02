import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "../hooks/usePolling";
import { ApiError } from "../api/client";

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

  it("descarta resposta que chega fora de ordem", async () => {
    // Trocar de página/filtro dispara um novo fetch antes do anterior voltar.
    // Se a resposta antiga chegar depois, ela NÃO pode sobrescrever a tela —
    // seriam dados que não correspondem aos parâmetros atuais.
    const fetcher = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => setTimeout(() => resolve("antigo"), 5_000)),
      )
      .mockImplementationOnce(() => Promise.resolve("novo"));

    const { result, rerender } = renderHook(
      ({ pagina }) => usePolling(fetcher, 60_000, [pagina]),
      { initialProps: { pagina: 1 } },
    );

    rerender({ pagina: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.data).toBe("novo");

    // A resposta lenta da primeira chamada chega agora e deve ser ignorada.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(result.current.data).toBe("novo");
  });

  it("aborta o fetch anterior ao disparar um novo", async () => {
    const sinais: AbortSignal[] = [];
    const fetcher = vi.fn((signal?: AbortSignal) => {
      if (signal) sinais.push(signal);
      return new Promise<string>((resolve) => setTimeout(() => resolve("ok"), 5_000));
    });

    const { rerender } = renderHook(
      ({ pagina }) => usePolling(fetcher, 60_000, [pagina]),
      { initialProps: { pagina: 1 } },
    );

    rerender({ pagina: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(sinais).toHaveLength(2);
    expect(sinais[0].aborted).toBe(true); // o anterior foi cancelado
    expect(sinais[1].aborted).toBe(false); // o atual segue em voo
  });

  it("aborta o fetch em voo no unmount", async () => {
    const sinais: AbortSignal[] = [];
    const fetcher = vi.fn((signal?: AbortSignal) => {
      if (signal) sinais.push(signal);
      return new Promise<string>((resolve) => setTimeout(() => resolve("ok"), 5_000));
    });

    const { unmount } = renderHook(() => usePolling(fetcher, 60_000));
    unmount();

    expect(sinais).toHaveLength(1);
    expect(sinais[0].aborted).toBe(true);
  });

  it("não expõe o cancelamento como erro de tela", async () => {
    const fetcher = vi.fn((signal?: AbortSignal) => {
      return new Promise<string>((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          const err = new Error("The operation was aborted.");
          err.name = "AbortError";
          reject(err);
        });
      });
    });

    const { result, rerender } = renderHook(
      ({ pagina }) => usePolling(fetcher, 60_000, [pagina]),
      { initialProps: { pagina: 1 } },
    );

    rerender({ pagina: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.error).toBeNull();
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

  it("em 429, expõe rateLimitedUntil e pula ticks até a janela liberar (sem martelar o backend)", async () => {
    const fetcher = vi.fn().mockRejectedValue(new ApiError(429, "limite excedido", 10));
    const { result } = renderHook(() => usePolling(fetcher, 1_000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.rateLimitedUntil).toBeInstanceOf(Date);
    expect(result.current.error).toContain("10s");

    // Ticks dentro da janela de 10s: nenhuma requisição nova.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    // Passada a janela, os próximos ticks voltam a tentar de verdade — não
    // importa quantos ticks exatos ocorrem no avanço, o que importa é que a
    // janela é respeitada (nenhuma chamada nova antes dela) e depois libera.
    fetcher.mockResolvedValue("ok");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(fetcher.mock.calls.length).toBeGreaterThan(1);
    expect(result.current.rateLimitedUntil).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
