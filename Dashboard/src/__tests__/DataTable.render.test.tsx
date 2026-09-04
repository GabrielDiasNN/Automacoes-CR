import { useState } from "react";
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataTable, type Column } from "../components/ui/DataTable";
import { TableDensityProvider } from "../context/TableDensityContext";
import { mountWithRerender } from "./helpers/renderCount";

interface Row {
  id: string;
  name: string;
}

// Constantes de módulo = referências estáveis (o que os consumidores precisam
// garantir com useMemo/useCallback para o memo funcionar).
const ROWS: Row[] = [
  { id: "a", name: "Alfa" },
  { id: "b", name: "Bravo" },
];
const ROW_KEY = (r: Row) => r.id;
const wrap = (c: React.ReactNode) => <TableDensityProvider>{c}</TableDensityProvider>;

describe("DataTable — React.memo (contagem de renders)", () => {
  it("é um componente memoizado", () => {
    expect((DataTable as unknown as { $$typeof: symbol }).$$typeof).toBe(Symbol.for("react.memo"));
  });

  it("NÃO re-executa o corpo quando o pai re-renderiza com props estáveis", () => {
    const renderCell = vi.fn((r: Row) => r.name);
    const COLUMNS: Column<Row>[] = [{ key: "name", header: "Nome", render: renderCell }];

    const h = mountWithRerender(
      () => <DataTable columns={COLUMNS} rows={ROWS} rowKey={ROW_KEY} />,
      wrap,
    );

    expect(renderCell).toHaveBeenCalledTimes(2); // 2 linhas, 1 render

    h.rerenderParent();
    h.rerenderParent();

    // memo segurou: as células não voltaram a ser renderizadas.
    expect(renderCell).toHaveBeenCalledTimes(2);
  });

  it("controle: re-renderiza quando `rows` muda de referência a cada render do pai", () => {
    const renderCell = vi.fn((r: Row) => r.name);
    const COLUMNS: Column<Row>[] = [{ key: "name", header: "Nome", render: renderCell }];
    let bump: () => void = () => {};

    function Parent() {
      const [n, setN] = useState(0);
      bump = () => setN((v) => v + 1);
      const rows = [{ id: "a", name: `Alfa ${n}` }]; // novo array a cada render
      return <DataTable columns={COLUMNS} rows={rows} rowKey={ROW_KEY} />;
    }

    render(wrap(<Parent />));
    expect(renderCell).toHaveBeenCalledTimes(1);
    act(() => bump());
    expect(renderCell).toHaveBeenCalledTimes(2);
  });
});
