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
      // Gate de regressao: medido 05/07/2026 em 43.6% linhas / 90% branches /
      // 70% funcoes (api/hooks/lib/context). Piso abaixo do medido para dar
      // margem, mesmo criterio usado no gate de cobertura do Orchestrator.
      thresholds: {
        lines: 40,
        statements: 40,
        functions: 65,
        branches: 85,
      },
    },
  },
});
