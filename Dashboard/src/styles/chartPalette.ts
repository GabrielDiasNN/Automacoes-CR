import { type Tone } from "../lib/status";

export type ToneColors = Record<Tone, string>;

export interface ChartPalette {
  tones: ToneColors;
  axis: string;
  grid: string;
}

/** Espelho JS dos tokens de cor — o canvas do uPlot desenha em <canvas> e não
 *  resolve `var(--x)`, então as cores precisam ser strings concretas. Lidas de
 *  `tokens.css` via getComputedStyle a cada recriação do gráfico (assim a troca
 *  de tema da Onda 4 é pega). Se o `:root` ainda não tiver as vars (ex.: teste
 *  em jsdom sem CSS), cai nos hex de fallback — MESMOS valores dos tokens. */
export function readPalette(): ChartPalette {
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
  // --border (não --graphite-700 direto): mesmo valor no escuro, mas
  // acompanha o tema claro da Onda 4-3 — --graphite-* nunca é redefinido
  // fora do escuro de propósito (não é um conceito que exista no claro).
  return { tones, axis: tones.grey, grid: read("--border", "#29333E") };
}
