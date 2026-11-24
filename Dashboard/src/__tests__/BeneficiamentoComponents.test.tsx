import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  orchestratorApi,
  type BeneficiamentoDetail,
  type BeneficiamentoFilterOptions,
} from "../api/orchestrator";
import { DetailDrawer } from "../components/beneficiamento/DetailDrawer";
import {
  DEFAULT_BENEFICIAMENTO_FILTERS,
  FilterBar,
} from "../components/beneficiamento/FilterBar";
import { ProductAutocomplete } from "../components/beneficiamento/ProductAutocomplete";
import { TableDensityProvider } from "../context/TableDensityContext";

const FILTER_OPTIONS: BeneficiamentoFilterOptions = {
  maquinas: ["RAM-01", "TIN-02"],
  fases: ["TINGIMENTO", "RAMA"],
  turnos: ["1º Turno", "2º Turno"],
  setores: ["TINGIMENTO"],
  grupos_fase: ["ACABAMENTO"],
  tipos_maquina: ["RAMA"],
};

const DETAIL_PAYLOAD: BeneficiamentoDetail = {
  generated_at: "2026-11-22T18:00:00Z",
  filters: { effective: {} },
  target: { type: "maquina_fase", label: "RAM-01" },
  summary: {
    target_type: "maquina_fase",
    ob_distintas: 12,
    fases_concluidas: 24,
    kg_total: 1500,
    mt_total: 4200,
    eficiencia_tempo_pct: 92.5,
    reprocesso_kg_pct: 3.2,
    produtividade_kg_h: 210,
    turnos: ["1º Turno"],
  },
  records: [
    {
      ob: "OB-9001",
      seq: 1,
      data_fim: "2026-11-22T17:30:00Z",
      codigo_fase: 10,
      fase: "RAMA",
      grupo_fase: "ACABAMENTO",
      setor: "TINGIMENTO",
      tipo_maquina: "RAMA",
      maquina: "RAM-01",
      turno: "1º Turno",
      alternativo: "ALT-1",
      reduz: "RED-1",
      produto: "MALHA ALGODAO",
      artigo: "ART-1",
      cor: "AZUL",
      kg: 320,
      mt: 900,
      pecas_origem: 10,
      kg_origem_real: 325,
      pecas_destino: 10,
      kg_destino_real: 320,
      min_real: 60,
      min_prev: 55,
      desvio_min: 5,
      reprocesso: 0,
    },
  ],
  trace: [],
  pagination: { page: 1, limit: 20, total: 1, pages: 1 },
  raw_records: [],
};

describe("Beneficiamento — FilterBar, DetailDrawer e ProductAutocomplete", () => {
  let originalMatchMedia: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalMatchMedia = Object.getOwnPropertyDescriptor(window, "matchMedia");
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    if (originalMatchMedia) {
      Object.defineProperty(window, "matchMedia", originalMatchMedia);
    } else {
      delete (window as unknown as { matchMedia?: unknown }).matchMedia;
    }
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("FilterBar dispara busca livre e limpa filtros quando ativo", () => {
    const onChange = vi.fn();
    const onReset = vi.fn();

    const { rerender } = render(
      <FilterBar
        filters={DEFAULT_BENEFICIAMENTO_FILTERS}
        options={FILTER_OPTIONS}
        onChange={onChange}
        onReset={onReset}
      />,
    );

    expect(screen.queryByRole("button", { name: /Limpar/i })).not.toBeInTheDocument();

    const searchInput = screen.getByLabelText("Busca livre");
    fireEvent.change(searchInput, { target: { value: "OB-9001" } });
    expect(onChange).toHaveBeenCalledWith({ q: "OB-9001" });

    rerender(
      <FilterBar
        filters={{ ...DEFAULT_BENEFICIAMENTO_FILTERS, q: "OB-9001" }}
        options={FILTER_OPTIONS}
        onChange={onChange}
        onReset={onReset}
      />,
    );

    const clearBtn = screen.getByRole("button", { name: /Limpar/i });
    fireEvent.click(clearBtn);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("DetailDrawer abre, exibe detalhes retornados pela API e fecha ao clicar no botão", async () => {
    const detailSpy = vi
      .spyOn(orchestratorApi, "getBeneficiamentoDetail")
      .mockResolvedValue(DETAIL_PAYLOAD);
    const onClose = vi.fn();

    const { rerender } = render(
      <TableDensityProvider>
        <DetailDrawer request={null} contextFilters={{}} onClose={onClose} />
      </TableDensityProvider>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    rerender(
      <TableDensityProvider>
        <DetailDrawer
          request={{ targetType: "maquina_fase", label: "RAM-01", maquina: "RAM-01" }}
          contextFilters={{ dt_inicio: "2026-11-01", dt_fim: "2026-11-22" }}
          onClose={onClose}
        />
      </TableDensityProvider>,
    );

    expect(screen.getByRole("dialog", { name: "RAM-01" })).toBeInTheDocument();
    await waitFor(() => expect(detailSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("OB-9001")).toBeInTheDocument();
    expect(screen.getByText("MALHA ALGODAO")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Fechar painel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ProductAutocomplete busca após digitação e dispara onSelect ao escolher opção", async () => {
    vi.useFakeTimers();
    const produtosSpy = vi
      .spyOn(orchestratorApi, "getBeneficiamentoProdutos")
      .mockResolvedValue({
        items: [
          { codigo: "P100", produto: "MALHA PIQUET" },
          { codigo: "P200", produto: "MALHA RIBANA" },
        ],
      });
    const onSelect = vi.fn();
    const onClear = vi.fn();

    render(<ProductAutocomplete value="" onSelect={onSelect} onClear={onClear} />);

    const input = screen.getByLabelText("Produto");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "MALHA" } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });

    expect(produtosSpy).toHaveBeenCalledWith("MALHA", expect.any(AbortSignal));

    const optionBtn = screen.getByRole("button", { name: /P100.*MALHA PIQUET/i });
    fireEvent.click(optionBtn);

    expect(onSelect).toHaveBeenCalledWith("P100", "P100 — MALHA PIQUET");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
