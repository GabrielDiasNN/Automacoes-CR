import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, setApiKey } from "../api/client";
import { orchestratorApi } from "../api/orchestrator";

function okJson(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api/orchestrator — cobertura completa de rotas", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setApiKey("test-key");
  });

  afterEach(() => {
    setApiKey("");
    vi.unstubAllGlobals();
  });

  describe("Automacoes", () => {
    it("listAutomations retorna items e serializa query params", async () => {
      fetchMock.mockResolvedValueOnce(okJson({ items: [{ id: 1, name: "Auto A" }], total: 1, page: 2, per_page: 20, pages: 1 }));
      const items = await orchestratorApi.listAutomations({ page: 2, per_page: 20, search: "Auto", sort: "name", order: "asc" });
      expect(items).toEqual([{ id: 1, name: "Auto A" }]);
      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/automations?page=2&per_page=20&search=Auto&sort=name&order=asc");
    });

    it("listAllAutomations consulta /api/automations/all", async () => {
      fetchMock.mockResolvedValueOnce(okJson([]));
      const res = await orchestratorApi.listAllAutomations();
      expect(res).toEqual([]);
      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/automations/all");
    });

    it("updateAutomation envia PATCH com payload", async () => {
      fetchMock.mockResolvedValueOnce(okJson({ id: 4, enabled: false }));
      await orchestratorApi.updateAutomation(4, { enabled: false, max_retries: 2 });
      const [url, init] = fetchMock.mock.calls[0]!;
      expect(url).toBe("/api/automations/4");
      expect(init?.method).toBe("PATCH");
      expect(init?.body).toBe(JSON.stringify({ enabled: false, max_retries: 2 }));
    });

    it("startAutomation, pauseAutomation e resumeAutomation enviam POST nas rotas corretas", async () => {
      fetchMock
        .mockResolvedValueOnce(okJson({ message: "ok", exec_id: "e1" }))
        .mockResolvedValueOnce(okJson({ message: "paused" }))
        .mockResolvedValueOnce(okJson({ message: "resumed" }));

      await orchestratorApi.startAutomation(10);
      await orchestratorApi.pauseAutomation(10);
      await orchestratorApi.resumeAutomation(10);

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/automations/10/start");
      expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/automations/10/pause");
      expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/automations/10/resume");
      expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("POST");
    });

    it("setAutomationTestMode, setGlobalTestMode, pauseAll e resumeAll enviam POST", async () => {
      fetchMock
        .mockResolvedValueOnce(okJson({ message: "ok" }))
        .mockResolvedValueOnce(okJson({ message: "ok" }))
        .mockResolvedValueOnce(okJson({ message: "ok" }))
        .mockResolvedValueOnce(okJson({ message: "ok" }));

      await orchestratorApi.setAutomationTestMode(3, true);
      await orchestratorApi.setGlobalTestMode(false);
      await orchestratorApi.pauseAll();
      await orchestratorApi.resumeAll();

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/automations/3/test-mode");
      expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ enabled: true }));
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/automations/test-mode/global");
      expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({ enabled: false }));
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/automations/control/pause-all");
      expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/automations/control/resume-all");
    });

    it("previewSchedule usa limit default 5 e aceita limit customizado", async () => {
      fetchMock
        .mockResolvedValueOnce(okJson({ valid: true, next_runs_preview: [], errors: [] }))
        .mockResolvedValueOnce(okJson({ valid: true, next_runs_preview: [], errors: [] }));

      await orchestratorApi.previewSchedule("0 8 * * *");
      await orchestratorApi.previewSchedule(null, 10);

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/system/schedule/preview");
      expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ schedule: "0 8 * * *", limit: 5 }));
      expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({ schedule: null, limit: 10 }));
    });
  });

  describe("Execucoes", () => {
    it("listExecutions, getExecution, stopExecution e requeueExecution", async () => {
      fetchMock
        .mockResolvedValueOnce(okJson({ items: [], total: 0, page: 1, per_page: 25, pages: 0 }))
        .mockResolvedValueOnce(okJson({ id: "exec-1" }))
        .mockResolvedValueOnce(okJson({ message: "stopped" }))
        .mockResolvedValueOnce(okJson({ message: "requeued" }))
        .mockResolvedValueOnce(okJson({ message: "requeued" }));

      await orchestratorApi.listExecutions({ page: 1, status: "ERROR", automation_id: 5 });
      await orchestratorApi.getExecution("exec-1");
      await orchestratorApi.stopExecution("exec-1");
      await orchestratorApi.requeueExecution("exec-1");
      await orchestratorApi.requeueExecution("exec-1", { reason: "manual", priority: "HIGH" });

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/executions?page=1&status=ERROR&automation_id=5");
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/executions/exec-1");
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/executions/exec-1/stop");
      expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/executions/exec-1/requeue");
      expect(fetchMock.mock.calls[3]?.[1]?.body).toBe(JSON.stringify({}));
      expect(fetchMock.mock.calls[4]?.[1]?.body).toBe(JSON.stringify({ reason: "manual", priority: "HIGH" }));
    });

    it("listExecutionsByAutomation, listExecutionArtifacts e downloadExecutionArtifact", async () => {
      const fakeBlob = new Blob(["pdf"], { type: "application/pdf" });
      fetchMock
        .mockResolvedValueOnce(okJson([]))
        .mockResolvedValueOnce(okJson([]))
        .mockResolvedValueOnce(okJson({ exec_id: "e1", artifacts: ["rel.pdf"] }))
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          blob: vi.fn().mockResolvedValue(fakeBlob),
        } as unknown as Response);

      await orchestratorApi.listExecutionsByAutomation(7);
      await orchestratorApi.listExecutionsByAutomation(7, 25);
      await orchestratorApi.listExecutionArtifacts("e1");
      const blob = await orchestratorApi.downloadExecutionArtifact("e1", "rel.pdf");

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/executions/by-automation/7?limit=10");
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/executions/by-automation/7?limit=25");
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/executions/e1/artifacts");
      expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/executions/e1/download?filename=rel.pdf");
      expect(blob).toBe(fakeBlob);
    });
  });

  describe("Sistema", () => {
    it("chama todas as rotas de leitura e manutencao do sistema", async () => {
      for (let i = 0; i < 14; i++) {
        fetchMock.mockResolvedValueOnce(okJson({ ok: true }));
      }

      await orchestratorApi.getHealth();
      await orchestratorApi.getOverview();
      await orchestratorApi.getHistory();
      await orchestratorApi.getHistory(48);
      await orchestratorApi.getSystemMetricsDaily();
      await orchestratorApi.getSystemMetricsDaily(30);
      await orchestratorApi.runCheckpoint();
      await orchestratorApi.runPurge();
      await orchestratorApi.recoverWorker();
      await orchestratorApi.wakeupWorker();
      await orchestratorApi.reloadScheduler();
      await orchestratorApi.getVersion();
      await orchestratorApi.getUptime();
      await orchestratorApi.getAuditLog({ limit: 50, action: "START" });

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/system/health/full");
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/system/overview");
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/system/history?hours=24");
      expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/system/history?hours=48");
      expect(fetchMock.mock.calls[4]?.[0]).toBe("/api/system/metrics/daily?days=14");
      expect(fetchMock.mock.calls[5]?.[0]).toBe("/api/system/metrics/daily?days=30");
      expect(fetchMock.mock.calls[6]?.[0]).toBe("/api/system/checkpoint");
      expect(fetchMock.mock.calls[6]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[7]?.[0]).toBe("/api/system/purge");
      expect(fetchMock.mock.calls[7]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[8]?.[0]).toBe("/api/system/worker/recover");
      expect(fetchMock.mock.calls[8]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[9]?.[0]).toBe("/api/system/worker/wakeup");
      expect(fetchMock.mock.calls[9]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[10]?.[0]).toBe("/api/system/scheduler/reload");
      expect(fetchMock.mock.calls[10]?.[1]?.method).toBe("POST");
      expect(fetchMock.mock.calls[11]?.[0]).toBe("/api/system/version");
      expect(fetchMock.mock.calls[12]?.[0]).toBe("/api/system/uptime");
      expect(fetchMock.mock.calls[13]?.[0]).toBe("/api/system/audit?limit=50&action=START");
    });
  });

  describe("Portfolio", () => {
    it("getPortfolioHealth, getDrift e getPortfolioRunbook (com encodeURIComponent)", async () => {
      fetchMock
        .mockResolvedValueOnce(okJson({ items: [] }))
        .mockResolvedValueOnce(okJson({ items: [] }))
        .mockResolvedValueOnce(new Response("# Runbook", { status: 200 }));

      await orchestratorApi.getPortfolioHealth();
      await orchestratorApi.getDrift();
      const md = await orchestratorApi.getPortfolioRunbook("cat/especial 1");

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/portfolio/health");
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/portfolio/drift");
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/portfolio/runbook/cat%2Fespecial%201");
      expect(md).toBe("# Runbook");
    });
  });

  describe("Beneficiamento", () => {
    it("chama todas as rotas de beneficiamento com query params corretos", async () => {
      for (let i = 0; i < 6; i++) {
        fetchMock.mockResolvedValueOnce(okJson({ ok: true }));
      }

      await orchestratorApi.getBeneficiamentoHealth();
      await orchestratorApi.getBeneficiamentoOverview({ dt_inicio: "2026-01-01", maquina: "M1", turno: undefined });
      await orchestratorApi.getBeneficiamentoDetail({ target_type: "fase", fase: "TINGIMENTO", page: 2, limit: 50 });
      await orchestratorApi.getBeneficiamentoProdutos("MALHA");
      await orchestratorApi.getBeneficiamentoTingimento({ dt_inicio: "2026-01-01", dt_fim: "2026-01-31" });
      await orchestratorApi.refreshBeneficiamento("2026-01");

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/beneficiamento/health");
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/beneficiamento/overview?dt_inicio=2026-01-01&maquina=M1");
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/beneficiamento/detail?target_type=fase&fase=TINGIMENTO&page=2&limit=50");
      expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/beneficiamento/produtos?q=MALHA");
      expect(fetchMock.mock.calls[4]?.[0]).toBe("/api/beneficiamento/tingimento?dt_inicio=2026-01-01&dt_fim=2026-01-31");
      expect(fetchMock.mock.calls[5]?.[0]).toBe("/api/beneficiamento/refresh?period=2026-01");
      expect(fetchMock.mock.calls[5]?.[1]?.method).toBe("POST");
    });
  });

  describe("Promovidas", () => {
    it("getPromovidas, getPromovidaLatest, getPromovidaCardBlob e getPromovidaHistory", async () => {
      const cardBlob = new Blob(["png"], { type: "image/png" });
      fetchMock
        .mockResolvedValueOnce(okJson({ items: [] }))
        .mockResolvedValueOnce(okJson({ slug: "vendas/dia" }))
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          blob: vi.fn().mockResolvedValue(cardBlob),
        } as unknown as Response)
        .mockResolvedValueOnce(okJson({ slug: "vendas/dia", items: [] }))
        .mockResolvedValueOnce(okJson({ slug: "vendas/dia", items: [] }));

      await orchestratorApi.getPromovidas();
      await orchestratorApi.getPromovidaLatest("vendas/dia");
      const blob = await orchestratorApi.getPromovidaCardBlob("vendas/dia", "card 1.png");
      await orchestratorApi.getPromovidaHistory("vendas/dia");
      await orchestratorApi.getPromovidaHistory("vendas/dia", 5);

      expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/promovidas/");
      expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/promovidas/vendas%2Fdia/latest");
      expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/promovidas/vendas%2Fdia/cards/card%201.png");
      expect(blob).toBe(cardBlob);
      expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/promovidas/vendas%2Fdia/history?limit=20");
      expect(fetchMock.mock.calls[4]?.[0]).toBe("/api/promovidas/vendas%2Fdia/history?limit=5");
    });

    it("propaga ApiError quando o backend responde com erro", async () => {
      fetchMock.mockResolvedValueOnce(new Response("Nao encontrado", { status: 404 }));
      await expect(orchestratorApi.getPromovidaLatest("inexistente")).rejects.toBeInstanceOf(ApiError);
    });
  });
});
