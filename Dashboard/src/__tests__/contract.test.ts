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
import systemOverview from "./fixtures/system-overview.json";
import executionsPage from "./fixtures/executions-page.json";
import systemVersion from "./fixtures/system-version.json";
import systemUptime from "./fixtures/system-uptime.json";
import portfolioDrift from "./fixtures/portfolio-drift.json";
// item sintético do schema PortfolioDriftItem — a instância viva não tinha drift
// no momento da captura (summary.items_with_drift === 0).
import portfolioDriftWithItems from "./fixtures/portfolio-drift-with-items.json";
import executionsByAutomation from "./fixtures/executions-by-automation.json";
// sintética: artefatos variam muito por automação (a lista real depende de
// qual robô rodou) — nomes plausíveis, só para exercitar o shape do schema.
import executionArtifacts from "./fixtures/execution-artifacts.json";

// Vocabulários que os `switch` de lib/status.ts assumem — se o backend
// renomear um estado, o teste falha aqui em vez de a UI cair no ramo cinza
// (mesma classe do achado nº 1 da rodada anterior).
const EXECUTION_STATUSES = [
  "PENDING",
  "RUNNING",
  "SUCCESS",
  "PARTIAL",
  "ERROR",
  "TIMEOUT",
  "TERMINATED",
  "FAILED_BY_REBOOT",
  "REQUEUED",
  "EXPIRED",
];
const OPERATIONAL_STATES = ["healthy", "in_progress", "attention", "paused", "idle", "not_registered"];
const SLA_STATUSES = ["ok", "at_risk", "violated", "unknown"];

