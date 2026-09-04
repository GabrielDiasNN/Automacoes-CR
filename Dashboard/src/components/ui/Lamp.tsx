import type { CSSProperties } from "react";
import styles from "./Lamp.module.css";

export interface LampProps {
  /** px — os 4 tamanhos hoje em uso: 7 (StatusTag), 8 (Mimico · fila), 9
   *  (StatusBar/Annunciator/AutomacoesPage), 10 (Mimico · worker). */
  size: 7 | 8 | 9 | 10;
  /** círculo = sinal de status; quadrado = instrumento (Annunciator,
   *  Mimico · fila). Diferença semântica, não acidental — preservada. */
  shape?: "circle" | "square" | undefined;
  /** Cor resolvida pelo chamador (`var(--tone)` ou expressão computada) —
   *  o Lamp não conhece `Tone`. */
  color: string;
  /** `blink-alarm 1s steps(1,end) infinite` — StatusBar (saúde unhealthy) e
   *  Annunciator (alarme ativo). */
  blink?: boolean | undefined;
  /** `pulse-ring 2s var(--ease) infinite` — StatusTag e Mimico · worker
   *  rodando. Use com `pulseGlow` (ver `lib/status.ts toneGlow`) para o halo
   *  acompanhar o tom real em vez do âmbar fixo do fallback do keyframe. */
  pulse?: boolean | undefined;
  pulseGlow?: string | undefined;
  className?: string | undefined;
  style?: CSSProperties | undefined;
  role?: string | undefined;
  "aria-label"?: string | undefined;
}

/** Indicador luminoso de status — consolida as 6 implementações que existiam
 *  cada uma com seu próprio CSS quase idêntico (StatusBar, Annunciator,
 *  AutomacoesPage, StatusTag `.dot`, Mimico `.laneLamp`/`.workerLamp`). */
export function Lamp({
  size,
  shape = "circle",
  color,
  blink,
  pulse,
  pulseGlow,
  className,
  style,
  role,
  "aria-label": ariaLabel,
}: LampProps) {
  return (
    <span
      role={role}
      aria-label={ariaLabel}
      className={[styles.lamp, shape === "square" ? styles.square : styles.circle, className]
        .filter(Boolean)
        .join(" ")}
      style={{
        width: size,
        height: size,
        background: color,
        animation: blink
          ? "blink-alarm 1s steps(1, end) infinite"
          : pulse
            ? "pulse-ring 2s var(--ease) infinite"
            : undefined,
        ...(pulse && pulseGlow ? ({ "--pulse-glow": pulseGlow } as CSSProperties) : {}),
        ...style,
      }}
    />
  );
}
