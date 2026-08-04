import type { SelectHTMLAttributes } from "react";
import styles from "./Select.module.css";

/** Select padrão — consolida o estilo duplicado 8x em FilterBar. */
export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={[styles.select, className].filter(Boolean).join(" ")} {...rest} />;
}
