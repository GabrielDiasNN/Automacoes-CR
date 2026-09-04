import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { toneVar, type Tone } from "../../lib/status";
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

type ToneColors = Record<Tone, string>;

/** Espelho JS dos tokens de cor — o canvas do uPlot desenha em <canvas> e não
 *  resolve `var(--x)`, então as cores precisam ser strings concretas. Lidas de
 *  `tokens.css` via getComputedStyle a cada recriação do gráfico (assim a troca
 *  de tema da Onda 4 é pega). Se o `:root` ainda não tiver as vars (ex.: teste
 *  em jsdom sem CSS), cai nos hex de fallback — MESMOS valores dos tokens. */
function readPalette(): { tones: ToneColors; axis: string; grid: string } {
  const FALLBACK: ToneColors = {
    cyan: "#38C5C9",
    amber: "#E8A317",
    green: "#3FB950",
    red: "#F0524D",
    blue: "#4C8DF6",
    grey: "#7C8A9C",
  };
  if (typeof window === "undefined" || !document?.documentElement) {
    return { tones: FALLBACK, axis: FALLBACK.grey, grid: "#29333E" };
  }
  const cs = getComputedStyle(document.documentElement);
  const read = (name: string, fb: string) => cs.getPropertyValue(name).trim() || fb;
  const tones: ToneColors = {
    cyan: read("--cyan", FALLBACK.cyan),
    amber: read("--amber", FALLBACK.amber),
    green: read("--green", FALLBACK.green),
    red: read("--red", FALLBACK.red),
    blue: read("--blue", FALLBACK.blue),
    grey: read("--grey", FALLBACK.grey),
  };
  return { tones, axis: tones.grey, grid: read("--graphite-700", "#29333E") };
}

function toData(xLabels: string[], lines: SeriesLine[]): uPlot.AlignedData {
  return [xLabels.map((_, i) => i), ...lines.map((l) => l.values.map((v) => (v == null ? null : v)))];
}

/** Série temporal de telemetria (uPlot). Eixo X por índice, rótulos mapeados.
 *
 *  Recriar o gráfico (`plot.destroy()` + `new uPlot`) só acontece quando a
 *  ESTRUTURA muda — nº de séries, rótulos/tons, rótulos do eixo X ou altura.
 *  Mudança só de valores usa `plot.setData`, que redesenha sem recriar o canvas.
 *  Sem isso, como `xLabels`/`lines` chegam como arrays novos a cada render, no
 *  Monitor cada mensagem do WebSocket destruía e reconstruía o gráfico inteiro
 *  (achado nº 14 — mesmo princípio de virtualização do LogViewer). */
export function TimeSeries({ xLabels, lines, height = 200 }: TimeSeriesProps) {
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);

  const structureKey = JSON.stringify({ height, x: xLabels, series: lines.map((l) => [l.label, l.tone]) });
  const valuesKey = JSON.stringify(lines.map((l) => l.values));

  // Atualiza só os valores, sem recriar o gráfico.
  useEffect(() => {
    plotRef.current?.setData(toData(xLabels, lines));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valuesKey]);

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
}
