/** Fonte única dos breakpoints. O CSS ainda usa os literais (derivação real
 *  via @custom-media é decisão pendente do orquestrador); estes valores DEVEM
 *  espelhar os @media de *.module.css. */
export const BREAKPOINTS = {
  narrow: 560,
  compact: 720,
  wide: 900,
} as const;

export const mediaMaxWidth = (bp: keyof typeof BREAKPOINTS) =>
  `(max-width: ${BREAKPOINTS[bp]}px)`;
