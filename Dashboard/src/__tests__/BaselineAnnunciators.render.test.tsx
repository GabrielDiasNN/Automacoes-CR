import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BaselineAnnunciators } from "../components/ui";

const metricas = [
  { code: "fila", label: "fila", status: "healthy", current_value: "2" },
  { code: "erros", label: "erros 24h", status: "attention", current_value: "7" },
  { code: "worker", label: "worker", status: "incident", current_value: null },
];

describe("BaselineAnnunciators", () => {
  it("mostra legenda e valor de cada métrica e o rótulo de estado só nas lâmpadas acesas", () => {
    render(<BaselineAnnunciators metrics={metricas} />);

    expect(screen.getByText("fila")).toBeInTheDocument();
    expect(screen.getByText("erros 24h")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("atenção")).toBeInTheDocument();
    expect(screen.getByText("incidente")).toBeInTheDocument();
    // `healthy` fica apagada: nenhum rótulo de estado é renderizado para ela.
    expect(screen.queryByText("saudável")).toBeNull();
  });

  it("deriva o tom com healthTone: atenção acende âmbar e incidente acende vermelho", () => {
    render(<BaselineAnnunciators metrics={metricas} />);

    const tileDe = (legenda: string) => screen.getByText(legenda).parentElement as HTMLElement;
    expect(tileDe("erros 24h").style.getPropertyValue("--tile-color")).toBe("var(--amber)");
    expect(tileDe("worker").style.getPropertyValue("--tile-color")).toBe("var(--red)");
    expect(tileDe("fila").style.getPropertyValue("--tile-color")).toBe("");
  });

  it("renderiza uma lista vazia sem erro", () => {
    const { container } = render(<BaselineAnnunciators metrics={[]} />);
    expect(container.firstElementChild).not.toBeNull();
    expect(container.querySelectorAll("span").length).toBe(0);
  });
});
