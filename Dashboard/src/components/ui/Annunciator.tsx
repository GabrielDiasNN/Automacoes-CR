import type { ReactNode } from "react";
import { toneVar, type Tone } from "../../lib/status";
import styles from "./Annunciator.module.css";

interface AnnunciatorProps {
  legend: string;
  value?: ReactNode;
  tone: Tone;
  /** aceso = condição presente; apagado = repouso */
  active?: boolean;
  /** pisca quando aceso (alarme) */
  blink?: boolean;
  onClick?: () => void;
}

/** Tile de anunciador (estilo painel de planta): acende/pisca em alarme.
 *  Linguagem de alerta recorrente — codifica severidade real. */
export function Annunciator({ legend, value, tone, active, blink, onClick }: AnnunciatorProps) {
  const color = toneVar[tone];
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      className={[styles.tile, active ? styles.on : styles.off, onClick ? styles.clickable : ""]
        .filter(Boolean)
        .join(" ")}
      style={
        active
          ? ({ "--tile-color": color } as React.CSSProperties)
          : undefined
      }
      onClick={onClick}
      {...(onClick ? { type: "button" as const } : {})}
    >
      <span
        className={`${styles.lamp} ${active && blink ? styles.blink : ""}`}
        style={{ background: active ? color : "var(--graphite-700)" }}
      />
      <span className={styles.legend}>{legend}</span>
      {value != null && <span className={styles.value}>{value}</span>}
    </Tag>
  );
}

export function AnnunciatorGrid({ children }: { children: ReactNode }) {
  return <div className={styles.grid}>{children}</div>;
}
