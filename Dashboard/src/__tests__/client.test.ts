import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, getApiKey, qs, setApiKey } from "../api/client";

describe("qs", () => {
  it("monta query-string a partir de um objeto", () => {
    expect(qs({ status: "SUCCESS", limit: 10 })).toBe("?status=SUCCESS&limit=10");
  });

  it("omite chaves com valor null, undefined ou string vazia", () => {
    expect(qs({ a: "1", b: null, c: undefined, d: "" })).toBe("?a=1");
  });

  it("retorna string vazia quando não há parâmetros válidos", () => {
    expect(qs({ a: null, b: undefined })).toBe("");
  });

  it("serializa booleanos e números como texto", () => {
    expect(qs({ enabled: true, count: 0 })).toBe("?enabled=true&count=0");
  });
});

describe("setApiKey / getApiKey", () => {
  afterEach(() => {
    setApiKey("");
  });

  it("armazena e recupera a chave em memória", () => {
    setApiKey("minha-chave");
    expect(getApiKey()).toBe("minha-chave");
  });

  it("permite limpar a chave", () => {
    setApiKey("minha-chave");
    setApiKey("");
    expect(getApiKey()).toBe("");
  });
});

describe("api.get", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setApiKey("chave-teste");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    setApiKey("");
  });

  it("envia o header X-API-Key quando a chave está definida", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    });
    globalThis.fetch = mockFetch as unknown as typeof fetch;

    await api.get("/api/system/health");

    const [, init] = mockFetch.mock.calls[0];
    expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("chave-teste");
  });

  it("lança erro com status e corpo quando a resposta não é ok", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      text: async () => "API key inválida",
    });
    globalThis.fetch = mockFetch as unknown as typeof fetch;

    await expect(api.get("/api/system/health")).rejects.toThrow("403 API key inválida");
  });
});
