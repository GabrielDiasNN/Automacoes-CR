import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/__tests__/**/*.test.{ts,tsx}"],
    // Sem isso (achado nº 34, Onda 5), @testing-library/jest-dom e
    // @testing-library/react's cleanup() automático nunca eram ativados —
    // duas devDeps instaladas e nunca usadas, e o DOM de um teste vazava
    // para o próximo em qualquer arquivo que usasse renderHook/render sem
    // seu próprio afterEach manual (achado real: useAction.test.ts precisou
    // de um antes desta config existir).
    setupFiles: ["src/__tests__/setup.ts"],
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
      // RECALIBRADO em 02/09/2026 (Onda 5 da revisao geral do frontend): a
      // cobertura medida subiu bem acima do piso de 04/08 (novos testes de
      // useAction, useWebSocket, contrato de API com MSW), deixando o gate
      // sem efeito pratico — nao pegaria regressao nenhuma antes de cair
      // ~14pp abaixo do real. Medido 02/09/2026 com Vitest 4.1.10: 67.2%
      // linhas / 66.8% statements / 68.8% branches / 53.2% funcoes.
      // `useAsyncResource.ts`, `useFocusTrap.ts`, `useMediaQuery.ts` e
      // `useDiagnostics.ts` estao em 0% (verificado nao ser regressao desta
      // rodada exceto useAsyncResource, que e novo e foi validado por
      // Playwright real em vez de teste unitario — ver commit da Onda 4).
      thresholds: {
        lines: 60,
        statements: 59,
        functions: 46,
        branches: 61,
      },
    },
  },
});
