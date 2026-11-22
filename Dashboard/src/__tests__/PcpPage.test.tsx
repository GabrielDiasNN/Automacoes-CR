import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  orchestratorApi,
  type PromovidaResumo,
  type PromovidaSnapshot,
} from "../api/orchestrator";
import { TableDensityProvider } from "../context/TableDensityContext";
import { PcpPage } from "../pages/PcpPage";

const ITEMS: PromovidaResumo[] = [
  {
    slug: "rama-risco-atraso",
    nome: "Risco Atraso Ramas",
    titulo: "Risco de Atraso nas Ramas",
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
    nome: "Pulmão Ramas",
    titulo: "Pulmão e Autonomia das Ramas",
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
  slug: "rama-risco-atraso",
  nome: "Risco Atraso Ramas",
  titulo: "Risco de Atraso nas Ramas",
  modo: "sombra",
  generated_at: "2026-11-22T00:00:00Z",
  age_minutes: 12,
  total_rows: 2,
  excecoes_count: 1,
  kpis: { count: 2, "sum:KG": 120.5 },
  columns: ["OB", "CLIENTE", "KG"],
  rows: [
    { OB: "1001", CLIENTE: "MALHAS SUL", KG: 80 },
    { OB: "1002", CLIENTE: "TEXTIL NORTE", KG: 40.5 },
  ],
};

function renderPage() {
  return render(
    <TableDensityProvider>
      <PcpPage />
    </TableDensityProvider>,
  );
}

describe("PcpPage — consultas promovidas snapshot-first", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lista o catálogo, carrega o snapshot da primeira consulta com dados e filtra linhas", async () => {
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({ items: ITEMS });
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue(SNAPSHOT);

    renderPage();

    expect(await screen.findByText("Risco Atraso Ramas")).toBeInTheDocument();
    expect(screen.getByText("Pulmão Ramas")).toBeInTheDocument();
    expect(await screen.findByText("MALHAS SUL")).toBeInTheDocument();
    expect(screen.getByText("TEXTIL NORTE")).toBeInTheDocument();

    const search = screen.getByLabelText("Filtrar linhas do snapshot");
    fireEvent.change(search, { target: { value: "NORTE" } });

    expect(screen.queryByText("MALHAS SUL")).not.toBeInTheDocument();
    expect(screen.getByText("TEXTIL NORTE")).toBeInTheDocument();
  });

  it("exibe estado vazio quando a consulta selecionada ainda não possui snapshot", async () => {
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({ items: ITEMS });
    vi.spyOn(orchestratorApi, "getPromovidaLatest").mockResolvedValue(SNAPSHOT);

    renderPage();

    const emptyItem = await screen.findByText("Pulmão Ramas");
    fireEvent.click(emptyItem);

    expect(await screen.findByText("Nenhum snapshot gerado ainda")).toBeInTheDocument();
  });
});
