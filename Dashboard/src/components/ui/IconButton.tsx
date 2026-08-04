import type { ButtonHTMLAttributes } from "react";
import styles from "./IconButton.module.css";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "bordered" | "plain";
  size?: "sm" | "md";
  active?: boolean;
  "aria-label": string;
}

/** Botão só-ícone — consolida os padrões repetidos em Shell/Drawer/LogViewer/etc. */
export function IconButton({
  variant = "bordered",
  size = "md",
  active,
  className,
  type = "button",
  ...rest
}: IconButtonProps) {
  const cls = [styles.btn, styles[variant], styles[size], active ? styles.active : "", className]
    .filter(Boolean)
    .join(" ");
  return <button type={type} className={cls} {...rest} />;
}
