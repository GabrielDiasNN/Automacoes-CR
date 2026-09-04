import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "../hooks/usePolling";
import { ApiError } from "../api/client";
import { _clearCache } from "../lib/resourceCache";

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    _clearCache();
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
    expect(sinais[0]!.aborted).toBe(true); // o anterior foi cancelado
    expect(sinais[1]!.aborted).toBe(false); // o atual segue em voo
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
    expect(sinais[0]!.aborted).toBe(true);
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

  it("com cacheKey, uma remontagem semeia data do cache e não mostra loading", async () => {
    const fetcher = vi.fn().mockResolvedValue({ n: 1 });
    const { result, unmount } = renderHook(() =>
      usePolling(fetcher, 60_000, [], { cacheKey: "ov" }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.data).toEqual({ n: 1 });
    unmount();

    // Remonta (equivale a /painel -> /sistema -> /painel): antes voltaria a
    // loading=true / data=null.
    const remount = renderHook(() => usePolling(fetcher, 60_000, [], { cacheKey: "ov" }));
    expect(remount.result.current.loading).toBe(false);
    expect(remount.result.current.data).toEqual({ n: 1 });
    // ...e ainda revalida por baixo (SWR).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("skipIfFresh: usa o cache e não faz requisição enquanto outra fonte o mantém fresco", async () => {
    const { writeCache } = await import("../lib/resourceCache");
    const fetcher = vi.fn().mockResolvedValue("da-rede");

    // Outra tela já gravou a chave há pouco.
    writeCache("health", "do-cache");

    const { result } = renderHook(() =>
      usePolling(fetcher, 1_000, [], { cacheKey: "health", cacheTtlMs: 5_000, skipIfFresh: true }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.data).toBe("do-cache");
    expect(result.current.loading).toBe(false);

    // Passado o TTL sem ninguém renovar, a requisição real volta (auto-cura).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(fetcher).toHaveBeenCalled();
    expect(result.current.data).toBe("da-rede");
  });

  it("onData roda a cada sucesso (para derivar chaves de cache de um payload composto)", async () => {
    const { readCache, writeCache } = await import("../lib/resourceCache");
    const fetcher = vi.fn().mockResolvedValue({ health: { status: "healthy" }, outra: 1 });
    renderHook(() =>
      usePolling(fetcher, 60_000, [], {
        onData: (d: { health: unknown }) => writeCache("health", d.health),
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(readCache("health", 30_000)).toEqual({ status: "healthy" });
  });

  it("refresh durante a janela de 429 enfileira em vez de virar no-op silencioso", async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new ApiError(429, "limite", 10));
    const { result } = renderHook(() => usePolling(fetcher, 0)); // sem intervalo

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.refreshQueued).toBe(false);

    // Operador dispara um refresh manual DENTRO da janela — antes: no-op mudo.
    fetcher.mockResolvedValue("fresco");
    await act(async () => {
      await result.current.refresh();
    });
    expect(fetcher).toHaveBeenCalledTimes(1); // não bateu no backend ainda
    expect(result.current.refreshQueued).toBe(true);
    expect(result.current.loading).toBe(false); // não ficou preso

    // Passada a janela, o refresh enfileirado dispara sozinho.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_100);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.data).toBe("fresco");
    expect(result.current.refreshQueued).toBe(false);
  });

  it("erro não-429 após janela de 429 limpa rateLimitedUntil para não carregar semântica de rate limit", async () => {
    // Cenário: primeiro um 429 (seta rateLimitedUntil), depois um erro genérico (ex: 500).
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(429, "limite", 5))
      .mockRejectedValueOnce(new Error("servidor indisponível"));

    const { result } = renderHook(() => usePolling(fetcher, 1_000));

    // Primeiro fetch: 429 — seta rateLimitedUntil e mostra mensagem de limite.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.rateLimitedUntil).toBeInstanceOf(Date);
    expect(result.current.error).toContain("limite");

    // Espera passar a janela de 429.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100);
    });

    // Próximo fetch: erro diferente (500, timeout, etc.). Deve limpar rateLimitedUntil
    // para que FreshnessTag não confunda o novo erro com semântica de rate limit.
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBe("servidor indisponível");
    expect(result.current.rateLimitedUntil).toBeNull();
  });
});
