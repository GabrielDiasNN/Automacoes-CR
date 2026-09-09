# Regra de Workspace: Dashboard (Frontend SPA)

Aplica-se ao desenvolvimento, manutenção e testes na pasta `Dashboard/`.

## Toolchain e Comandos

O Dashboard possui toolchain próprio em `Dashboard/` (lockfile dedicado, ESLint, Vitest e Vite). Todo comando deve ser executado a partir da raiz com `--prefix Dashboard` ou diretamente dentro da pasta:

- Instalar dependências pelo lockfile:
  `npm ci --prefix Dashboard`
- Linting (ESLint):
  `npm run lint --prefix Dashboard`
- Testes unitários com cobertura (Vitest):
  `npm run test:coverage --prefix Dashboard`
- Build de produção (tsc + Vite):
  `npm run build --prefix Dashboard`
  *O build gera `Dashboard/dist/`, que é servido como arquivos estáticos pelo FastAPI.*
- Teste unitário pontual:
  `npm run test --prefix Dashboard -- src/components/Exemplo.test.tsx -t "nome do teste"`

## Segurança e Zero-Trust

- **API Key**: O Dashboard solicita a chave do Orchestrator via prompt e a armazena exclusivamente em `sessionStorage` (não sobrevive ao fechamento da aba).
- **Veto a credenciais em `localStorage`**: É estritamente proibido gravar credenciais ou tokens em `localStorage`.
- **Preferências de UI**: A persistência de preferências benignas de interface (ex.: densidade de tabela em `TableDensityContext.tsx`) em `localStorage` é legítima e permitida. Não altere para `sessionStorage`.

## Validação E2E com Playwright

- Qualquer alteração em componentes, templates, estado de UI ou contratos de API consumidos pelo front exige validação final E2E com Playwright.
- O build (`npm run build --prefix Dashboard`) deve ser executado antes do teste E2E para que o FastAPI sirva os assets compilados atualizados.
- Padrão de execução: `cd Orchestrator && ..\.venv\Scripts\pytest -m e2e -v` ou via driver de orquestração.
