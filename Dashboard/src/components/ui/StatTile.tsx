import { memo, type ReactNode } from "react";
import { toneVar, type Tone } from "../../lib/status";
import styles from "./StatTile.module.css";

interface StatTileProps {
  label: string;
  value: ReactNode;
  // `| undefined` explicito: os call sites passam `cond ? "amber" : undefined`,
  // idioma que `exactOptionalPropertyTypes` rejeita sem isso.
  tone?: Tone | undefined;
  hint?: ReactNode;
  /** leitura grande de instrumento (mono tabular) */
  big?: boolean;
}

/** Mostrador de leitura única — número grande + legenda gravada.
 *  `memo`: grades de tiles re-renderizam junto com a página (Monitor a cada
 *  frame de log, Beneficiamento a cada tecla). Efetivo só para tiles com
 *  `value`/`hint` primitivos ou memoizados no call site. */
export const StatTile = memo(function StatTile({ label, value, tone, hint, big = true }: StatTileProps) {
  return (
    <div className={styles.tile}>
      <div className={styles.label}>{label}</div>
      <div
        className={big ? styles.valueBig : styles.value}
        style={tone ? { color: toneVar[tone] } : undefined}
      >
        {value}
      </div>
      {hint && <div className={styles.hint}>{hint}</div>}
    </div>
  );
});
