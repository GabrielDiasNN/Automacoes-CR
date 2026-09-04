import { memo, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
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

const INTERACTIVE_SELECTOR = "button, a[href], input, select, textarea, [role='button']";

/** Um controle interativo dentro da linha (ex.: botão "Parar"/"Reenfileirar"
 *  numa coluna de ações) não deve também disparar `onRowClick` — nem no
 *  clique (mouse) nem no Enter (teclado). Antes só o clique era protegido
 *  via `stopPropagation` manual no consumidor (ExecucoesPage); um usuário de
 *  teclado que confirmasse "Parar" com Enter também abria o drawer de
 *  detalhe da linha por baixo, numa ação destrutiva em produção (achado
 *  nº 6, Onda 1). Resolvido na origem — o consumidor não precisa lembrar.
 *
 *  `boundary` (a própria `<tr>`, via `e.currentTarget`) é excluído do match:
 *  a linha clicável agora tem `role="button"` (Onda 4-2, suporte a leitor de
 *  tela), que também casa em `[role='button']` — sem excluir `boundary`, a
 *  própria linha "detectava a si mesma" como controle aninhado e engolia
 *  TODO clique silenciosamente. */
function targetIsInteractive(target: EventTarget, boundary: Element): boolean {
  if (!(target instanceof Element)) return false;
  const hit = target.closest(INTERACTIVE_SELECTOR);
  return hit !== null && hit !== boundary;
}

/** Tabela de dados de telemetria — header fixo, números tabulares. */
function DataTableInner<T>({ columns, rows, rowKey, onRowClick, rowTone }: DataTableProps<T>) {
  const { density } = useTableDensity();
  // tabIndex={0}+role="region": overflow-x precisa ser alcançável por
  // teclado (WCAG 2.1.1) quando a tabela é mais larga que o contêiner — sem
  // isso, um usuário de teclado não conseguia rolar horizontalmente (achado
  // via axe-core, Onda 4-3). aria-label evita cair na regra de "region sem
  // nome". jsx-a11y não reconhece "region" como landmark que justifica
  // tabIndex (só roles de widget) — é o padrão recomendado pelo WAI-ARIA
  // Authoring Practices pra região com scroll, então o disable é
  // intencional, não um escape de preguiça.
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className={styles.scroll} tabIndex={0} role="region" aria-label="tabela com rolagem horizontal">
      <table className={`${styles.table} ${density === "compact" ? styles.compact : ""}`}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
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
            const handleClick = (e: MouseEvent<HTMLTableRowElement>) => {
              if (targetIsInteractive(e.target, e.currentTarget)) return;
              onRowClick?.(row);
            };
            const handleKeyDown = (e: KeyboardEvent<HTMLTableRowElement>) => {
              // Space ativa igual a Enter — mesmo contrato de um <button> real
              // (antes só Enter funcionava; Space rolava a página em vez de
              // ativar a linha).
              if (e.key !== "Enter" && e.key !== " ") return;
              if (targetIsInteractive(e.target, e.currentTarget)) return;
              e.preventDefault();
              onRowClick?.(row);
            };
            return (
              <tr
                key={rowKey(row)}
                className={onRowClick ? styles.clickable : undefined}
                onClick={onRowClick ? handleClick : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? "button" : undefined}
                onKeyDown={onRowClick ? handleKeyDown : undefined}
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

/** `React.memo` — a página de Execuções faz polling a cada 8s e Beneficiamento
 *  re-renderiza a cada tecla na busca; sem memo cada tick reconstruía todas as
 *  linhas. O cast preserva a assinatura genérica que `memo()` apaga — exige que
 *  os consumidores passem `columns`/`rows`/`rowKey`/`onRowClick`/`rowTone`
 *  referencialmente estáveis (useMemo/useCallback), senão o memo é teatro. */
export const DataTable = memo(DataTableInner) as typeof DataTableInner;
