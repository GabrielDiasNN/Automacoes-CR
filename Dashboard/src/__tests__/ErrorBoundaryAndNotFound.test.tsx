import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { NotFoundPage } from "../pages/NotFoundPage";

function BrokenChild(): never {
  throw new Error("Falha simulada de renderização");
}

describe("ErrorBoundary e NotFoundPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("ErrorBoundary captura exceção de render e exibe botão Recarregar", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const reloadSpy = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, reload: reloadSpy },
      configurable: true,
    });

    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Algo quebrou nesta tela");
    expect(screen.getByText("Falha simulada de renderização")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Recarregar" }));
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });

  it("NotFoundPage exibe o caminho inexistente e navega para /painel", () => {
    render(
      <MemoryRouter initialEntries={["/rota-que-nao-existe"]}>
        <Routes>
          <Route path="/painel" element={<div>Painel Destino</div>} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/Não existe rota para "\/rota-que-nao-existe"/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ir para o Painel" }));
    expect(screen.getByText("Painel Destino")).toBeInTheDocument();
  });
});
