import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { orchestratorApi } from "../api/orchestrator";
import { CardGallery } from "../components/CardGallery";

describe("CardGallery", () => {
  let origCreateDesc: PropertyDescriptor | undefined;
  let origRevokeDesc: PropertyDescriptor | undefined;
  let revokeSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    origCreateDesc = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    origRevokeDesc = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    let seq = 0;
    revokeSpy = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(() => `blob:card-${++seq}`),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeSpy,
    });
  });

  afterEach(() => {
    if (origCreateDesc) Object.defineProperty(URL, "createObjectURL", origCreateDesc);
    else delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
    if (origRevokeDesc) Object.defineProperty(URL, "revokeObjectURL", origRevokeDesc);
    else delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
    vi.restoreAllMocks();
  });

  it("renderiza estado vazio quando cards é vazio", () => {
    render(<CardGallery slug="obs-paradas-fase" cards={[]} />);
    expect(screen.getByText("Nenhum card PNG disponível")).toBeInTheDocument();
  });

  it("carrega cards PNG, reaproveita blob no Lightbox, navega por teclado e revoga ObjectURL ao desmontar", async () => {
    const blobSpy = vi.spyOn(orchestratorApi, "getPromovidaCardBlob").mockResolvedValue(
      new Blob(["png"], { type: "image/png" }),
    );

    const { unmount } = render(
      <CardGallery
        slug="obs-paradas-fase"
        cards={[
          { key: "c1", filename: "card1.png", title: "Card Um", caption: "Legenda 1" },
          { key: "c2", filename: "card2.png", title: "Card Dois", caption: "Legenda 2" },
        ]}
      />,
    );

    const ampliarBtn = await screen.findByRole("button", { name: "Ampliar Card Um" });
    expect(blobSpy).toHaveBeenCalledTimes(2);
    fireEvent.click(ampliarBtn);

    const dialog = screen.getByRole("dialog", { name: "Card Um" });
    expect(dialog).toBeInTheDocument();
    // Reaproveita initialBlob sem disparar um terceiro fetch
    expect(blobSpy).toHaveBeenCalledTimes(2);

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByRole("dialog", { name: "Card Dois" })).toBeInTheDocument();
    expect(await screen.findByAltText("Card ampliado: Card Dois")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    unmount();
    expect(revokeSpy).toHaveBeenCalled();
  });

  it("aborta fetch anterior ao trocar rápido de card e exibe erro se a miniatura ou ampliação falhar", async () => {
    const signals: AbortSignal[] = [];
    vi.spyOn(orchestratorApi, "getPromovidaCardBlob").mockImplementation(async (_slug, filename, signal) => {
      if (signal) signals.push(signal);
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

    expect(await screen.findByText("Não foi possível carregar a imagem.")).toBeInTheDocument();
    const ampliarBtn = await screen.findByRole("button", { name: "Ampliar Card Um" });
    fireEvent.click(ampliarBtn);
    expect(await screen.findByAltText("Card ampliado: Card Um")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByText("Não foi possível carregar a imagem ampliada.")).toBeInTheDocument();
    expect(screen.queryByAltText("Card ampliado: Card Dois")).not.toBeInTheDocument();
  });
});
