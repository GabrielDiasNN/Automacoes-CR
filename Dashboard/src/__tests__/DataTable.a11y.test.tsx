import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DataTable, type Column } from "../components/ui/DataTable";
import { TableDensityProvider } from "../context/TableDensityContext";

interface Row {
  id: string;
  name: string;
}

const ROWS: Row[] = [
  { id: "a", name: "Alfa" },
  { id: "b", name: "Bravo" },
];
const ROW_KEY = (r: Row) => r.id;
const wrap = (c: React.ReactNode) => <TableDensityProvider>{c}</TableDensityProvider>;

function renderTable(onRowClick: (row: Row) => void, extraColumn?: Column<Row>) {
  const columns: Column<Row>[] = [{ key: "name", header: "Nome", render: (r) => r.name }];
  if (extraColumn) columns.push(extraColumn);
  return render(
    wrap(
      <DataTable
        columns={columns}
        rows={ROWS}
        rowKey={ROW_KEY}
        onRowClick={onRowClick}
        rowLabel={(r) => `Abrir detalhe de ${r.name}`}
      />,
    ),
  );
}

describe("DataTable — semântica de linha clicável (achado nº 3, revisão 04/09/2026)", () => {
  it("a linha não se anuncia como role=button — mantém role=row implícito da <tr>", () => {
    renderTable(vi.fn());

    // getByRole("row") só resolve se a <tr> ainda tiver o role implícito de
    // linha de tabela — se role="button" tivesse sobrescrito, isto falharia
    // e nenhum elemento seria encontrado com role="button" pai de <td>.
    const rows = screen.getAllByRole("row");
    // 1 linha de cabeçalho + 2 linhas de dados
    expect(rows).toHaveLength(3);

    expect(screen.queryByRole("button", { name: /abrir detalhe/i })).not.toBeInTheDocument();
  });

  it("a linha clicável tem aria-label descritivo (fallback quando rowLabel não é passado)", () => {
    const columns: Column<Row>[] = [{ key: "name", header: "Nome", render: (r) => r.name }];
    render(
      wrap(<DataTable columns={columns} rows={ROWS} rowKey={ROW_KEY} onRowClick={vi.fn()} />),
    );

    const row = screen.getByRole("row", { name: "Abrir detalhes da linha a" });
    expect(row).toBeInTheDocument();
  });

  it("usa o rowLabel do consumidor quando fornecido", () => {
    renderTable(vi.fn());
    expect(screen.getByRole("row", { name: "Abrir detalhe de Alfa" })).toBeInTheDocument();
  });

  it("Enter na linha dispara onRowClick", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    renderTable(onRowClick);

    const row = screen.getByRole("row", { name: "Abrir detalhe de Alfa" });
    row.focus();
    await user.keyboard("{Enter}");

    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
  });

  it("Space na linha dispara onRowClick", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    renderTable(onRowClick);

    const row = screen.getByRole("row", { name: "Abrir detalhe de Alfa" });
    row.focus();
    await user.keyboard(" ");

    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
  });

  it("clique em botão dentro da linha NÃO dispara onRowClick", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    const onStop = vi.fn();
    renderTable(onRowClick, {
      key: "acoes",
      header: "Ações",
      render: (r) => (
        <button type="button" onClick={() => onStop(r.id)}>
          Parar
        </button>
      ),
    });

    const [stopButton] = screen.getAllByRole("button", { name: "Parar" });
    if (!stopButton) throw new Error("botão 'Parar' não encontrado na tabela");
    await user.click(stopButton);

    expect(onStop).toHaveBeenCalledWith("a");
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("Enter com foco no botão 'Parar' dentro da linha NÃO dispara onRowClick", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    const onStop = vi.fn();
    renderTable(onRowClick, {
      key: "acoes",
      header: "Ações",
      render: (r) => (
        <button type="button" onClick={() => onStop(r.id)}>
          Parar
        </button>
      ),
    });

    const [stopButton] = screen.getAllByRole("button", { name: "Parar" });
    if (!stopButton) throw new Error("botão 'Parar' não encontrado na tabela");
    stopButton.focus();
    await user.keyboard("{Enter}");

    expect(onRowClick).not.toHaveBeenCalled();
  });
});
