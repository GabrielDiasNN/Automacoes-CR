import type { CSSProperties, InputHTMLAttributes, ReactNode } from "react";
import styles from "./Input.module.css";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  /** Espaço reservado à direita (px) quando algo é sobreposto ao campo, ex.: botão de limpar. */
  trailingPadding?: number;
}

/** Campo de texto/data padrão — consolida os estilos duplicados em FilterBar/ProductAutocomplete. */
export function Input({ icon, trailingPadding, className, style, ...rest }: InputProps) {
  const mergedStyle: CSSProperties | undefined =
    trailingPadding != null ? { paddingRight: trailingPadding, ...style } : style;

  if (icon) {
    return (
      <div className={styles.iconWrap}>
        <span className={styles.icon} aria-hidden="true">
          {icon}
        </span>
        <input
          className={[styles.input, styles.withIcon, className].filter(Boolean).join(" ")}
          style={mergedStyle}
          {...rest}
        />
      </div>
    );
  }
  return (
    <input className={[styles.input, className].filter(Boolean).join(" ")} style={mergedStyle} {...rest} />
  );
}
