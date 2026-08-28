import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi } from "../api/orchestrator";
import { setApiKey } from "../api/client";

describe("orchestratorApi", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => setApiKey("chave-teste"));
  afterEach(() => {
    globalThis.fetch = originalFetch;
    setApiKey("");
    vi.restoreAllMocks();
  });

  it("listAutomations desembrulha o campo `items` da resposta paginada", async () => {
    // Superfície de risco de baixa severidade: se o backend deixar de devolver
    // `{ items: [...] }`, a tela renderiza lista vazia sem erro. O teste trava o
    // contrato de que esse unwrap acontece na camada de API.
    const paginada = {
      items: [{ id: 1, name: "RB-01" }, { id: 2, name: "MT-02" }],
      page: 1,
      per_page: 25,
      total: 2,
      pages: 1,
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => paginada,
    }) as unknown as typeof fetch;

    const resultado = await orchestratorApi.listAutomations({ search: "R" });

    expect(Array.isArray(resultado)).toBe(true);
    expect(resultado).toHaveLength(2);
    expect(resultado[0]).toMatchObject({ id: 1, name: "RB-01" });
  });

  it("getExecution repassa o AbortSignal para o fetch", async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "X" }) });
    globalThis.fetch = mockFetch as unknown as typeof fetch;
    const controller = new AbortController();

    await orchestratorApi.getExecution("EXEC_1", controller.signal);

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/executions/EXEC_1");
    expect(init.signal).toBe(controller.signal);
  });
});
