import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./ListRow.module.css";

interface ListRowProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Cor (var CSS ou valor resolvido) da faixa de destaque à esquerda. */
  tone?: string;
  leading?: ReactNode;
  trailing?: ReactNode;
  children: ReactNode;
}

/** Linha de lista clicável — feed compacto sem cabeçalho de tabela (ex.: últimas execuções). */
export function ListRow({ tone, leading, trailing, children, className, style, type = "button", ...rest }: ListRowProps) {
  const cls = [styles.row, className].filter(Boolean).join(" ");
  return (
    <button
      type={type}
      className={cls}
      style={{ ...(tone ? { boxShadow: `inset 3px 0 0 ${tone}` } : undefined), ...style }}
      {...rest}
    >
      {leading}
      <span className={styles.label}>{children}</span>
      {trailing}
    </button>
  );
}
