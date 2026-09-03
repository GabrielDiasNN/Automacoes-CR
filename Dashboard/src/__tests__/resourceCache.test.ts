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
});
