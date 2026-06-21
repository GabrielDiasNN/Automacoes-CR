import type { ReactNode } from "react";
import { toneTint, toneVar, type Tone } from "../../lib/status";
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
        <span
          className={styles.dot}
          style={{
            background: toneVar[tone],
            animation: pulse ? "pulse-ring 2s var(--ease) infinite" : undefined,
          }}
        />
      )}
      {children}
    </span>
  );
}
