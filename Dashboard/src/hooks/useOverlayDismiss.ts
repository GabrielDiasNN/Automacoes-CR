import { useEffect, useRef, type RefObject } from "react";

/** Clique-fora de um diálogo: fecha quando o mousedown tem como alvo o próprio
 *  overlay (não um filho). Escape já é tratado por `useFocusTrap`.
 *
 *  O listener é nativo, anexado ao elemento do overlay, e não um `onMouseDown`
 *  no JSX: o overlay não recebe papel interativo (jsx-a11y), pois o fechamento
 *  por mouse é só conveniência — o teclado fecha pelo Escape. */
export function useOverlayDismiss(
  overlayRef: RefObject<HTMLElement>,
  active: boolean,
  onDismiss: () => void,
): void {
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!active || !overlay) return;
    const onMouseDown = (e: MouseEvent) => {
      if (e.target === overlay) onDismissRef.current();
    };
    overlay.addEventListener("mousedown", onMouseDown);
    return () => overlay.removeEventListener("mousedown", onMouseDown);
  }, [active, overlayRef]);
}
