# Dashboard — Sala de Instrumentação

SPA React + TypeScript + Vite do Hub de Automações. Consome a API do
Orchestrator e é servido por ele via `StaticFiles` com fallback SPA
(`http://127.0.0.1:8000/dashboard/`). Ver `../CLAUDE.md` para a arquitetura
geral do monorepo.

## Rodar em desenvolvimento

```powershell
npm ci
npm run dev
```

Sobe em `http://localhost:5173`. Requer a API Key do Orchestrator (solicitada
via prompt na primeira carga, persistida em `localStorage`).

## Build de produção

```powershell
npm run build
```

Roda `tsc` (type-check completo) seguido de `vite build`, gerando `dist/`
(servido pelo Orchestrator em produção).

## Testes

```powershell
npm test              # Vitest (roda uma vez)
npm run test:watch    # Vitest em modo watch
npm run test:coverage # Vitest com gate de cobertura (o mesmo do CI)
npm run lint           # ESLint (src/**/*.ts,tsx)
npm run typecheck      # tsc --noEmit
```

**Escopo do gate de cobertura Vitest** (`vitest.config.ts`): cobre apenas
`src/api/`, `src/hooks/`, `src/lib/` e `src/context/` — a lógica que faz
sentido testar isoladamente. `src/components/` e `src/pages/` ficam
deliberadamente fora: são validados via Playwright E2E contra o Dashboard
rodando de verdade (ver `../docs/playwright-e2e-standard.md`), que é a
validação final obrigatória para qualquer mudança em `Dashboard/src/`.

## Design system

Identidade "Sala de Instrumentação" — industrial, grafite como base, cor com
significado semântico (ciano/âmbar/verde/vermelho para status). Tokens de
cor, tipografia (IBM Plex) e espaçamento em
[`src/styles/tokens.css`](src/styles/tokens.css). Acessibilidade WCAG AA
verificada (contraste de texto ≥ 4.5:1 documentado inline nos tokens).
