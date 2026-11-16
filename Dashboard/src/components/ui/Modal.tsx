import { useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { useOverlayDismiss } from "../../hooks/useOverlayDismiss";
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
  const overlayRef = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, open, onCancel);
  useOverlayDismiss(overlayRef, open, onCancel);
  const titleId = useId();

  if (!open) return null;

  return createPortal(
    // Clique-fora via `useOverlayDismiss`; Escape já fecha via useFocusTrap.
    <div ref={overlayRef} className={`overlay-scrim ${styles.overlay}`}>
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
