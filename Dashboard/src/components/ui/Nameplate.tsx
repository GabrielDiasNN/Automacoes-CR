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

/** Cabeçalho gravado (placa). Estrutura que ancora a página/seção.
 *  `size="page"` (o uso de longe mais comum — cada página chama exatamente
 *  um `<Nameplate>` no topo) emite `<h1>`: antes não existia NENHUM `<h1>`
 *  no app inteiro, e a navegação por cabeçalho de leitor de tela — uma forma
 *  padrão de pular direto ao conteúdo — ficava sem âncora nenhuma. */
export function Nameplate({ eyebrow, title, actions, size = "page" }: NameplateProps) {
  const Titulo = size === "page" ? "h1" : "h2";
  return (
    <header className={styles.head}>
      <div className={styles.left}>
        {eyebrow && <div className="label-mono eyebrow">{eyebrow}</div>}
        <Titulo className={size === "page" ? styles.titlePage : styles.titleSection}>{title}</Titulo>
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </header>
  );
}
