import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useFocusTrap } from "../hooks/useFocusTrap";

const originalOffsetParent = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "offsetParent",
);

function setMockOffsetParent() {
  Object.defineProperty(HTMLElement.prototype, "offsetParent", {
    configurable: true,
    get() {
      return (this as HTMLElement).style.display === "none" ? null : document.body;
    },
  });
}

function restoreOffsetParent() {
  if (originalOffsetParent) {
    Object.defineProperty(HTMLElement.prototype, "offsetParent", originalOffsetParent);
  } else {
    delete (HTMLElement.prototype as { offsetParent?: unknown }).offsetParent;
  }
}

interface DialogHarnessProps {
  initialActive?: boolean;
  onClose?: () => void;
  empty?: boolean;
}

function DialogHarness({
  initialActive = false,
  onClose = () => {},
  empty = false,
}: DialogHarnessProps) {
  const [active, setActive] = useState(initialActive);
  const dialogRef = useRef<HTMLDivElement>(null);

  useFocusTrap(dialogRef, active, () => {
    onClose();
    setActive(false);
  });

  return (
    <div>
      <button type="button" onClick={() => setActive(true)}>
        Abrir
      </button>
      <div ref={dialogRef} tabIndex={-1} data-testid="dialog">
        {!empty && (
          <>
            <button type="button" disabled>
              Desabilitado
            </button>
            <button type="button" style={{ display: "none" }}>
              Oculto
            </button>
            <button type="button">Primeiro</button>
            <input type="text" aria-label="Campo" />
            <button type="button">Ultimo</button>
          </>
        )}
      </div>
    </div>
  );
}

describe("useFocusTrap", () => {
  beforeEach(() => {
    setMockOffsetParent();
  });

  afterEach(() => {
    restoreOffsetParent();
  });

  it("não prende foco nem reage a Escape quando inativo", () => {
    const onClose = vi.fn();
    render(<DialogHarness initialActive={false} onClose={onClose} />);

    const trigger = screen.getByRole("button", { name: "Abrir" });
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(trigger);
  });

  it("move o foco inicial para o primeiro elemento focável visível e habilitado", () => {
    render(<DialogHarness initialActive />);

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Primeiro" }));
  });

  it("faz ciclo de Tab e Shift+Tab entre o primeiro e o último elemento focável", () => {
    render(<DialogHarness initialActive />);

    const first = screen.getByRole("button", { name: "Primeiro" });
    const middle = screen.getByLabelText("Campo");
    const last = screen.getByRole("button", { name: "Ultimo" });

    // Shift+Tab no primeiro → volta para o último
    expect(document.activeElement).toBe(first);
    const shiftTabEvt = new KeyboardEvent("keydown", {
      key: "Tab",
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(shiftTabEvt);
    expect(shiftTabEvt.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(last);

    // Tab no último → volta para o primeiro
    const tabEvt = new KeyboardEvent("keydown", {
      key: "Tab",
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(tabEvt);
    expect(tabEvt.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);

    // Tab em elemento intermediário não previne o comportamento padrão
    middle.focus();
    const middleTabEvt = new KeyboardEvent("keydown", {
      key: "Tab",
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(middleTabEvt);
    expect(middleTabEvt.defaultPrevented).toBe(false);

    // Tecla comum é ignorada
    const otherEvt = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(otherEvt);
    expect(otherEvt.defaultPrevented).toBe(false);
  });

  it("chama onClose e interrompe propagação ao pressionar Escape", () => {
    const onClose = vi.fn();
    const outerKeyDown = vi.fn();
    document.addEventListener("keydown", outerKeyDown);

    try {
      render(<DialogHarness initialActive onClose={onClose} />);
      fireEvent.keyDown(document, { key: "Escape" });

      expect(onClose).toHaveBeenCalledTimes(1);
      expect(outerKeyDown).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener("keydown", outerKeyDown);
    }
  });

  it("restaura o foco anterior ao fechar e ao desmontar", () => {
    const { unmount } = render(<DialogHarness initialActive={false} />);

    const trigger = screen.getByRole("button", { name: "Abrir" });
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    fireEvent.click(trigger);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Primeiro" }));

    // Fechar via Escape restaura o foco no botão que abriu
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(trigger);

    // Abrir novamente e desmontar também restaura o foco anterior
    fireEvent.click(trigger);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Primeiro" }));
    unmount();
    expect(document.activeElement).toBe(document.body);
  });

  it("foca o próprio container e bloqueia Tab quando não há elementos focáveis", () => {
    render(<DialogHarness initialActive empty />);

    const dialog = screen.getByTestId("dialog");
    expect(document.activeElement).toBe(dialog);

    const tabEvt = new KeyboardEvent("keydown", {
      key: "Tab",
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(tabEvt);
    expect(tabEvt.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(dialog);
  });
});
