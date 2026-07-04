import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { getApiKey } from "../api/client";
import { useApiKey } from "../hooks/useApiKey";

const STORAGE_KEY = "orchestrator_api_key";

describe("useApiKey", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("inicia vazio quando não há chave no sessionStorage", () => {
    const { result } = renderHook(() => useApiKey());
    expect(result.current.apiKey).toBe("");
  });

  it("lê a chave já persistida no sessionStorage ao montar", () => {
    sessionStorage.setItem(STORAGE_KEY, "chave-existente");
    const { result } = renderHook(() => useApiKey());
    expect(result.current.apiKey).toBe("chave-existente");
  });

  it("saveKey persiste no sessionStorage e sincroniza o cliente de API", () => {
    const { result } = renderHook(() => useApiKey());

    act(() => {
      result.current.saveKey("nova-chave");
    });

    expect(result.current.apiKey).toBe("nova-chave");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("nova-chave");
    expect(getApiKey()).toBe("nova-chave");
  });

  it("clearKey remove do sessionStorage e reseta o cliente de API", () => {
    const { result } = renderHook(() => useApiKey());

    act(() => {
      result.current.saveKey("chave-a-limpar");
    });
    act(() => {
      result.current.clearKey();
    });

    expect(result.current.apiKey).toBe("");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(getApiKey()).toBe("");
  });

  it("não usa localStorage — a chave não persiste entre sessões (só sessionStorage)", () => {
    const { result } = renderHook(() => useApiKey());

    act(() => {
      result.current.saveKey("chave-de-sessao");
    });

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
