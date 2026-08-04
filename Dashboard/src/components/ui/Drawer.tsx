import { useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { IconButton } from "./IconButton";
import styles from "./Drawer.module.css";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  eyebrow?: string;
  children: ReactNode;
  width?: number;
}

/** Painel lateral (detalhe/visor). Focus-trap + Escape + clique fora. */
export function Drawer({ open, onClose, title, eyebrow, children, width = 560 }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(panelRef, open, onClose);

  if (!open) return null;

  return createPortal(
    <div className={styles.overlay} onMouseDown={onClose}>
      <aside
        ref={panelRef}
        className={`${styles.panel} animate-in`}
        style={{ width: `min(${width}px, 96vw)` }}
        role="dialog"
        aria-modal="true"
        aria-label={title ?? "Detalhe"}
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className={styles.head}>
          <div className={styles.headText}>
            {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
            {title && <h3 className={styles.title}>{title}</h3>}
          </div>
          <IconButton onClick={onClose} aria-label="Fechar painel">
            <X size={18} />
          </IconButton>
        </header>
        <div className={styles.body}>{children}</div>
      </aside>
    </div>,
    document.body,
  );
}
