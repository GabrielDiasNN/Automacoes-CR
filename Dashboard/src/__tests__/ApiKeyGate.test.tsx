import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { getApiKey, setUnauthorizedHandler } from "../api/client";
import { ApiKeyGate } from "../components/ApiKeyGate";
import { ApiKeyProvider, useApiKeyContext } from "../context/ApiKeyContext";

function ContextProbe() {
  const { apiKey, clearKey } = useApiKeyContext();
  return (
    <div>
      <span data-testid="ctx-key">{apiKey}</span>
      <button onClick={clearKey}>Sair</button>
    </div>
  );
}

describe("ApiKeyContext e ApiKeyGate", () => {
  afterEach(() => {
    sessionStorage.clear();
    setUnauthorizedHandler(null);
  });

  it("lança erro ao usar useApiKeyContext fora de ApiKeyProvider", () => {
    expect(() => render(<ContextProbe />)).toThrow(
      "useApiKeyContext deve ser usado dentro de ApiKeyProvider",
    );
  });

  it("valida chave vazia, autentica chave válida e limpa ao sair", () => {
    render(
      <ApiKeyProvider>
        <ApiKeyGate>
          <ContextProbe />
        </ApiKeyGate>
      </ApiKeyProvider>,
    );

    // Chave vazia exibe erro acessível
    fireEvent.click(screen.getByRole("button", { name: /Entrar/i }));
    expect(screen.getByRole("alert")).toHaveTextContent("Chave não pode estar vazia.");

    // Digitar e enviar chave válida libera os filhos e sincroniza client.ts
    const input = screen.getByLabelText("API Key");
    fireEvent.change(input, { target: { value: "  chave-segura-123  " } });
    fireEvent.click(screen.getByRole("button", { name: /Entrar/i }));

    expect(screen.getByTestId("ctx-key")).toHaveTextContent("chave-segura-123");
    expect(getApiKey()).toBe("chave-segura-123");

    // Simular logout / limpeza de chave
    fireEvent.click(screen.getByRole("button", { name: "Sair" }));
    expect(screen.getByLabelText("API Key")).toBeInTheDocument();
  });
});
