/** Fonte única dos breakpoints — TODO `@media (max-width: Npx)` do app usa um
 *  destes 4 valores (nenhum literal solto). O CSS repete o número (decisão da
 *  Onda 4-2: `postcss-custom-media` traria derivação real, mas é tooling novo
 *  de build tarde nesta rodada — risco maior que o ganho de não repetir 3
 *  dígitos em ~6 arquivos). `FilterBar.module.css` usa `min-width: 721px`
 *  (não 720) DE PROPÓSITO — evita a zona morta de 1px entre um breakpoint
 *  `max-width` e um `min-width` combinados; não "arredondar" para `compact`. */
export const BREAKPOINTS = {
  xnarrow: 400,
  narrow: 560,
  compact: 720,
  wide: 900,
} as const;

export const mediaMaxWidth = (bp: keyof typeof BREAKPOINTS) =>
  `(max-width: ${BREAKPOINTS[bp]}px)`;
