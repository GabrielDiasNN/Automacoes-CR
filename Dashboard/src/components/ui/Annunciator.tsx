import type { ReactNode } from "react";
import { toneVar, type Tone } from "../../lib/status";
import { Lamp } from "./Lamp";
import styles from "./Annunciator.module.css";

interface AnnunciatorProps {
  legend: string;
  value?: ReactNode;
  tone: Tone;
  /** aceso = condição presente; apagado = repouso */
  active?: boolean;
  /** pisca quando aceso (alarme) */
  blink?: boolean;
  /** Palavra do estado (ex.: "atenção", "incidente") — antes a severidade era
   *  comunicada só pela cor da lâmpada e pela piscada; renderizada quando
   *  `active`, ao lado da legenda. */
  statusLabel?: string;
}

/** Tile de anunciador (estilo painel de planta): acende/pisca em alarme.
 *  Linguagem de alerta recorrente — codifica severidade real. */
export function Annunciator({ legend, value, tone, active, blink, statusLabel }: AnnunciatorProps) {
  const color = toneVar[tone];
  return (
    <div
      className={[styles.tile, active ? styles.on : styles.off].filter(Boolean).join(" ")}
      style={active ? ({ "--tile-color": color } as React.CSSProperties) : undefined}
    >
      <Lamp size={9} shape="square" color={active ? color : "var(--track)"} blink={active && blink} />
      <span className={styles.legend}>{legend}</span>
      {active && statusLabel && <span className={styles.status}>{statusLabel}</span>}
      {value != null && <span className={styles.value}>{value}</span>}
    </div>
  );
}

export function AnnunciatorGrid({ children }: { children: ReactNode }) {
  return <div className={styles.grid}>{children}</div>;
}
