import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi } from "../api/orchestrator";
import { CommandPalette } from "../components/CommandPalette";

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="current-location">{loc.pathname + loc.search}</div>;
}

describe("CommandPalette — busca global de telas, consultas PCP e automações", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("filtra consultas PCP, navega para /pcp?slug=... e não exibe resultados obsoletos ao reabrir", async () => {
    vi.useFakeTimers();
    const listAutosSpy = vi.spyOn(orchestratorApi, "listAutomations").mockResolvedValue([]);
    const getPromovidasSpy = vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
      items: [
        {
          slug: "rama-risco-atraso",
          codigo: "CP-01",
          nome: "Risco Atraso Ramas",
          titulo: "Risco Atraso Ramas",
          setor: "Acabamento & Ramas",
          modo: "sombra",
          destinos: ["dashboard"],
          has_snapshot: true,
          generated_at: null,
          age_minutes: null,
          total_rows: 10,
          excecoes_count: 2,
          kpis: {},
        },
      ],
    });
    const onClose = vi.fn();
    const navItems = [{ to: "/painel", label: "Visão Geral", icon: <span /> }];

    const { rerender } = render(
      <MemoryRouter initialEntries={["/painel"]}>
        <LocationProbe />
        <Routes>
          <Route
            path="*"
            element={<CommandPalette open onClose={onClose} navItems={navItems} />}
          />
        </Routes>
      </MemoryRouter>,
    );

    const input = screen.getByRole("combobox", { name: "Busca global" });
    fireEvent.change(input, { target: { value: "Ramas" } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(260);
    });

    const optionText = screen.getByText("CP-01 · Risco Atraso Ramas");
    const optionBtn = optionText.closest("button");
    expect(optionBtn).not.toBeNull();
    expect(optionBtn).toHaveAttribute("tabindex", "-1");
    expect(input.getAttribute("aria-activedescendant")).toBe(optionBtn!.id);

    fireEvent.click(optionText);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("current-location")).toHaveTextContent("/pcp?slug=rama-risco-atraso");

    // Fechar e reabrir não deve disparar novas requisições com a busca anterior
    const autosCallsAntes = listAutosSpy.mock.calls.length;
    const promCallsAntes = getPromovidasSpy.mock.calls.length;
    rerender(
      <MemoryRouter initialEntries={["/painel"]}>
        <LocationProbe />
        <Routes>
          <Route
            path="*"
            element={<CommandPalette open={false} onClose={onClose} navItems={navItems} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    rerender(
      <MemoryRouter initialEntries={["/painel"]}>
        <LocationProbe />
        <Routes>
          <Route
            path="*"
            element={<CommandPalette open onClose={onClose} navItems={navItems} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(listAutosSpy).toHaveBeenCalledTimes(autosCallsAntes);
    expect(getPromovidasSpy).toHaveBeenCalledTimes(promCallsAntes);
  });
});
