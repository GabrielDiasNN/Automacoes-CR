import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Theme = "system" | "light" | "dark";

const STORAGE_KEY = "orchestrator_theme";
const CYCLE: readonly Theme[] = ["system", "light", "dark"];

interface ThemeContextValue {
  theme: Theme;
  cycleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

// Única fonte de verdade para a transição do ciclo — usada por cycleTheme
// e exportada para quem precisa anunciar o próximo tema (ex.: aria-label
// do botão no Shell) sem reimplementar a sequência.
export function nextTheme(theme: Theme): Theme {
  return CYCLE[(CYCLE.indexOf(theme) + 1) % CYCLE.length]!;
}

function readStoredTheme(): Theme {
  const raw = localStorage.getItem(STORAGE_KEY);
  return CYCLE.includes(raw as Theme) ? (raw as Theme) : "system";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  // "system" não seta o atributo — deixa o @media (prefers-color-scheme)
  // do tokens.css decidir. light/dark setam explicitamente e vencem o OS
  // (tokens.css guarda a regra de media com :root:not([data-theme="dark"])).
  useEffect(() => {
    if (theme === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", theme);
    }
  }, [theme]);

  const cycleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = nextTheme(prev);
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  // Mesmo racional do TableDensityContext (achado nº 30, Onda 5): sem
  // useMemo, todo consumidor via useContext re-renderiza a cada render do
  // provider, mesmo quando `theme` não muda.
  const value = useMemo(() => ({ theme, cycleTheme }), [theme, cycleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme deve ser usado dentro de ThemeProvider");
  return ctx;
}
