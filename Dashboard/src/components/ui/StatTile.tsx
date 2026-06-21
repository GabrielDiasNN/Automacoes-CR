import type { ReactNode } from "react";
import { toneVar, type Tone } from "../../lib/status";
import styles from "./StatTile.module.css";

interface StatTileProps {
  label: string;
  value: ReactNode;
  tone?: Tone;
  hint?: ReactNode;
  /** leitura grande de instrumento (mono tabular) */
  big?: boolean;
}

/** Mostrador de leitura única — número grande + legenda gravada. */
export function StatTile({ label, value, tone, hint, big = true }: StatTileProps) {
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
}
