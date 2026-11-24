import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  orchestratorApi,
  type Automation,
  type PromovidaResumo,
  type PromovidaSnapshot,
} from "../api/orchestrator";
import { ToastProvider } from "../components/ui";
import { exportRowsAsCsv, exportRowsAsExcel } from "../components/pcp/PcpExportUtils";
import { TableDensityProvider } from "../context/TableDensityContext";
import { PcpPage } from "../pages/PcpPage";

const ITEMS: PromovidaResumo[] = [
  {
    slug: "obs-paradas-fase",
    codigo: "OBP-04",
    nome: "OBs Paradas Fase",
    titulo: "OBs Paradas por Fase",
    origem: "automacao",
    setor: "Beneficiamento & Fases",
    modo: "producao",
    destinos: ["whatsapp", "dashboard"],
    has_snapshot: true,
    generated_at: "2026-11-22T00:00:00Z",
    age_minutes: 10,
    total_rows: 2,
    excecoes_count: 2,
    cards_count: 1,
    kpis: { count: 2 },
  },
  {
    slug: "rama-risco-atraso",
    codigo: "CP-01",
    nome: "Risco Atraso Ramas",
    titulo: "Risco de Atraso nas Ramas",
    origem: "promovida",
    setor: "Acabamento & Ramas",
    modo: "sombra",
    destinos: ["whatsapp", "dashboard"],
    has_snapshot: true,
    generated_at: "2026-11-22T00:00:00Z",
    age_minutes: 12,
    total_rows: 2,
    excecoes_count: 1,
    kpis: { count: 2, "sum:KG": 120.5 },
  },
  {
    slug: "rama-pulmao-autonomia",
    codigo: "CP-02",
    nome: "Pulmão Ramas",
    titulo: "Pulmão e Autonomia das Ramas",
    origem: "promovida",
    setor: "Acabamento & Ramas",
    modo: "sombra",
    destinos: ["whatsapp", "dashboard"],
    has_snapshot: false,
    generated_at: null,
    age_minutes: null,
    total_rows: 0,
    excecoes_count: 0,
    kpis: {},
  },
];

