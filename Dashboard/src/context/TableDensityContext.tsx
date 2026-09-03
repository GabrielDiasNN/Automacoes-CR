import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type TableDensity = "comfortable" | "compact";

const STORAGE_KEY = "orchestrator_table_density";

interface TableDensityContextValue {
  density: TableDensity;
  toggleDensity: () => void;
}

const TableDensityContext = createContext<TableDensityContextValue | null>(null);

export function TableDensityProvider({ children }: { children: ReactNode }) {
  const [density, setDensity] = useState<TableDensity>(
    () => (localStorage.getItem(STORAGE_KEY) as TableDensity | null) ?? "comfortable",
  );

  const toggleDensity = useCallback(() => {
    setDensity((prev) => {
      const next = prev === "comfortable" ? "compact" : "comfortable";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  // Sem useMemo, `value` era um objeto novo a cada render do provider —
  // qualquer consumidor de useTableDensity (a topbar, todo DataTable via
  // useContext) re-renderizava mesmo quando density não mudava (achado
  // nº 30, Onda 5).
  const value = useMemo(() => ({ density, toggleDensity }), [density, toggleDensity]);

  return <TableDensityContext.Provider value={value}>{children}</TableDensityContext.Provider>;
}

export function useTableDensity() {
  const ctx = useContext(TableDensityContext);
  if (!ctx) throw new Error("useTableDensity deve ser usado dentro de TableDensityProvider");
  return ctx;
}
