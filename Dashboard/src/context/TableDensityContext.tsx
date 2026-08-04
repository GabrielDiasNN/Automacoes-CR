import { createContext, useContext, useState, type ReactNode } from "react";

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

  const toggleDensity = () => {
    setDensity((prev) => {
      const next = prev === "comfortable" ? "compact" : "comfortable";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  };

  return (
    <TableDensityContext.Provider value={{ density, toggleDensity }}>{children}</TableDensityContext.Provider>
  );
}

export function useTableDensity() {
  const ctx = useContext(TableDensityContext);
  if (!ctx) throw new Error("useTableDensity deve ser usado dentro de TableDensityProvider");
  return ctx;
}
