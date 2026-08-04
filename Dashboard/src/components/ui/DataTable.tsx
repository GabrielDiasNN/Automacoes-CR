import type { ReactNode } from "react";
import { useTableDensity } from "../../context/TableDensityContext";
import styles from "./DataTable.module.css";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  width?: number | string;
  hideOnNarrow?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  rowTone?: (row: T) => string | undefined;
}

/** Tabela de dados de telemetria — header fixo, números tabulares. */
export function DataTable<T>({ columns, rows, rowKey, onRowClick, rowTone }: DataTableProps<T>) {
  const { density } = useTableDensity();
  return (
    <div className={styles.scroll}>
      <table className={`${styles.table} ${density === "compact" ? styles.compact : ""}`}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={c.hideOnNarrow ? styles.hideNarrow : undefined}
                style={{ textAlign: c.align ?? "left", width: c.width }}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const tone = rowTone?.(row);
            return (
              <tr
                key={rowKey(row)}
                className={onRowClick ? styles.clickable : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter") onRowClick(row);
                      }
                    : undefined
                }
                style={tone ? { boxShadow: `inset 3px 0 0 ${tone}` } : undefined}
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={c.hideOnNarrow ? styles.hideNarrow : undefined}
                    style={{ textAlign: c.align ?? "left" }}
                  >
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
