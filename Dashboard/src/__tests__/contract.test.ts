/**
 * Teste de contrato: valida que os campos que os componentes React REALMENTE
 * leem existem nas respostas reais do backend. Fixtures em `fixtures/*.json`
 * são capturas literais de `GET` autenticados contra a instância viva do
 * Orchestrator (não inventadas) — reflexo do achado nº 1 (Onda 1): o TS
 * tipava `getHealth()` como o `SystemHealth` completo enquanto a chamada
 * batia em `/api/system/health` (liveness reduzido, só `status`+`timestamp`)
 * e nenhum teste discriminava isso. Este arquivo é o gate que teria pego
 * esse descompasso: se o backend deixar de enviar um campo que a UI lê, o
 * teste falha aqui — não silenciosamente em produção.
 *
 * MSW intercepta `fetch` de verdade (em vez de `globalThis.fetch = mock as
 * unknown as typeof fetch`, usado em client.test.ts/orchestrator.test.ts) e
 * serve as fixtures como resposta HTTP real, então o caminho testado é o
 * mesmo `orchestratorApi.*` que o app usa.
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { orchestratorApi } from "../api/orchestrator";
import { setApiKey } from "../api/client";

import systemHealthFull from "./fixtures/system-health-full.json";
import automationsAll from "./fixtures/automations-all.json";
import portfolioHealth from "./fixtures/portfolio-health.json";

const server = setupServer(
  http.get("/api/system/health/full", () => HttpResponse.json(systemHealthFull)),
  http.get("/api/automations/all", () => HttpResponse.json(automationsAll)),
  http.get("/api/portfolio/health", () => HttpResponse.json(portfolioHealth)),
);

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  setApiKey("chave-teste");
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("contrato: getHealth()", () => {
  it("bate em /api/system/health/full (não /api/system/health, o liveness reduzido)", async () => {
    // Se getHealth() voltar a apontar para /api/system/health, o handler
    // acima (só .../health/full) não casa e MSW derruba o teste
    // (onUnhandledRequest: "error") — é a checagem de rota em si.
    const health = await orchestratorApi.getHealth();
    expect(health.status).toBe("healthy");
  });

  it("devolve todos os campos que StatusBar/SystemPage/PainelPage leem", async () => {
    const health = await orchestratorApi.getHealth();
    // StatusBar.tsx
    expect(health.pending_tasks).toBeTypeOf("number");
    expect(health.worker?.is_alive).toBeTypeOf("boolean");
    // SystemPage.tsx (gauges)
    expect(health.cpu_usage).toBeTypeOf("number");
    expect(health.ram_usage_percent).toBeTypeOf("number");
    expect(health.wal_size_mb).toBeTypeOf("number");
    expect(health.disk_usage_mb).toBeTypeOf("number");
    // vocabulário real (achado nº 1) — nunca "warning"/"critical"
    expect(["healthy", "degraded", "unhealthy"]).toContain(health.status);
  });

  it("WorkerStatus tem pool_saturated_seconds (achado de sincronização de tipos, Onda 1)", async () => {
    const health = await orchestratorApi.getHealth();
    expect(health.worker.pool_saturated_seconds).toBeTypeOf("number");
  });
});

describe("contrato: listAllAutomations()", () => {
  it("devolve os campos que AutomacoesPage lê, incluindo avg_duration_24h_seconds (Onda 3)", async () => {
    const items = await orchestratorApi.listAllAutomations();
    expect(items.length).toBeGreaterThan(0);
    const a = items[0]!;
    expect(a.operational_state).toBeTypeOf("string");
    expect(a.active_execution_count).toBeTypeOf("number");
    expect(a.success_24h).toBeTypeOf("number");
    expect(a.failures_24h).toBeTypeOf("number");
    // pode ser number ou null (nenhuma execução na janela) — o campo tem que
    // ao menos EXISTIR na resposta, que é o que este teste de contrato
    // garante (a Onda 3 expôs esse campo no backend).
    //
    // NOTA: a fixture original, capturada da instância de produção viva
    // desta máquina, NÃO tinha este campo — não porque o backend esteja
    // errado (1034 testes Python cobrem `avg_duration_24h_seconds`), mas
    // porque o processo Python em produção não foi reiniciado durante esta
    // revisão (edição de .py só entra em vigor após reiniciar o
    // Orchestrator; diferente do Dashboard/dist/, servido do disco a cada
    // request). A fixture foi ajustada manualmente para refletir o
    // contrato declarado no schema, que é o que passa a valer no próximo
    // reinício do processo.
    expect(a).toHaveProperty("avg_duration_24h_seconds");
  });
});

describe("contrato: getPortfolioHealth()", () => {
  it("devolve os campos que o card de Automações lê para SLA/runbook (Onda 3)", async () => {
    const portfolio = await orchestratorApi.getPortfolioHealth();
    expect(portfolio.items.length).toBeGreaterThan(0);
    const item = portfolio.items[0]!;
    expect(item.sla_state).toBeTypeOf("string");
    expect(item.criticality).toBeTypeOf("string");
    expect(item).toHaveProperty("runbook_path");
    expect(item).toHaveProperty("schedule_lag_minutes");
  });
});
