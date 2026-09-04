import { afterEach, describe, expect, it, vi } from "vitest";
import { _clearCache, invalidateCache, readCache, writeCache } from "../lib/resourceCache";

afterEach(() => {
  _clearCache();
  vi.useRealTimers();
});

describe("resourceCache", () => {
  it("lê o que foi escrito dentro do TTL", () => {
    writeCache("overview", { total: 3 });
    expect(readCache("overview", 30_000)).toEqual({ total: 3 });
  });

  it("expira e remove a entrada quando passa do TTL", () => {
    vi.useFakeTimers();
    writeCache("overview", { total: 3 });
    vi.advanceTimersByTime(31_000);
    expect(readCache("overview", 30_000)).toBeUndefined();
    // segunda leitura confirma que foi removida, não só ignorada
    expect(readCache("overview", 999_999)).toBeUndefined();
  });

  it("miss devolve undefined (distinto de um valor nulo cacheado)", () => {
    writeCache("nulo", null);
    expect(readCache("nulo", 30_000)).toBeNull();
    expect(readCache("ausente", 30_000)).toBeUndefined();
  });

  it("invalida chave exata", () => {
    writeCache("a", 1);
    writeCache("b", 2);
    invalidateCache("a");
    expect(readCache("a", 30_000)).toBeUndefined();
    expect(readCache("b", 30_000)).toBe(2);
  });

  it("invalida por prefixo quando a chave termina em ':'", () => {
    writeCache("exec:1", "um");
    writeCache("exec:2", "dois");
    writeCache("overview", "outro");
    invalidateCache("exec:");
    expect(readCache("exec:1", 30_000)).toBeUndefined();
    expect(readCache("exec:2", 30_000)).toBeUndefined();
    expect(readCache("overview", 30_000)).toBe("outro");
  });

  it("writeCache congela o valor: mutação lança em vez de contaminar o outro consumidor", () => {
    // Cenário: dois consumidores leem a mesma chave; um tenta mutar. Congelado,
    // a tentativa lança (strict mode) em vez de corromper a leitura seguinte.
    const originalArray = [1, 2, 3];
    const originalObject = { name: "automacao", count: 5 };

    writeCache("arr", originalArray);
    writeCache("obj", originalObject);

    const firstArr = readCache<typeof originalArray>("arr", 30_000)!;
    expect(() => firstArr.push(999)).toThrow();
    expect(readCache<typeof originalArray>("arr", 30_000)).toEqual([1, 2, 3]);

    const firstObj = readCache<typeof originalObject>("obj", 30_000)!;
    expect(() => {
      firstObj.count = 999;
    }).toThrow();
    expect(readCache<typeof originalObject>("obj", 30_000)?.count).toBe(5);
  });

  it("readCache mantém a referência estável entre leituras (evita re-render no dedupe)", () => {
    // usePolling faz setData(cached) a cada tick do caminho skipIfFresh; se a
    // referência mudasse, o React re-renderizaria a cada 15s sem dado novo.
    const payload = { name: "automacao", count: 5 };
    writeCache("estavel", payload);

    const primeira = readCache<typeof payload>("estavel", 30_000);
    const segunda = readCache<typeof payload>("estavel", 30_000);

    expect(primeira).toBe(segunda);
  });

  it("readCache preserva valores primitivos e null sem cópia desnecessária", () => {
    writeCache("str", "texto");
    writeCache("num", 42);
    writeCache("nulo", null);

    expect(readCache("str", 30_000)).toBe("texto");
    expect(readCache("num", 30_000)).toBe(42);
    expect(readCache("nulo", 30_000)).toBeNull();
  });
});
