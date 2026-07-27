import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/__tests__/**/*.test.{ts,tsx}"],
    globals: false,
    css: false,
    coverage: {
      provider: "v8",
      // components/ e pages/ ficam fora: validados via Playwright E2E
      // (docs/playwright-e2e-standard.md), nao por teste unitario Vitest.
      include: ["src/api/**", "src/hooks/**", "src/lib/**", "src/context/**"],
      exclude: [
        "src/components/**",
        "src/pages/**",
        "src/App.tsx",
        "src/main.tsx",
        "src/vite-env.d.ts",
      ],
      // Gate de regressao: medido 27/07/2026 em 46.8% linhas / 92.2% branches /
      // 71.9% funcoes (api/hooks/lib/context). Piso abaixo do medido para dar
      // margem, mesmo criterio usado no gate de cobertura do Orchestrator.
      // O gate cumpriu o papel: a cobertura havia caido de 43.6% (05/07) para
      // 38.3% com a entrada de hooks sem teste, e reprovou o CI ate serem
      // cobertos usePolling e useDebouncedValue.
      thresholds: {
        lines: 40,
        statements: 40,
        functions: 65,
        branches: 85,
      },
    },
  },
});
