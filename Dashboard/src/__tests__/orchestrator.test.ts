import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { orchestratorApi } from "../api/orchestrator";
import { setApiKey } from "../api/client";

// Só este teste (sobre o SHAPE dos dados devolvidos, não a mecânica de
// transporte) migrou para MSW — os demais deste arquivo inspecionam
// headers/mecanismo de fetch em si, onde um mock direto continua mais
// natural. Servidor próprio (não o de contract.test.ts) para não acoplar
// os dois arquivos de teste um ao outro.
const server = setupServer(
  http.get("/api/automations", () =>
    HttpResponse.json({
      items: [{ id: 1, name: "RB-01" }, { id: 2, name: "MT-02" }],
      page: 1,
      per_page: 25,
      total: 2,
      pages: 1,
    }),
  ),
);

describe("orchestratorApi", () => {
  const originalFetch = globalThis.fetch;

  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  afterAll(() => server.close());
  beforeEach(() => setApiKey("chave-teste"));
  afterEach(() => {
    server.resetHandlers();
    globalThis.fetch = originalFetch;
    setApiKey("");
    vi.restoreAllMocks();
  });

  it("listAutomations desembrulha o campo `items` da resposta paginada", async () => {
    // Superfície de risco de baixa severidade: se o backend deixar de devolver
    // `{ items: [...] }`, a tela renderiza lista vazia sem erro. O teste trava o
    // contrato de que esse unwrap acontece na camada de API.
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
    // `client.ts` combina o signal do chamador com um timeout via
    // `AbortSignal.any` (achado nº 5, Onda 1) — não é mais o MESMO objeto,
    // mas precisa continuar abortando quando o `controller` original aborta.
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect((init.signal as AbortSignal).aborted).toBe(false);
    controller.abort();
    expect((init.signal as AbortSignal).aborted).toBe(true);
  });
});
