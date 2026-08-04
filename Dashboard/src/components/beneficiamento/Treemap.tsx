import { useMemo } from "react";
import type { BeneficiamentoTreemapNode } from "../../api/orchestrator";
import { formatNumber } from "../../lib/format";
import styles from "./Treemap.module.css";

interface TreemapProps {
  nodes: BeneficiamentoTreemapNode[];
  height?: number;
  onCellClick?: (cell: { setor: string; fase: string }) => void;
}

interface FaseCell {
  fase: string;
  kg_total: number;
  maquinas: { maquina: string; kg_total: number }[];
}

interface SetorGroup {
  setor: string;
  kg_total: number;
  fases: FaseCell[];
}

const TONE_ROTATION = [
  "var(--cyan)",
  "var(--blue)",
  "var(--green)",
  "var(--amber)",
  "var(--red)",
  "var(--grey)",
];

function groupBySetor(nodes: BeneficiamentoTreemapNode[]): SetorGroup[] {
  const setores = new Map<string, Map<string, FaseCell>>();
  for (const node of nodes) {
    if (!setores.has(node.setor)) setores.set(node.setor, new Map());
    const fases = setores.get(node.setor)!;
    if (!fases.has(node.fase)) fases.set(node.fase, { fase: node.fase, kg_total: 0, maquinas: [] });
    const cell = fases.get(node.fase)!;
    cell.kg_total += node.kg_total;
    cell.maquinas.push({ maquina: node.maquina, kg_total: node.kg_total });
  }
  return Array.from(setores.entries())
    .map(([setor, fases]) => {
      const fasesArr = Array.from(fases.values())
        .map((f) => ({ ...f, maquinas: f.maquinas.sort((a, b) => b.kg_total - a.kg_total) }))
        .sort((a, b) => b.kg_total - a.kg_total);
      return { setor, kg_total: fasesArr.reduce((sum, f) => sum + f.kg_total, 0), fases: fasesArr };
    })
    .sort((a, b) => b.kg_total - a.kg_total);
}

/** Treemap slice-and-dice (Setor -> Fase, detalhe de Máquina no tooltip). SVG próprio, sem dependência externa. */
export function Treemap({ nodes, height = 320, onCellClick }: TreemapProps) {
  const groups = useMemo(() => groupBySetor(nodes), [nodes]);
  const total = groups.reduce((sum, g) => sum + g.kg_total, 0);

  if (groups.length === 0 || total <= 0) {
    return <div className={styles.empty}>Sem dados para o recorte filtrado.</div>;
  }

  const width = 1000;
  let xOffset = 0;
  const columns = groups.map((group) => {
    const colWidth = (group.kg_total / total) * width;
    const col = { group, x: xOffset, width: colWidth };
    xOffset += colWidth;
    return col;
  });

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={styles.svg} preserveAspectRatio="none" role="img">
      {columns.map(({ group, x, width: colWidth }, gi) => {
        let yOffset = 0;
        return (
          <g key={group.setor}>
            {group.fases.map((fase) => {
              const cellHeight = (fase.kg_total / group.kg_total) * height;
              const rect = { x, y: yOffset, width: colWidth, height: cellHeight };
              yOffset += cellHeight;
              const topMaquinas = fase.maquinas
                .slice(0, 3)
                .map((m) => `${m.maquina}: ${formatNumber(m.kg_total)} kg`)
                .join(" · ");
              return (
                <g
                  key={fase.fase}
                  onClick={() => onCellClick?.({ setor: group.setor, fase: fase.fase })}
                  className={styles.cell}
                >
                  <title>{`${group.setor} / ${fase.fase} — ${formatNumber(fase.kg_total)} kg\n${topMaquinas}`}</title>
                  <rect
                    x={rect.x}
                    y={rect.y}
                    width={Math.max(rect.width - 1, 0)}
                    height={Math.max(rect.height - 1, 0)}
                    fill={TONE_ROTATION[gi % TONE_ROTATION.length]}
                    fillOpacity={0.25 + 0.5 * (fase.kg_total / group.kg_total)}
                    stroke="var(--border)"
                    strokeWidth={1}
                  />
                  {rect.width > 60 && rect.height > 16 && (
                    <text x={rect.x + 6} y={rect.y + 14} className={styles.label}>
                      {fase.fase}
                    </text>
                  )}
                </g>
              );
            })}
            {colWidth > 60 && (
              <text x={x + 6} y={height - 6} className={styles.setorLabel}>
                {group.setor}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
