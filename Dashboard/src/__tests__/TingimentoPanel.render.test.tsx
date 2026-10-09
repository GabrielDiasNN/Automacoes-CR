import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TingimentoPanel } from "../components/beneficiamento/TingimentoPanel";
import { orchestratorApi, type BeneficiamentoTingimento } from "../api/orchestrator";
import { TableDensityProvider } from "../context/TableDensityContext";

// `TimeSeries` importa uPlot, que exige `matchMedia` no load do módulo. Este
// teste não desenha gráfico (série diária vazia), então o uPlot é substituído.
vi.mock("uplot", () => ({ default: vi.fn() }));

const maquina = (over: Record<string, unknown>) => ({
  maquina: "M1",
  fases: 6,
  kg_total: 500,
  eficiencia_tempo_pct: 75,
  setup_medio_min: 28,
  reprocesso_kg_pct: 3.1,
  amostra_insuficiente: false,
  ...over,
});

const cor = (over: Record<string, unknown>) => ({
  cor: "Azul",
  ob_distintas: 2,
  fases: 4,
  kg_total: 300,
  reprocesso_kg_pct: 2.5,
  amostra_insuficiente: false,
  ...over,
});

const payload = {
  generated_at: "2026-10-08 10:00:00",
  filters: { effective: { dt_inicio: null, dt_fim: null } },
  health: { status: "ok", max_data_fim: null, records: 12 },
  resumo: {
    ob_distintas: 3,
    fases: 12,
    kg_total: 1000,
    mt_total: 900,
    eficiencia_tempo_pct: 80,
    reprocesso_kg_pct: 4.2,
    fases_reprocessadas: 1,
    setup_medio_min: 30,
    desvio_medio_min: 5,
    produtividade_kg_h: 20,
  },
  series: { diaria: [] },
  rankings: {
    por_maquina: [
      maquina({ maquina: "M1", fases: 6, reprocesso_kg_pct: 9.5, amostra_insuficiente: true }),
      maquina({ maquina: "M2", fases: 9 }),
    ],
    por_cor: [cor({ cor: "Azul", fases: 2, amostra_insuficiente: true })],
    por_turno: [],
  },
} as unknown as BeneficiamentoTingimento;

describe("TingimentoPanel — sinal de amostra baixa na coluna Reproc. %", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra um ícone de aviso com rótulo acessível só nas linhas de amostra baixa", async () => {
    vi.spyOn(orchestratorApi, "getBeneficiamentoTingimento").mockResolvedValue(payload);

    render(
      <TableDensityProvider>
        <TingimentoPanel />
      </TableDensityProvider>,
    );

    // Uma na tabela por máquina (M1) e uma na tabela por cor (Azul).
    const avisos = await screen.findAllByRole("img", { name: "amostra baixa" });
    expect(avisos).toHaveLength(2);
    // Mantém o título com a contagem de lotes; a linha sem amostra baixa não ganha aviso.
    expect(screen.getAllByTitle("6 lotes (amostra baixa)")).toHaveLength(1);
    expect(screen.getByTitle("9 lotes")).toBeInTheDocument();
    // O símbolo de texto U+26A0 não é mais usado como indicador.
    expect(document.body.textContent ?? "").not.toContain("\u26A0");
  });
});
