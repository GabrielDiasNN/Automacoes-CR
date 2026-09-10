---
name: html-css-enterprise-standard
description: Use when changing the React dashboard SPA, the legacy HTML dashboard template, or enterprise HTML reports that must stay free of business logic and reuse the repository's shared frontend assets.
---

## Purpose
Definir o contrato visual do hub, a SPA React do dashboard e o template HTML legado, mantendo regra de negócio fora da camada de apresentação, reúso dos assets compartilhados de `lib/assets/` e aderência aos validadores de template e de frontend.

## When to Use
- Ao alterar fontes da SPA em `Dashboard/src/` (componentes, contexts, estilos, funções de renderização).
- Ao mexer no template legado `.github/templates/dashboard-modern.html` ou em relatório HTML gerado por automação.
- Ao editar CSS, design tokens em `:root`, tema claro/escuro ou responsividade de tela servida pelo hub.
- Ao tocar `Dashboard/src/api/client.ts`, persistência de preferência de UI ou o fluxo de API Key do dashboard.
- Ao reutilizar ou adicionar asset em `lib/assets/` (fontes, ApexCharts, Lucide).

## Do Not Use When
- Para cálculo, filtro, agregação ou qualquer regra de negócio que monta o JSON de entrada: use a skill `python-enterprise-standard`.
- Para contrato de execução, propagação de ExecId ou arquivos de estado que alimentam a UI: use a skill `enterprise-orchestration-contract`.
- Para política de segredo, log, severidade ou encoding: use a skill `automation-runtime-safety`.
- Para canal de comunicação headless (WhatsApp) ou bootstrap `.bat`: use a skill `nodejs-communications`.
- Para sintaxe PowerShell, módulos `.psm1` ou monitoramento central: use a skill `powershell-automation-monitor`.

## Related Skills
- `enterprise-orchestration-contract` cobre os dados produzidos pelo fluxo corporativo e pelos arquivos de estado que a UI consome.
- `automation-runtime-safety` cobre o caso em que a tela expõe log, mensagem de erro ou texto sensível.
- `nodejs-communications` cobre o HTML que faz parte de um canal de comunicação e não do dashboard.
- `ai-native-development-standard` cobre a atualização de documentação viva quando a experiência final muda de forma estrutural.

## Non-Negotiable Rules
- Regra de negócio fica fora do template e dos componentes de apresentação; o HTML e o JSX recebem dados prontos para renderizar, e cálculo novo vai para o Python que monta o JSON.
- A UI ativa do operador é a SPA React + TypeScript + Vite; mudança de UI acontece em `Dashboard/src/`, não no template legado.
- `.github/templates/dashboard-modern.html` é legado canônico mantido de propósito: preserve os placeholders `__DASHBOARD_JSON__` e `__REFRESH_SECONDS__` e as funções de renderização exigidas por `Tools/Test-DashboardTemplate.ps1`, sem remover nem renomear.
- Reutilize os assets reais de `lib/assets/` antes de embutir biblioteca ou fonte nova: `css/fonts.css`, `js/apexcharts.min.js`, `js/lucide.min.js` e as fontes `fonts/plus-jakarta-sans-{300,400,500,600,700}.woff2` e `fonts/jetbrains-mono-{400,500}.woff2`.
- A credencial do dashboard (API Key) vive só em `sessionStorage`; o teste `useApiKey.test.ts` proíbe `localStorage` para a chave. O veto é sobre a credencial: preferência de UI benigna, como densidade de tabela em `Dashboard/src/context/TableDensityContext.tsx`, usa `localStorage` legitimamente e não deve ser migrada para `sessionStorage`.
- Não reintroduza referência conceitual a VBA; o projeto é 100% nativo em Python, PowerShell e Node.
- Encoding de `.html`, `.css`, `.ts` e `.tsx`: contrato em `AGENTS.md § Regras de Encoding`, não repetido aqui.

## Repo-Specific Constraints
- `Dashboard/dist/` é gitignored: sem `npm run build --prefix Dashboard` a rota `http://127.0.0.1:8000/dashboard/` fica sem bundle, porque o FastAPI serve `dist/` via `StaticFiles` com fallback SPA.
- O job `frontend` do CI é bloqueante quando o diff toca `.js`, `.ts` ou `.tsx`: ele roda `npm ci`, `npm run lint`, `npm run test:coverage` (Vitest com gate de cobertura) e `npm run build` com `working-directory: Dashboard`. Localmente o equivalente é a forma `--prefix Dashboard` (ou rodar a partir da pasta), documentada em `Dashboard/CLAUDE.md`.
- `Dashboard/src/api/client.ts` lê a API Key no carregamento do módulo, não em `useEffect`; a API responde 403, não 401, sem o header `X-API-Key`.
- Toda a toolchain de front tem lockfile próprio em `Dashboard/`; rode os comandos com `--prefix Dashboard` ou a partir dessa pasta, nunca pelo `package.json` da raiz.
- Padrão completo e evidência mínima da validação E2E do dashboard: `docs/playwright-e2e-standard.md`.

## Validation
- Para mudança na SPA: `npm run lint --prefix Dashboard`, `npm run test:coverage --prefix Dashboard` e `npm run build --prefix Dashboard` antes do E2E.
- Para mudança no template legado: `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-DashboardTemplate.ps1 -BasePath .`.
- Para mudança em padrão global de UI: `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance`.
- E2E Playwright por último, na tela servida em `http://127.0.0.1:8000/dashboard/`, cobrindo no mínimo navegação entre módulos, listagem e refresh de execuções, abertura de logs e ausência de erro de console; detalhes em `docs/playwright-e2e-standard.md`.
- Registre a evidência com `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PlaywrightEvidence.ps1`.

## Troubleshooting
- Tela em branco ou versão antiga em `/dashboard/`: bundle velho ou ausente em `Dashboard/dist/`; rode `npm run build --prefix Dashboard` (a API não precisa reiniciar, o `StaticFiles` lê do disco a cada request).
- `Tools/Test-DashboardTemplate.ps1` acusa função ausente: compare `.github/templates/dashboard-modern.html` com a lista de placeholders e funções obrigatórias no próprio script.
- Gate de login aparece onde não devia em teste: a API Key precisa estar em `sessionStorage` antes do bundle carregar, porque `Dashboard/src/api/client.ts` a lê no import do módulo.
- Regressão de responsividade: investigue primeiro wrappers de tabela com `overflow-x`, media queries e tokens em `:root` antes da lógica de componente.
- HTML recebendo lógica demais: mova o cálculo para o Python que monta o JSON de entrada (skill `python-enterprise-standard`).
- Necessidade de asset novo: confirme antes se `lib/assets/` já cobre o requisito (fonte, ApexCharts, Lucide) para não duplicar biblioteca.

## Pre-Delivery Checklist
- Nenhuma regra de negócio entrou no HTML ou no JSX; a camada recebe dados prontos.
- Assets reaproveitados de `lib/assets/` quando já existia alternativa suficiente.
- Template legado continua passando em `Tools/Test-DashboardTemplate.ps1` com placeholders e funções intactos.
- Job `frontend` (lint, test:coverage e build) verde para mudança que toca `.js`, `.ts` ou `.tsx`.
- API Key só em `sessionStorage`; preferência de UI benigna em `localStorage` preservada.
- E2E Playwright executado por último e evidência registrada (`docs/playwright-e2e-standard.md`).
- Sem menção a VBA; encoding conforme `AGENTS.md § Regras de Encoding`.
