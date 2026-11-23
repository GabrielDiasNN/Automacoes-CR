import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { useOverlayDismiss } from "../hooks/useOverlayDismiss";

interface OverlayHarnessProps {
  active: boolean;
  onDismiss: () => void;
}

function OverlayHarness({ active, onDismiss }: OverlayHarnessProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  useOverlayDismiss(overlayRef, active, onDismiss);

  return (
    <div ref={overlayRef} data-testid="scrim">
      <div data-testid="content">
        <button type="button">Ação interna</button>
      </div>
    </div>
  );
}

describe("useOverlayDismiss", () => {
  it("dispara onDismiss ao clicar (mousedown) diretamente no scrim", () => {
    const onDismiss = vi.fn();
    render(<OverlayHarness active onDismiss={onDismiss} />);

    fireEvent.mouseDown(screen.getByTestId("scrim"));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("não dispara onDismiss ao clicar dentro do conteúdo do diálogo", () => {
    const onDismiss = vi.fn();
    render(<OverlayHarness active onDismiss={onDismiss} />);

    fireEvent.mouseDown(screen.getByTestId("content"));
    fireEvent.mouseDown(screen.getByRole("button", { name: "Ação interna" }));
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("não dispara quando inativo e remove listener no cleanup ao fechar ou desmontar", () => {
    const onDismiss = vi.fn();
    const { rerender, unmount } = render(<OverlayHarness active={false} onDismiss={onDismiss} />);

    fireEvent.mouseDown(screen.getByTestId("scrim"));
    expect(onDismiss).not.toHaveBeenCalled();

    // Ativa e valida funcionamento
    rerender(<OverlayHarness active onDismiss={onDismiss} />);
    fireEvent.mouseDown(screen.getByTestId("scrim"));
    expect(onDismiss).toHaveBeenCalledTimes(1);

    // Desativa → cleanup remove listener
    rerender(<OverlayHarness active={false} onDismiss={onDismiss} />);
    fireEvent.mouseDown(screen.getByTestId("scrim"));
    expect(onDismiss).toHaveBeenCalledTimes(1);

    // Reativa e desmonta → listener removido no unmount
    const scrim = screen.getByTestId("scrim");
    rerender(<OverlayHarness active onDismiss={onDismiss} />);
    unmount();
    fireEvent.mouseDown(scrim);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("usa sempre a referência mais recente de onDismiss", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(<OverlayHarness active onDismiss={first} />);

    rerender(<OverlayHarness active onDismiss={second} />);
    fireEvent.mouseDown(screen.getByTestId("scrim"));

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
