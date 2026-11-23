import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi } from "../api/orchestrator";
import { CardGallery } from "../components/CardGallery";

describe("CardGallery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("carrega cards PNG, abre Lightbox com navegação por teclado e permite ampliar/fechar", async () => {
    if (!URL.createObjectURL) {
      URL.createObjectURL = vi.fn(() => "blob:card-1");
      URL.revokeObjectURL = vi.fn();
    } else {
      vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:card-1");
      vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    }

    vi.spyOn(orchestratorApi, "getPromovidaCardBlob").mockResolvedValue(
      new Blob(["png"], { type: "image/png" }),
    );

    render(
      <CardGallery
        slug="obs-paradas-fase"
        cards={[
          { key: "c1", filename: "card1.png", title: "Card Um", caption: "Legenda 1" },
          { key: "c2", filename: "card2.png", title: "Card Dois", caption: "Legenda 2" },
        ]}
      />,
    );

    const ampliarBtn = await screen.findByRole("button", { name: "Ampliar Card Um" });
    fireEvent.click(ampliarBtn);

    const dialog = screen.getByRole("dialog", { name: "Card Um" });
    expect(dialog).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByRole("dialog", { name: "Card Dois" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("limpa imagem anterior e mostra erro quando o card seguinte falha ao carregar", async () => {
    if (!URL.createObjectURL) {
      URL.createObjectURL = vi.fn(() => "blob:card-ok");
      URL.revokeObjectURL = vi.fn();
    } else {
      vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:card-ok");
      vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    }

    vi.spyOn(orchestratorApi, "getPromovidaCardBlob").mockImplementation(async (_slug, filename) => {
      if (filename === "card2.png") throw new Error("404 Not Found");
      return new Blob(["png"], { type: "image/png" });
    });

    render(
      <CardGallery
        slug="obs-paradas-fase"
        cards={[
          { key: "c1", filename: "card1.png", title: "Card Um", caption: "" },
          { key: "c2", filename: "card2.png", title: "Card Dois", caption: "" },
        ]}
      />,
    );

    const ampliarBtn = await screen.findByRole("button", { name: "Ampliar Card Um" });
    fireEvent.click(ampliarBtn);
    expect(await screen.findByAltText("Card ampliado: Card Um")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByText("Não foi possível carregar a imagem ampliada.")).toBeInTheDocument();
    expect(screen.queryByAltText("Card ampliado: Card Dois")).not.toBeInTheDocument();
  });
});
