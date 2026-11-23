import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi } from "../api/orchestrator";
import { CommandPalette } from "../components/CommandPalette";

describe("CommandPalette — busca global de telas, consultas PCP e automações", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("filtra consultas PCP e navega para /pcp?slug=...", async () => {
    vi.spyOn(orchestratorApi, "listAutomations").mockResolvedValue([]);
    vi.spyOn(orchestratorApi, "getPromovidas").mockResolvedValue({
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

    render(
      <MemoryRouter initialEntries={["/painel"]}>
        <Routes>
          <Route
            path="*"
            element={
              <CommandPalette
                open
                onClose={onClose}
                navItems={[{ to: "/painel", label: "Visão Geral", icon: <span /> }]}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    const input = screen.getByRole("combobox", { name: "Busca global" });
    fireEvent.change(input, { target: { value: "Ramas" } });

    const optionText = await screen.findByText("CP-01 · Risco Atraso Ramas");
    const optionBtn = optionText.closest("button");
    expect(optionBtn).not.toBeNull();
    expect(input.getAttribute("aria-activedescendant")).toBe(optionBtn!.id);

    fireEvent.click(optionText);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
