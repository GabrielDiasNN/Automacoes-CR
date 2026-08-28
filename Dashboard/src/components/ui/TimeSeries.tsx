import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { toneVar, type Tone } from "../../lib/status";

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

const CSS_TONE: Record<Tone, string> = {
  cyan: "#38C5C9",
  amber: "#E8A317",
  green: "#3FB950",
  red: "#F0524D",
  blue: "#4C8DF6",
  grey: "#7C8A9C",
};

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

    const opts: uPlot.Options = {
      width: el.clientWidth || 600,
      height,
      padding: [8, 12, 0, 0],
      cursor: { y: false, points: { size: 5 } },
      legend: { show: false },
      scales: { x: { time: false } },
      axes: [
        {
          stroke: "#7C8A9C",
          grid: { stroke: "#29333E", width: 1 },
          ticks: { stroke: "#29333E", width: 1 },
          font: "10px 'IBM Plex Mono', monospace",
          values: (_u, vals) => vals.map((i) => xLabels[i] ?? ""),
        },
        {
          stroke: "#7C8A9C",
          grid: { stroke: "#29333E", width: 1 },
          ticks: { stroke: "#29333E", width: 1 },
          font: "10px 'IBM Plex Mono', monospace",
          size: 38,
        },
      ],
      series: [
        {},
        ...lines.map((l) => ({
          label: l.label,
          stroke: CSS_TONE[l.tone] ?? toneVar[l.tone],
          width: 1.75,
          fill: `${CSS_TONE[l.tone]}1f`,
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

  return <div ref={ref} style={{ width: "100%" }} />;
}
