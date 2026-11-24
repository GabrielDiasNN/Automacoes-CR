import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, getApiKey, qs, setApiKey, setUnauthorizedHandler } from "../api/client";

function mockJsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api/client — cobertura completa", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setApiKey("");
    setUnauthorizedHandler(null);
  });

  afterEach(() => {
    setApiKey("");
    setUnauthorizedHandler(null);
    vi.unstubAllGlobals();
  });

  describe("setApiKey / getApiKey e header X-API-Key", () => {
    it("armazena e recupera a chave e envia X-API-Key quando definida", async () => {
      setApiKey("segredo-123");
      expect(getApiKey()).toBe("segredo-123");

      fetchMock.mockResolvedValueOnce(mockJsonResponse({ ok: true }));
      await api.get<{ ok: boolean }>("/api/ping");

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(url).toBe("/api/ping");
      expect((init?.headers as Record<string, string>)["X-API-Key"]).toBe("segredo-123");
    });

    it("omite X-API-Key quando a chave esta vazia", async () => {
      setApiKey("");
      fetchMock.mockResolvedValueOnce(mockJsonResponse({ ok: true }));
      await api.get("/api/ping");

      const [, init] = fetchMock.mock.calls[0]!;
      expect(init?.headers).toEqual({});
    });
  });

  describe("ApiError", () => {
    it("expoe status, message formatada e retryAfter padrao null", () => {
      const err = new ApiError(500, "Falha interna");
      expect(err).toBeInstanceOf(Error);
      expect(err.name).toBe("ApiError");
      expect(err.status).toBe(500);
      expect(err.message).toBe("500 Falha interna");
      expect(err.retryAfter).toBeNull();
    });

    it("preserva retryAfter quando informado", () => {
      const err = new ApiError(429, "Rate limit", 45);
      expect(err.status).toBe(429);
      expect(err.retryAfter).toBe(45);
    });
  });

  describe("qs", () => {
    it("retorna string vazia quando nao ha parametros validos", () => {
      expect(qs({})).toBe("");
      expect(qs({ a: undefined, b: null, c: "" })).toBe("");
    });

    it("serializa strings, numeros (inclusive zero) e booleanos", () => {
      expect(qs({ page: 1, limit: 0, active: false, q: "teste", ignored: null })).toBe(
        "?page=1&limit=0&active=false&q=teste",
      );
    });
  });

  describe("metodos HTTP (get, getText, getBlob, post, put, patch, delete)", () => {
    it("getText retorna texto puro", async () => {
      fetchMock.mockResolvedValueOnce(new Response("# Runbook\nConteudo", { status: 200 }));
      const text = await api.getText("/api/portfolio/runbook/cat-1");
      expect(text).toBe("# Runbook\nConteudo");
      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/portfolio/runbook/cat-1");
    });

    it("getBlob retorna Blob binario com header X-API-Key", async () => {
      setApiKey("key-blob");
      const blobMock = new Blob(["conteudo-binario"], { type: "application/octet-stream" });
      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: vi.fn().mockResolvedValue(blobMock),
      } as unknown as Response);

      const res = await api.getBlob("/api/executions/e1/download?filename=a.pdf");
      expect(res).toBe(blobMock);
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(url).toBe("/api/executions/e1/download?filename=a.pdf");
      expect((init?.headers as Record<string, string>)["X-API-Key"]).toBe("key-blob");
    });

    it("post envia JSON quando body e informado e null quando omitido", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({ id: 1 }));
      const res1 = await api.post<{ id: number }>("/api/items", { name: "A" });
      expect(res1).toEqual({ id: 1 });
      const [, init1] = fetchMock.mock.calls[0]!;
      expect(init1?.method).toBe("POST");
      expect((init1?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
      expect(init1?.body).toBe(JSON.stringify({ name: "A" }));

      fetchMock.mockResolvedValueOnce(mockJsonResponse({ ok: true }));
      await api.post("/api/items/trigger");
      const [, init2] = fetchMock.mock.calls[1]!;
      expect(init2?.method).toBe("POST");
      expect(init2?.body).toBeNull();
    });

    it("put envia metodo PUT com corpo JSON ou null", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({ updated: true }));
      const res = await api.put<{ updated: boolean }>("/api/items/1", { name: "B" });
      expect(res).toEqual({ updated: true });
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(url).toBe("/api/items/1");
      expect(init?.method).toBe("PUT");
      expect(init?.body).toBe(JSON.stringify({ name: "B" }));

      fetchMock.mockResolvedValueOnce(mockJsonResponse({ ok: true }));
      await api.put("/api/items/1");
      expect(fetchMock.mock.calls[1]?.[1]?.body).toBeNull();
    });

    it("patch envia metodo PATCH com corpo JSON", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({ enabled: false }));
      const res = await api.patch<{ enabled: boolean }>("/api/automations/7", { enabled: false });
      expect(res).toEqual({ enabled: false });
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(url).toBe("/api/automations/7");
      expect(init?.method).toBe("PATCH");
      expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
      expect(init?.body).toBe(JSON.stringify({ enabled: false }));
    });

    it("delete envia metodo DELETE e retorna JSON", async () => {
      fetchMock.mockResolvedValueOnce(mockJsonResponse({ deleted: true }));
      const res = await api.delete<{ deleted: boolean }>("/api/items/9");
      expect(res).toEqual({ deleted: true });
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(url).toBe("/api/items/9");
      expect(init?.method).toBe("DELETE");
    });
  });

  describe("tratamento de erros, 401/403, Retry-After e AbortSignal", () => {
    it("chama unauthorizedHandler em 401", async () => {
      const onUnauth = vi.fn();
      setUnauthorizedHandler(onUnauth);
      fetchMock.mockResolvedValueOnce(new Response("Nao autorizado", { status: 401 }));

      await expect(api.get("/api/system/overview")).rejects.toMatchObject({
        name: "ApiError",
        status: 401,
        message: "401 Nao autorizado",
      });
      expect(onUnauth).toHaveBeenCalledWith(401);
    });

    it("chama unauthorizedHandler em 403 quando corpo menciona API Key", async () => {
      const onUnauth = vi.fn();
      setUnauthorizedHandler(onUnauth);
      fetchMock.mockResolvedValueOnce(new Response("API Key invalida ou ausente", { status: 403 }));

      await expect(api.get("/api/system/overview")).rejects.toBeInstanceOf(ApiError);
      expect(onUnauth).toHaveBeenCalledWith(403);
    });

    it("nao chama unauthorizedHandler em 403 de operacao proibida (path safety)", async () => {
      const onUnauth = vi.fn();
      setUnauthorizedHandler(onUnauth);
      fetchMock.mockResolvedValueOnce(new Response("Acesso negado ao arquivo.", { status: 403 }));

      await expect(api.getBlob("/api/executions/1/download?filename=../x")).rejects.toMatchObject({
        status: 403,
        message: "403 Acesso negado ao arquivo.",
      });
      expect(onUnauth).not.toHaveBeenCalled();
    });

    it("extrai Retry-After numerico em 429 e ignora valor nao numerico", async () => {
      fetchMock.mockResolvedValueOnce(
        new Response("Too Many Requests", {
          status: 429,
          headers: { "Retry-After": "12" },
        }),
      );
      await expect(api.get("/api/limited")).rejects.toMatchObject({
        status: 429,
        retryAfter: 12,
      });

      fetchMock.mockResolvedValueOnce(
        new Response("Too Many Requests", {
          status: 429,
          headers: { "Retry-After": "invalido" },
        }),
      );
      await expect(api.get("/api/limited")).rejects.toMatchObject({
        status: 429,
        retryAfter: null,
      });
    });

    it("faz fallback para statusText quando res.text() falha ou nao existe", async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        text: vi.fn().mockRejectedValue(new Error("stream error")),
        headers: new Headers(),
      } as unknown as Response);

      await expect(api.get("/api/broken")).rejects.toMatchObject({
        status: 502,
        message: "502 Bad Gateway",
      });

      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
      } as unknown as Response);

      await expect(api.get("/api/down")).rejects.toMatchObject({
        status: 503,
        message: "503 Service Unavailable",
      });

      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 500,
      } as unknown as Response);

      await expect(api.get("/api/empty")).rejects.toMatchObject({
        status: 500,
        message: "500 ",
      });
    });

    it("combina AbortSignal do chamador com timeout e propaga abort", async () => {
      const controller = new AbortController();
      controller.abort(new DOMException("Cancelado", "AbortError"));

      fetchMock.mockImplementationOnce(async (_url, init) => {
        expect(init?.signal).toBeInstanceOf(AbortSignal);
        expect(init?.signal?.aborted).toBe(true);
        throw new DOMException("Aborted", "AbortError");
      });

      await expect(api.get("/api/slow", controller.signal)).rejects.toThrow("Aborted");
    });
  });
});
