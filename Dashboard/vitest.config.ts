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
      // Gate de regressao: piso abaixo do medido para dar margem (~7pp), mesmo
      // criterio usado no gate de cobertura do Orchestrator. O gate ja cumpriu o
      // papel: a cobertura havia caido de 43.6% (05/07/2026) para 38.3% com a
      // entrada de hooks sem teste, e reprovou o CI ate serem cobertos
      // usePolling e useDebouncedValue.
      //
      // RECALIBRADO em 04/08/2026 na subida para Vitest 4 (NAO e afrouxamento
      // do gate: os testes sao os mesmos, 92 passando; o que mudou foi a
      // MEDICAO). Duas remocoes do Vitest 4 explicam os novos numeros:
      //   - `coverage.ignoreEmptyLines` removido -> linhas sem codigo de runtime
      //     saem do denominador, entao % de linhas SOBE (46.8% -> 60.6%);
      //   - `coverage.experimentalAstAwareRemapping` removido por virar o unico
      //     metodo (era opt-in) -> contagem de branch/funcao fica precisa, e os
      //     numeros antigos se revelam INFLADOS (branches 92.2% -> 67.5%,
      //     funcoes 71.9% -> 42.6%). A cobertura real sempre foi essa.
      // Medido 04/08/2026 com Vitest 4.1.10: 60.6% linhas / 60.2% statements /
      // 67.5% branches / 42.6% funcoes. `src/context/**` esta em 0% porque
      // nunca teve teste (verificado) — nao e regressao desta onda.
      thresholds: {
        lines: 53,
        statements: 53,
        functions: 35,
        branches: 60,
      },
    },
  },
});
