import { memo, useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { toneVar, type Tone } from "../../lib/status";
import { readPalette } from "../../styles/chartPalette";
import styles from "./TimeSeries.module.css";

export interface SeriesLine {
  label: string;
  values: (number | null)[];
  tone: Tone;
}

interface TimeSeriesProps {
  xLabels: string[];
  lines: SeriesLine[];
  height?: number;
}

function toData(xLabels: string[], lines: SeriesLine[]): uPlot.AlignedData {
  return [xLabels.map((_, i) => i), ...lines.map((l) => l.values.map((v) => (v == null ? null : v)))];
}

/** Assinatura barata da ESTRUTURA do gráfico (altura, nº e rótulos do eixo X,
 *  nº/rótulo/tom de cada série) — substitui o `JSON.stringify` que serializava
 *  TAMBÉM os arrays de valores a cada render (no Monitor: 6x por mensagem de WS
 *  com 3 gráficos montados). Aqui entram só os campos que obrigam a recriar o
 *  `uPlot`; a mudança de valores é tratada separadamente por `setData`. */
function structureSignature(height: number, xLabels: string[], lines: SeriesLine[]): string {
  const parts: string[] = [String(height), String(xLabels.length)];
  for (const label of xLabels) parts.push(label);
  parts.push("|series|");
  for (const line of lines) {
    parts.push(line.label);
    parts.push(line.tone);
  }
  return parts.join(",");
}

/** Série temporal de telemetria (uPlot). Eixo X por índice, rótulos mapeados.
 *
 *  Recriar o gráfico (`plot.destroy()` + `new uPlot`) só acontece quando a
 *  ESTRUTURA muda — nº de séries, rótulos/tons, rótulos do eixo X ou altura.
 *  Mudança só de valores usa `plot.setData`, que redesenha sem recriar o canvas.
 *  Sem isso, como `xLabels`/`lines` chegam como arrays novos a cada render, no
 *  Monitor cada mensagem do WebSocket destruía e reconstruía o gráfico inteiro
 *  (achado nº 14 — mesmo princípio de virtualização do LogViewer).
 *
 *  `memo`: no Monitor cada mensagem de WebSocket re-renderiza a página inteira
 *  (estado `lines` do console) sem relação com os 3 gráficos montados. Exige
 *  `xLabels`/`lines` referencialmente estáveis nos call sites (useMemo). */
export const TimeSeries = memo(function TimeSeries({ xLabels, lines, height = 200 }: TimeSeriesProps) {
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);

  const structureKey = structureSignature(height, xLabels, lines);

  // Atualiza só os valores, sem recriar o gráfico. Depende da REFERÊNCIA de
  // `lines` — os call sites memoizam `lines`, então nova referência = valores
  // realmente novos. Nunca perde um update (a ref muda sempre que o conteúdo
  // muda) e não paga o custo de serializar todos os pontos a cada render.
  useEffect(() => {
    plotRef.current?.setData(toData(xLabels, lines));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines]);

  // Recria o gráfico apenas quando a estrutura muda.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const palette = readPalette();

    const opts: uPlot.Options = {
      width: el.clientWidth || 600,
      height,
      padding: [8, 12, 0, 0],
      cursor: { y: false, points: { size: 5 } },
      legend: { show: false },
      scales: { x: { time: false } },
      axes: [
        {
          stroke: palette.axis,
          grid: { stroke: palette.grid, width: 1 },
          ticks: { stroke: palette.grid, width: 1 },
          font: "10px 'IBM Plex Mono', monospace",
          values: (_u, vals) => vals.map((i) => xLabels[i] ?? ""),
        },
        {
          stroke: palette.axis,
          grid: { stroke: palette.grid, width: 1 },
          ticks: { stroke: palette.grid, width: 1 },
          font: "10px 'IBM Plex Mono', monospace",
          size: 38,
        },
      ],
      series: [
        {},
        ...lines.map((l) => ({
          label: l.label,
          stroke: palette.tones[l.tone],
          width: 1.75,
          fill: `${palette.tones[l.tone]}1f`,
          points: { show: false },
        })),
      ],
    };

    const plot = new uPlot(opts, toData(xLabels, lines), el);
    plotRef.current = plot;

    const ro = new ResizeObserver(() => {
      plot.setSize({ width: el.clientWidth || 600, height });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      plot.destroy();
      plotRef.current = null;
    };
    // `structureKey` é a fonte de verdade da recriação; xLabels/lines/height
    // entram só pelo valor serializado nela.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureKey]);

  // O canvas do uPlot não é exposto pela árvore de acessibilidade e
  // `legend: { show: false }` (acima) remove a legenda visual do próprio
  // gráfico — antes disso os rótulos de `SeriesLine.label` não apareciam em
  // lugar nenhum: um gráfico de 2 linhas coloridas sem indicar qual é qual,
  // nem para quem enxerga nem para leitor de tela. `role="img"` é seguro
  // aqui (sem filhos interativos, diferente de Mimico/Treemap).
  const resumo = `Série temporal: ${lines.map((l) => l.label).join(", ")}`;

  return (
    <div>
      <div ref={ref} role="img" aria-label={resumo} style={{ width: "100%" }} />
      <div className={styles.legend} aria-hidden="true">
        {lines.map((l) => (
          <span key={l.label} className={styles.item}>
            <span className={styles.swatch} style={{ background: toneVar[l.tone] }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
});
