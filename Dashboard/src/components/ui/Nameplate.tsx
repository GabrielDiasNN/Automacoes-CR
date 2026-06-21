import type { ReactNode } from "react";
import styles from "./Nameplate.module.css";

interface NameplateProps {
  /** linha mono superior, ex.: "// operação" */
  eyebrow?: string;
  title: string;
  actions?: ReactNode;
  /** tamanho do título: page = hero, section = menor */
  size?: "page" | "section";
}

/** Cabeçalho gravado (placa). Estrutura que ancora a página/seção. */
export function Nameplate({ eyebrow, title, actions, size = "page" }: NameplateProps) {
  return (
    <header className={styles.head}>
      <div className={styles.left}>
        {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
        <h2 className={size === "page" ? styles.titlePage : styles.titleSection}>{title}</h2>
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </header>
  );
}
