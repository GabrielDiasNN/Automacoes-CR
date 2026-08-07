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
via prompt na primeira carga, persistida em `sessionStorage` — não sobrevive
ao fechamento da aba; há teste dedicado proibindo o uso de `localStorage`).

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

## Estrutura de pastas

`src/pages/` e `src/components/` coexistem em quatro padrões, cada um com um
gatilho próprio — não é inconsistência acidental:

- **`components/ui/`** — design system genérico (`Button`, `Card`, `DataTable`,
  `Select`, ...). Qualquer componente reusado por 2+ páginas vive aqui.
- **`components/<feature>/`** (ex.: `components/beneficiamento/`) — quando uma
  página cresce a ponto de ter **múltiplos** subcomponentes exclusivos dela
  (aqui: `DetailDrawer`, `FilterBar`, `ProductAutocomplete`, `TingimentoPanel`,
  `Treemap` — 5 componentes só usados por `BeneficiamentoPage`), eles ganham
  pasta de feature própria em vez de inflar `pages/`.
- **`pages/<Page>.<Sufixo>.tsx`** (ex.: `ExecucoesPage.ExecDetailBody.tsx`) —
  quando só existe **um** bloco isolável de uma página (não uma feature
  inteira com vários arquivos), a extração é por sufixo de nome de arquivo
  dentro de `pages/`, não uma pasta nova.
- **`components/<Nome>.tsx` solto na raiz de `components/`** (`Shell`,
  `StatusBar`, `CommandPalette`, `ApiKeyGate`) — componentes de app-shell/layout
  usados **uma única vez**, no topo da árvore de rotas (`App.tsx`/`Shell.tsx`),
  compondo o layout de nível superior em vez do conteúdo de uma página
  específica. Não são genéricos o bastante para `ui/` (não são reusados por
  2+ páginas) nem exclusivos de uma feature (não há uma página "dona" deles),
  então ficam soltos na raiz em vez de em subpasta.
- **Sem subdivisão** (`AutomacoesPage`, `MonitorPage`, `PainelPage`,
  `SystemPage`) — o JSX cabe inteiro na própria página sem nenhum bloco grande
  o bastante para justificar extração.

Regra prática: extraia para pasta de feature ao passar de 1 subcomponente
exclusivo; extraia por sufixo de arquivo para um único bloco isolável;
componente de app-shell usado uma única vez no topo da árvore de rotas fica
solto na raiz de `components/`; não force extração antecipada em página que
ainda cabe inline.

## Design system

Identidade "Sala de Instrumentação" — industrial, grafite como base, cor com
significado semântico (ciano/âmbar/verde/vermelho para status). Tokens de
cor, tipografia (IBM Plex) e espaçamento em
[`src/styles/tokens.css`](src/styles/tokens.css). Acessibilidade WCAG AA
verificada (contraste de texto ≥ 4.5:1 documentado inline nos tokens).
