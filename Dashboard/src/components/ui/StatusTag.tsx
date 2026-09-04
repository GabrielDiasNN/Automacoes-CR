import type { ReactNode } from "react";
import { toneGlow, toneTint, toneVar, type Tone } from "../../lib/status";
import { Lamp } from "./Lamp";
import styles from "./StatusTag.module.css";

interface StatusTagProps {
  tone: Tone;
  children: ReactNode;
  dot?: boolean;
  pulse?: boolean;
}

/** Legenda acesa — pílula com tom semântico (cor = significado). */
export function StatusTag({ tone, children, dot, pulse }: StatusTagProps) {
  return (
    <span className={styles.tag} style={{ color: toneVar[tone], background: toneTint[tone] }}>
      {dot && (
        // `pulseGlow` alimenta @keyframes pulse-ring (tokens.css) — sem isso
        // o halo do pulso era sempre âmbar, mesmo num StatusTag vermelho ou
        // verde.
        <Lamp size={7} color={toneVar[tone]} pulse={pulse} pulseGlow={pulse ? toneGlow[tone] : undefined} />
      )}
      {children}
    </span>
  );
}
