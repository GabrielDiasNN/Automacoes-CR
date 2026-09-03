import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getApiKey, qs, setApiKey, setUnauthorizedHandler } from "../api/client";

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
    setUnauthorizedHandler(null);
  });

  it("envia o header X-API-Key quando a chave está definida", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    });
    globalThis.fetch = mockFetch;

    await api.get("/api/system/health");

    const [, init] = mockFetch.mock.calls[0]!;
    expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("chave-teste");
  });

  it("lança erro com status e corpo quando a resposta não é ok", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      text: async () => "API key inválida",
    });
    globalThis.fetch = mockFetch;

    await expect(api.get("/api/system/health")).rejects.toThrow("403 API key inválida");
  });

  it("lança ApiError com status e sem retryAfter quando o header não vem", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      text: async () => "erro interno",
    });

    try {
      await api.get("/api/system/health");
      expect.unreachable("deveria ter lançado");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).status).toBe(500);
      expect((e as ApiError).retryAfter).toBeNull();
    }
  });

  it("lê Retry-After em 429 para permitir backoff no polling", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      statusText: "Too Many Requests",
      text: async () => "limite excedido",
      headers: { get: (name: string) => (name === "Retry-After" ? "60" : null) },
    });

    try {
      await api.get("/api/system/health");
      expect.unreachable("deveria ter lançado");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).status).toBe(429);
      expect((e as ApiError).retryAfter).toBe(60);
    }
  });
});

describe("setUnauthorizedHandler", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    setUnauthorizedHandler(null);
  });

  it("chama o handler ao receber status 401", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      text: async () => "Token expirado",
    });

    await expect(api.get("/api/system/overview")).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(401);
  });

  it("chama o handler ao receber status 403", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      text: async () => "Acesso negado",
    });

    await expect(api.get("/api/system/overview")).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(403);
  });

  it("não chama o handler para outros erros HTTP (ex: 400 ou 500)", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      text: async () => "Erro interno",
    });

    await expect(api.get("/api/system/overview")).rejects.toThrow();
    expect(handler).not.toHaveBeenCalled();
  });

  it("permite desregistrar o handler passando null", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setUnauthorizedHandler(null);

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      text: async () => "Token expirado",
    });

    await expect(api.get("/api/system/overview")).rejects.toThrow();
    expect(handler).not.toHaveBeenCalled();
  });
});
