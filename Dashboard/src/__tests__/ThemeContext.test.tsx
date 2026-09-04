import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ThemeProvider, useTheme } from "../context/ThemeContext";

const STORAGE_KEY = "orchestrator_theme";

function renderTheme() {
  return renderHook(() => useTheme(), { wrapper: ThemeProvider });
}

describe("ThemeContext", () => {
  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("inicia em 'system' quando não há nada no localStorage", () => {
    const { result } = renderTheme();
    expect(result.current.theme).toBe("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("lê o tema já persistido no localStorage ao montar", () => {
    localStorage.setItem(STORAGE_KEY, "dark");
    const { result } = renderTheme();
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("cycleTheme avança system -> light -> dark -> system, persistindo cada passo", () => {
    const { result } = renderTheme();

    act(() => result.current.cycleTheme());
    expect(result.current.theme).toBe("light");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    act(() => result.current.cycleTheme());
    expect(result.current.theme).toBe("dark");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    act(() => result.current.cycleTheme());
    expect(result.current.theme).toBe("system");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("system");
    // "system" não seta o atributo — deixa o @media (prefers-color-scheme) decidir.
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});