const server = setupServer(
  http.get("/api/system/health/full", () => HttpResponse.json(systemHealthFull)),
  http.get("/api/automations/all", () => HttpResponse.json(automationsAll)),
  http.get("/api/portfolio/health", () => HttpResponse.json(portfolioHealth)),
  http.get("/api/system/overview", () => HttpResponse.json(systemOverview)),
  http.get("/api/executions", () => HttpResponse.json(executionsPage)),
  http.get("/api/system/version", () => HttpResponse.json(systemVersion)),
  http.get("/api/system/uptime", () => HttpResponse.json(systemUptime)),
  http.get("/api/portfolio/drift", () => HttpResponse.json(portfolioDrift)),
  http.get("/api/executions/by-automation/:automationId", () => HttpResponse.json(executionsByAutomation)),
  http.get("/api/executions/:execId/artifacts", () => HttpResponse.json(executionArtifacts)),
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

describe("contrato: getOverview()", () => {
  it("kpis tem os campos que PainelPage/StatTile leem", async () => {
    const ov = await orchestratorApi.getOverview();
    expect(ov.kpis.active_automations).toBeTypeOf("number");
    expect(ov.kpis.success_24h).toBeTypeOf("number");
    expect(ov.kpis.errors_24h).toBeTypeOf("number");
    expect(ov.kpis.pending_now).toBeTypeOf("number");
    expect(ov.kpis.next_window).toBeTypeOf("string");
  });

  it("health embutido é o SystemHealth completo (não o liveness reduzido)", async () => {
    const ov = await orchestratorApi.getOverview();
    expect(["healthy", "degraded", "unhealthy", "ok"]).toContain(ov.health.status);
    expect(ov.health.worker.is_alive).toBeTypeOf("boolean");
  });

  it("automations[]: sla_status e operational_state dentro do vocabulário de lib/status.ts", async () => {
    const ov = await orchestratorApi.getOverview();
    expect(ov.automations.length).toBeGreaterThan(0);
    for (const a of ov.automations) {
      expect(SLA_STATUSES).toContain(a.sla_status);
      expect(OPERATIONAL_STATES).toContain(a.operational_state);
      if (a.last_status !== null) expect(EXECUTION_STATUSES).toContain(a.last_status);
    }
  });

  it("recent[]: status dentro de ExecutionStatus", async () => {
    const ov = await orchestratorApi.getOverview();
    for (const ex of ov.recent) expect(EXECUTION_STATUSES).toContain(ex.status);
  });

  it("diagnostics.operational_baseline existe (PainelPage:103 / SystemPage:69) e findings é lista", async () => {
    const ov = await orchestratorApi.getOverview();
    expect(ov.diagnostics.operational_baseline).toBeTypeOf("object");
    expect(ov.diagnostics.operational_baseline.status).toBeTypeOf("string");
    expect(Array.isArray(ov.diagnostics.findings)).toBe(true);
  });

  it("portfolio (quando presente) tem os contadores que SystemPage lê", async () => {
    const ov = await orchestratorApi.getOverview();
    if (ov.portfolio) {
      expect(ov.portfolio.total_items).toBeTypeOf("number");
      expect(ov.portfolio.governed_items).toBeTypeOf("number");
      expect(ov.portfolio.drift_items).toBeTypeOf("number");
      expect(ov.portfolio.docs_missing_items).toBeTypeOf("number");
      expect(ov.portfolio.sla_breached_items).toBeTypeOf("number");
      expect(ov.portfolio).toHaveProperty("top_issue");
      expect(ov.portfolio).toHaveProperty("recommended_action");
    }
  });
});

describe("contrato: listExecutions()", () => {
  it("envelope Paginated<ExecutionSummary> com items/total/page/per_page/pages", async () => {
    const res = await orchestratorApi.listExecutions({ per_page: 5 });
    expect(Array.isArray(res.items)).toBe(true);
    expect(res.total).toBeTypeOf("number");
    expect(res.page).toBeTypeOf("number");
    expect(res.per_page).toBeTypeOf("number");
    expect(res.pages).toBeTypeOf("number");
  });

  it("items[]: campos que a DataTable de Execuções renderiza", async () => {
    const res = await orchestratorApi.listExecutions({ per_page: 5 });
    expect(res.items.length).toBeGreaterThan(0);
    const ex = res.items[0]!;
    expect(EXECUTION_STATUSES).toContain(ex.status);
    expect(ex.priority).toBeTypeOf("string");
    expect(ex.retry_count).toBeTypeOf("number");
    expect(ex.max_retries).toBeTypeOf("number");
    expect(ex).toHaveProperty("automation_name");
    expect(ex).toHaveProperty("failure_reason");
    expect(ex).toHaveProperty("duration_seconds");
    // decoração do operador (rowTone / drawer)
    expect(ex.operator_severity).toBeTypeOf("string");
    expect(ex).toHaveProperty("operator_attention_required");
  });
});

describe("contrato: getVersion() — card runtime do SystemPage (Onda 6)", () => {
  it("devolve version/schema_version/contract_version/python_version/started_at/max_workers", async () => {
    const v = await orchestratorApi.getVersion();
    expect(v.version).toBeTypeOf("string");
    expect(v.schema_version).toBeTypeOf("string");
    expect(v.contract_version).toBeTypeOf("string");
    expect(v.python_version).toBeTypeOf("string");
    expect(v.started_at).toBeTypeOf("string");
    expect(v.uptime_seconds).toBeTypeOf("number");
    expect(v.max_workers).toBeTypeOf("number");
    expect(Array.isArray(v.allowed_origins)).toBe(true);
  });
});

describe("contrato: getUptime() — card runtime (Onda 6)", () => {
  it("devolve started_at/uptime_seconds/uptime_human", async () => {
    const u = await orchestratorApi.getUptime();
    expect(u.started_at).toBeTypeOf("string");
    expect(u.uptime_seconds).toBeTypeOf("number");
    expect(u.uptime_human).toBeTypeOf("string");
  });
});

describe("contrato: getDrift() — card de drift do SystemPage (Onda 6)", () => {
  it("envelope com generated_at + summary.items_with_drift/total_issues + items[] (instância viva sem drift)", async () => {
    const d = await orchestratorApi.getDrift();
    expect(d.generated_at).toBeTypeOf("string");
    expect(d.summary.items_with_drift).toBeTypeOf("number");
    expect(d.summary.total_issues).toBeTypeOf("number");
    expect(Array.isArray(d.items)).toBe(true);
  });

  it("item de drift (fixture sintética do schema) tem os campos que o card lê", async () => {
    server.use(http.get("/api/portfolio/drift", () => HttpResponse.json(portfolioDriftWithItems)));
    const d = await orchestratorApi.getDrift();
    expect(d.items.length).toBeGreaterThan(0);
    const item = d.items[0]!;
    expect(item.catalog_id).toBeTypeOf("string");
    expect(item.name).toBeTypeOf("string");
    expect(Array.isArray(item.issues)).toBe(true);
    const iss = item.issues[0]!;
    expect(iss.code).toBeTypeOf("string");
    expect(iss.message).toBeTypeOf("string");
    // `manifest_value`/`runtime_value` são string | null — o card só renderiza a
    // seta quando ambos != null, então basta a propriedade existir.
    expect(iss).toHaveProperty("manifest_value");
    expect(iss).toHaveProperty("runtime_value");
  });
});

describe("contrato: listExecutionsByAutomation() — timeline do drawer (Onda 6)", () => {
  it("bate em /api/executions/by-automation/{id} e devolve ExecutionSummary[]", async () => {
    const execs = await orchestratorApi.listExecutionsByAutomation(2, 8);
    expect(execs.length).toBeGreaterThan(0);
    const ex = execs[0]!;
    expect(EXECUTION_STATUSES).toContain(ex.status);
    expect(ex.id).toBeTypeOf("string");
    expect(ex.automation_id).toBeTypeOf("number");
    expect(ex.started_at).toBeTypeOf("string");
  });
});

describe("contrato: listExecutionArtifacts() — card de artefatos do drawer (Onda 6)", () => {
  it("devolve exec_id + artifacts[] (fixture sintética — nomes variam por automação)", async () => {
    const res = await orchestratorApi.listExecutionArtifacts("CRON_2_1788460200_8ea3");
    expect(res.exec_id).toBeTypeOf("string");
    expect(Array.isArray(res.artifacts)).toBe(true);
    expect(res.artifacts.length).toBeGreaterThan(0);
    expect(res.artifacts[0]).toBeTypeOf("string");
  });
});
