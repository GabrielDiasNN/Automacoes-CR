import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setApiKey, setUnauthorizedHandler } from "../api/client";
import { ApiKeyProvider, useApiKeyContext } from "../context/ApiKeyContext";
import { TableDensityProvider, useTableDensity } from "../context/TableDensityContext";

const STORAGE_KEY = "orchestrator_table_density";

function renderTableDensity() {
  return renderHook(() => useTableDensity(), { wrapper: TableDensityProvider });
}

describe("TableDensityContext", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("inicia em 'comfortable' quando não há valor salvo no localStorage", () => {
    const { result } = renderTableDensity();
    expect(result.current.density).toBe("comfortable");
  });

  it("lê a densidade 'compact' persistida no localStorage ao montar", () => {
    localStorage.setItem(STORAGE_KEY, "compact");
    const { result } = renderTableDensity();
    expect(result.current.density).toBe("compact");
  });

  it("alterna entre 'comfortable' e 'compact' e persiste no localStorage", () => {
    const { result } = renderTableDensity();

    act(() => result.current.toggleDensity());
    expect(result.current.density).toBe("compact");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("compact");

    act(() => result.current.toggleDensity());
    expect(result.current.density).toBe("comfortable");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("comfortable");
  });

  it("recupera para 'comfortable' ao alternar a partir de valor inválido no localStorage", () => {
    localStorage.setItem(STORAGE_KEY, "desconhecido");
    const { result } = renderTableDensity();

    act(() => result.current.toggleDensity());
    expect(result.current.density).toBe("comfortable");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("comfortable");
  });

  it("lança erro quando useTableDensity é chamado fora de TableDensityProvider", () => {
    expect(() => renderHook(() => useTableDensity())).toThrow(
      "useTableDensity deve ser usado dentro de TableDensityProvider",
    );
  });
});

describe("ApiKeyProvider — callback de 401/403 via api/client", () => {
  afterEach(() => {
    sessionStorage.clear();
    setApiKey("");
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });

  it("limpa a chave quando o cliente recebe 401", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Unauthorized", { status: 401, statusText: "Unauthorized" }),
    );

    const { result } = renderHook(() => useApiKeyContext(), { wrapper: ApiKeyProvider });

    act(() => result.current.saveKey("chave-valida"));
    expect(result.current.hasKey).toBe(true);
    expect(result.current.apiKey).toBe("chave-valida");

    await act(async () => {
      await expect(api.get("/api/ping")).rejects.toBeInstanceOf(ApiError);
    });

    expect(result.current.hasKey).toBe(false);
    expect(result.current.apiKey).toBe("");
  });

  it("limpa a chave quando o cliente recebe 403 indicando API Key inválida", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("API Key inválida", { status: 403, statusText: "Forbidden" }),
    );

    const { result } = renderHook(() => useApiKeyContext(), { wrapper: ApiKeyProvider });

    act(() => result.current.saveKey("chave-expirada"));
    expect(result.current.hasKey).toBe(true);

    await act(async () => {
      await expect(api.get("/api/ping")).rejects.toBeInstanceOf(ApiError);
    });

    expect(result.current.hasKey).toBe(false);
    expect(result.current.apiKey).toBe("");
  });
});
