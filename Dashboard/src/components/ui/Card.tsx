import type { ReactNode } from "react";
import styles from "./Card.module.css";

interface CardProps {
  /** rótulo mono gravado no topo do painel */
  label?: string;
  actions?: ReactNode;
  children: ReactNode;
  /** demarca o painel como zona de atenção (faixa de risco no topo) */
  alert?: boolean;
  padded?: boolean;
  className?: string;
}

/** Painel de instrumento com cabeçalho de placa opcional. */
export function Card({ label, actions, children, alert, padded = true, className }: CardProps) {
  return (
    <section className={[styles.card, alert ? styles.alert : "", className].filter(Boolean).join(" ")}>
      {alert && <div className={`hazard ${styles.hazardBar}`} aria-hidden="true" />}
      {(label || actions) && (
        <div className={styles.head}>
          {label && <span className={styles.label}>{label}</span>}
          {actions && <div className={styles.actions}>{actions}</div>}
        </div>
      )}
      <div className={padded ? styles.body : undefined}>{children}</div>
    </section>
  );
}
