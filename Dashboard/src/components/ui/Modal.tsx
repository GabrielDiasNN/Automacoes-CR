import { useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { Button } from "./Button";
import styles from "./Modal.module.css";

interface ConfirmModalProps {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Diálogo de confirmação centralizado para ações sensíveis. */
export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  danger,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, open, onCancel);
  const titleId = useId();

  if (!open) return null;

  return createPortal(
    // Overlay de clique-fora do modal (padrão sem equivalente nativo).
    // Fecha só quando o próprio overlay é o alvo do evento — evita precisar
    // de stopPropagation no filho. Escape já fecha via useFocusTrap.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div className={`overlay-scrim ${styles.overlay}`} onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div
        ref={ref}
        className={`${styles.box} animate-in`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <h3 id={titleId} className={styles.title}>{title}</h3>
        <div className={styles.message}>{message}</div>
        <div className={styles.actions}>
          <Button variant="subtle" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