const SNAPSHOT: PromovidaSnapshot = {
  slug: "obs-paradas-fase",
  codigo: "OBP-04",
  nome: "OBs Paradas Fase",
  titulo: "OBs Paradas por Fase",
  origem: "automacao",
  modo: "producao",
  generated_at: "2026-11-22T00:00:00Z",
  age_minutes: 10,
  total_rows: 2,
  excecoes_count: 2,
  kpis: { count: 2, "sum:KG": 120.5 },
  columns: ["OB", "CLIENTE", "KG"],
  rows: [
    { OB: "1001", CLIENTE: "MALHAS SUL", KG: 80 },
    { OB: "1002", CLIENTE: "TEXTIL NORTE", KG: 40.5 },
  ],
  cards: [
    {
      key: "FELPAGEM",
      title: "Felpagem",
      filename: "FELPAGEM.png",
      caption: "Felpagem - 2 OBs paradas",
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <TableDensityProvider>
          <PcpPage />
        </TableDensityProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("PcpPage — consultas promovidas snapshot-first", () => {
  afterEach(() => {
    localStorage.clear();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("lista o catálogo, carrega o snapshot da primeira consulta com dados e filtra linhas", async () => {
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({ items: ITEMS });
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue(SNAPSHOT);
    vi.spyOn(orchestratorApi, "listAllAutomations").mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("Risco Atraso Ramas")).toBeInTheDocument();
    expect(screen.getByText("Pulmão Ramas")).toBeInTheDocument();
    expect(await screen.findByText("MALHAS SUL")).toBeInTheDocument();
    expect(screen.getByText("TEXTIL NORTE")).toBeInTheDocument();
    expect(screen.getByText("Linhas no snapshot")).toBeInTheDocument();
    expect(screen.queryByText("Total de linhas")).not.toBeInTheDocument();

    const search = screen.getByLabelText("Filtrar linhas do snapshot");
    fireEvent.change(search, { target: { value: "NORTE" } });

    expect(screen.queryByText("MALHAS SUL")).not.toBeInTheDocument();
    expect(screen.getByText("TEXTIL NORTE")).toBeInTheDocument();
  });

  it("exibe estado vazio quando a consulta selecionada ainda não possui snapshot", async () => {
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({ items: ITEMS });
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue(SNAPSHOT);
    vi.spyOn(orchestratorApi, "listAllAutomations").mockResolvedValue([]);

    renderPage();

    const emptyItem = await screen.findByText("Pulmão Ramas");
    fireEvent.click(emptyItem);

    expect(await screen.findByText("Nenhum snapshot gerado ainda")).toBeInTheDocument();
  });

  it("filtra catálogo por origem, exibe cards PNG e histórico", async () => {
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({ items: ITEMS });
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue(SNAPSHOT);
    vi.spyOn(orchestratorApi, "listAllAutomations").mockResolvedValue([]);
    vi.spyOn(orchestratorApi, "getPromovidaCardBlob").mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    vi.spyOn(orchestratorApi, "getPromovidaHistory").mockResolvedValue({
      slug: "obs-paradas-fase",
      items: [
        { slug: "obs-paradas-fase", generated_at: "22/11/2026 14:00:00", modo: "producao", total_rows: 2, excecoes_count: 2, kpis: {} },
      ],
    });

    const origCreateDesc = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const origRevokeDesc = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(() => "blob:mock-card"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });

    try {
      renderPage();

      expect(await screen.findByText("OBs Paradas Fase")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Promovidas \(2\)/ }));
      expect(screen.queryByText("OBs Paradas Fase")).not.toBeInTheDocument();
      expect(screen.getByText("Risco Atraso Ramas")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Todas \(3\)/ }));
      fireEvent.click(screen.getByRole("tab", { name: /Cards Visuais PNG/ }));
      expect(await screen.findByText("Felpagem")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("tab", { name: /Histórico/ }));
      expect(await screen.findByText("22/11/2026 14:00:00")).toBeInTheDocument();
    } finally {
      if (origCreateDesc) Object.defineProperty(URL, "createObjectURL", origCreateDesc);
      else delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
      if (origRevokeDesc) Object.defineProperty(URL, "revokeObjectURL", origRevokeDesc);
      else delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
    }
  });

  it("permite fixar favorito, recolher catálogo, filtrar por coluna e exportar Excel", async () => {
    localStorage.clear();
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
      items: [
        {
          slug: "obs-paradas-fase",
          origem: "automacao",
          codigo: "OBP-04",
          nome: "OBs Paradas Fase",
          titulo: "OBs Paradas na Fase",
          setor: "Beneficiamento",
          modo: "producao",
          destinos: [],
          has_snapshot: true,
          generated_at: "22/11/2026 14:00:00",
          age_minutes: 5,
          total_rows: 2,
          excecoes_count: 1,
          cards_count: 0,
          kpis: {},
        },
        {
          slug: "rama-risco-atraso",
          origem: "promovida",
          codigo: "CP-01",
          nome: "Risco Atraso Ramas",
          titulo: "Ramas com risco de atraso",
          setor: "Acabamento",
          modo: "producao",
          destinos: [],
          has_snapshot: false,
          generated_at: null,
          age_minutes: null,
          total_rows: 0,
          excecoes_count: 0,
          cards_count: 0,
          kpis: {},
        },
      ],
    });
    vi.spyOn(orchestratorApi, "listAllAutomations").mockResolvedValue([]);
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue({
      slug: "obs-paradas-fase",
      nome: "OBs Paradas Fase",
      titulo: "OBs Paradas na Fase",
      modo: "producao",
      generated_at: "22/11/2026 14:00:00",
      age_minutes: 5,
      total_rows: 2,
      excecoes_count: 1,
      kpis: {},
      columns: ["ob", "fase"],
      rows: [
        { ob: "OB-1", fase: "Tingimento" },
        { ob: "OB-2", fase: "Felpagem" },
      ],
      cards: [],
    });

    const origCreateDesc = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const origRevokeDesc = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const createSpy = vi.fn(() => "blob:export-btn");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, writable: true, value: createSpy });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: vi.fn() });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    try {
      renderPage();
      expect(await screen.findByText("OB-1")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Exportar Excel" }));
      expect(createSpy).toHaveBeenCalledTimes(1);
      expect(clickSpy).toHaveBeenCalledTimes(1);
    } finally {
      clickSpy.mockRestore();
      if (origCreateDesc) Object.defineProperty(URL, "createObjectURL", origCreateDesc);
      else delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
      if (origRevokeDesc) Object.defineProperty(URL, "revokeObjectURL", origRevokeDesc);
      else delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
    }

    // Fixar favorito persiste em localStorage
    const pinBtn = screen.getByRole("button", { name: /Fixar Risco Atraso Ramas nos favoritos/i });
    fireEvent.click(pinBtn);
    expect(JSON.parse(localStorage.getItem("pcp_pinned_slugs") ?? "[]")).toContain("rama-risco-atraso");

    // Filtrar por coluna
    fireEvent.change(screen.getByLabelText("Filtrar por coluna"), { target: { value: "fase" } });
    fireEvent.change(screen.getByLabelText("Valor da coluna"), { target: { value: "Felpagem" } });
    expect(screen.getByText("OB-2")).toBeInTheDocument();
    expect(screen.queryByText("OB-1")).not.toBeInTheDocument();

    // Recolher e mostrar catálogo
    fireEvent.click(screen.getByRole("button", { name: "Recolher catálogo" }));
    expect(screen.queryByText("Catálogo ativo")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar catálogo" }));
    expect(screen.getByText("Catálogo ativo")).toBeInTheDocument();
  });

  it("exibe aba Sobre / Regra de Negócio com metadados e automação vinculada", async () => {
    localStorage.clear();
    const linkedAuto: Automation = {
      id: 7,
      name: "OBs Paradas Fase",
      description: "Monitora OBs paradas acima do limite por fase",
      script_path: "Automacoes/OBsParadas/run.ps1",
      schedule: "0 8,14 * * 1-5",
      max_runtime_minutes: 15,
      max_retries: 1,
      cooldown_minutes: 10,
      queue_group: "pcp",
      sla_minutes: 30,
      enabled: true,
      test_mode: true,
      notification_channels: "whatsapp",
      created_at: "2026-01-01 08:00:00",
      updated_at: null,
      next_run: "23/11/2026 08:00:00",
      last_status: "SUCCESS",
      last_execution_id: "exec-1",
      last_execution_started_at: null,
      last_execution_finished_at: null,
      last_execution_duration_seconds: null,
      last_failure_reason: null,
      last_recovery_action: null,
      last_requested_by: null,
      schedule_type: "cron",
      schedule_summary: "Seg–Sex às 08:00 e 14:00",
      next_runs_preview: [],
      active_execution_count: 0,
      success_24h: 2,
      failures_24h: 0,
      timeouts_24h: 0,
      error_24h: 0,
      avg_duration_24h_seconds: null,
      pending_count: 0,
      operational_state: "healthy",
      validated: true,
      backup_path: null,
      audit_id: null,
    };

    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({ items: ITEMS });
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue(SNAPSHOT);
    vi.spyOn(orchestratorApi, "listAllAutomations").mockResolvedValue([linkedAuto]);

    renderPage();

    expect(await screen.findByText("MALHAS SUL")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Sobre \/ Regra de Negócio/ }));

    expect(screen.getByText("obs-paradas-fase")).toBeInTheDocument();
    expect(screen.getByText("Automação operacional")).toBeInTheDocument();
    expect(screen.getAllByText("Beneficiamento & Fases").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("whatsapp, dashboard")).toBeInTheDocument();
    expect(screen.getByText("Ativa")).toBeInTheDocument();
    expect(screen.getByText("Sandbox (teste)")).toBeInTheDocument();
    expect(screen.getByText("Seg–Sex às 08:00 e 14:00")).toBeInTheDocument();
  });

  it("neutraliza formula injection (incluindo whitespace e XSS) ao exportar CSV e Excel", async () => {
    vi.useFakeTimers();
    const blobs: Blob[] = [];
    const origCreateDesc = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const origRevokeDesc = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const revokeSpy = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn((b: Blob | MediaSource) => {
        if (b instanceof Blob) blobs.push(b);
        return "blob:export";
      }),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeSpy,
    });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    try {
      exportRowsAsCsv("teste", ["DESCRICAO", "VALOR"], [
        { DESCRICAO: "=CMD()", VALOR: -10.5 },
        { DESCRICAO: "+1+1", VALOR: 5 },
        { DESCRICAO: "-1+1", VALOR: 0 },
        { DESCRICAO: " =HYPERLINK()", VALOR: 1 },
        { DESCRICAO: "\t=1", VALOR: 2 },
        { DESCRICAO: "\n=1", VALOR: 3 },
        { DESCRICAO: 'a;b"c', VALOR: 4 },
      ]);
      exportRowsAsExcel("teste", ["DESCRICAO", "VALOR"], [
        { DESCRICAO: "@SUM(A1)", VALOR: -2 },
        { DESCRICAO: "\n=1+1 & <script>alert(1)</script>", VALOR: 1 },
      ]);

      vi.runAllTimers();
      expect(revokeSpy).toHaveBeenCalledTimes(2);
      expect(blobs).toHaveLength(2);

      const csvText = await blobs[0]!.text();
      expect(csvText).toContain("'=CMD()");
      expect(csvText).toContain("'+1+1");
      expect(csvText).toContain("'-1+1");
      expect(csvText).toContain("' =HYPERLINK()");
      expect(csvText).toContain("'\t=1");
      expect(csvText).toContain("'\n=1");
      expect(csvText).toContain('"a;b""c"');
      expect(csvText).toContain(";-10.5");

      const xlsText = await blobs[1]!.text();
      expect(xlsText).toContain("'@SUM(A1)</td>");
      expect(xlsText).toContain("'\n=1+1 &amp; &lt;script&gt;alert(1)&lt;/script&gt;</td>");
      expect(xlsText).toContain("<td>-2</td>");
    } finally {
      clickSpy.mockRestore();
      if (origCreateDesc) Object.defineProperty(URL, "createObjectURL", origCreateDesc);
      else delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
      if (origRevokeDesc) Object.defineProperty(URL, "revokeObjectURL", origRevokeDesc);
      else delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
    }
  });
});
