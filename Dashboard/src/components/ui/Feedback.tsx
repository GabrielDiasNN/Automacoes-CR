import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import styles from "./Feedback.module.css";

/** Estado vazio — convite para agir, não apenas "nada aqui". */
export function EmptyState({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className={styles.empty}>
      {icon && <div className={styles.emptyIcon}>{icon}</div>}
      <div className={styles.emptyTitle}>{title}</div>
      {hint && <div className={styles.emptyHint}>{hint}</div>}
    </div>
  );
}

/** Carregando — leitura de instrumento "aguardando sinal". */
export function Loading({ label = "carregando" }: { label?: string }) {
  return (
    <div className={styles.loading}>
      <Loader2 size={15} className={styles.spin} />
      <span>{label}…</span>
    </div>
  );
}

/** Erro de carregamento — direção, não desculpa. */
export function ErrorState({ message }: { message: string }) {
  return (
    <div className={styles.error}>
      <AlertTriangle size={15} />
      <span>{message}</span>
    </div>
  );
}

/** Placeholder de carregamento (shimmer discreto). */
export function Skeleton({ height = 16, width = "100%" }: { height?: number; width?: number | string }) {
  return <span className={styles.skeleton} style={{ height, width }} />;
}
