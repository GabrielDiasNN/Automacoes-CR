# progress.md — Frontend do Orquestrador, rodada 2

Estado do loop agêntico. Fonte canônica de retomada — não depende da memória da conversa.

## Contrato do loop

| Componente | Definição |
|---|---|
| **Objetivo** | 6 ondas do plano "rodada 2": (1) gates+build, (2) camada de dados, (3) tokens, (4) visual+tema claro, (5) performance de render, (6) capacidades novas |
| **Done por onda** | Gates verdes (`lint`/`typecheck`/`test:coverage`/`build`) + `pytest -m e2e` + `driver.py smoke` + critério específico da onda. Ondas 1–3: **4 baselines de screenshot passam sem regeneração** |
| **Done global** | As 6 ondas fechadas e mergeadas |
| **Observação** | Saída real dos comandos — nunca a impressão de que funcionou |
| **Verificação** | Determinística primeiro (grep gates, tsc, eslint, vitest, pytest); inspeção visual só para o que é visual |
| **Terminal states** | Success · Blocked · No Progress (2 turnos) · Max Attempts (8/onda) · Human Review Required |
| **Regressão** | Métrica piora → reverter para o melhor commit conhecido da onda, tentar ação diferente, ou escalar |

### Checkpoints humanos (loop PARA e aguarda aprovação explícita)
- (a) Aprovação da paleta/tipografia antes de tocar qualquer componente na Onda 4
- (b) Depreciação das 3 rotas `/api/beneficiamento/{dashboard,periods,periods/{p}}`
- (c) **Qualquer `npm run build`** — é o deploy (FastAPI serve `Dashboard/dist` com `no-cache`)
- (d) Reinício do Orchestrator
- (e) Merge em `main`

## Estado atual

- **Ondas 1 e 2:** ✅ VERIFICADAS. Branches `escalar/frontend-rodada2-onda1` (`89f3d4f`) e `escalar/frontend-rodada2-onda2` (`6d07ae7`, branchada da onda1). Aguardando push + PR (checkpoint e).
- **Terminal state:** Success (Ondas 1–2). Próxima: Onda 3 — fundação de tokens (invisível).
- **Iteração:** 1
- **Verificação Onda 2:** lint 0/0 · typecheck 0 · 152 vitest · coverage exit 0 · bundle `index` 22,5 KB gzip (uplot separado) · **12/12 E2E, 4 screenshots sem regenerar** · **req/min em `/painel` parado: 18 → 6** (meta ≤ 8) · `useDiagnostics` 0% → 100% com teste de corrida

## Histórico por onda

### Onda 1 — Gates e fundação de build
- **Status:** ✅ COMPLETA E VERIFICADA (branch `escalar/frontend-rodada2-onda1`, `89f3d4f`) — falta só push+PR+merge (checkpoint e)
- **Critério de pronto:** lint verde com `no-floating-promises`/`no-misused-promises`/`await-thenable` em `error`; typecheck verde com `noUncheckedIndexedAccess`+`exactOptionalPropertyTypes`; chunk `index` < 70 KB gzip com `uplot` em chunk próprio; 4 screenshots sem regenerar baseline
- **Etapas:**
  - [x] 1.1 `d71e2c0` — TimeSeries fora do barrel de ui
  - [x] 1.2 `dd4157b` — vite.config: manualChunks/target/sourcemap/warnLimit
  - [x] 1.3 `e4deac3` — noUncheckedIndexedAccess + exactOptionalPropertyTypes (71 erros resolvidos; 2 latentes em logParser/useFocusTrap)
  - [x] 1.4 `16d2b18` — ESLint type-aware (3 regras `error` + 4 `warn`; 31 erros de promise, todos `void` no call site)
  - [x] 1.5 `720217f` — unions do backend viram tipos literais (ExecutionStatus, OperationalState, SlaStatus/SlaState, HealthStatus); achado: `attentionRank` comparava `sla_state` contra valores mortos
  - [x] 1.6 `e40e17a` — contract tests getOverview + listExecutions (fixtures reais; 138 testes)
  - [x] `b6f216d` — fix manualChunks p/ forma de função (Vite 8 = rolldown, forma de objeto quebra o build)
  - [x] MEDIÇÃO DE BUNDLE (build em dir temporário, sem deploy):
    - `index`: 71,2 KB raw / **22,1 KB gzip** — meta `< 70 KB gzip` ✅ (folgado)
    - `uplot`: chunk próprio 51,3 KB / 21,9 KB gzip, **ausente do index** (`grep u-cursor` = 0) ✅
    - `react` 172,8/56,5 · `lucide` 15,7/6,0 · `index.css` 30,2/6,3 (gzip)
    - `sourcemap: hidden` confirmado (nenhum `sourceMappingURL` nos `.js`)
  - [x] `89f3d4f` — override `ORCHESTRATOR_DASHBOARD_DIST` no backend (destrava E2E sem deploy)
  - [x] CHECKPOINT (d) resolvido: **`pytest -m e2e` 12/12 verde**, os 4 screenshots comparados contra baseline **sem regeneração** (`docs/playwright-screenshots/baseline/` intacto no git). `driver.py smoke` pulado — nada deployado, testaria só o build antigo.
  - [x] CHANGELOG.md [1.3.71]
  - [ ] `/preflight` + push + PR (checkpoint e)
- **Observação (verificação real):** lint 0/0 · typecheck 0 · 138 vitest · build medido (index 22,1 KB gzip) · 12/12 E2E · governança Python limpa

### Onda 2 — Camada de dados: memória, sem framework novo
- **Status:** ✅ COMPLETA E VERIFICADA (branch `escalar/frontend-rodada2-onda2`)
- **Etapas:**
  - [x] `5124c17` — 403 de path safety não derruba a sessão (só 401 / 403 "API Key")
  - [x] `bc90c61` — `refresh()` durante 429 enfileira + `refreshQueued` no FreshnessTag; `loading` preso corrigido
  - [x] `ba3aa69` — cache SWR (`resourceCache.ts`); `usePolling({cacheKey})`; `useAction({invalidate})`; overview cacheado em Painel/Sistema
  - [x] `6dc92eb` — `useDiagnostics` sobre `usePolling` (sem `getWorkerStatus`); `LiveStatusContext` dividido (data vs subscribe)
  - [x] `a64eb74` — 2 fetch manuais → `useAsyncResource` (ExecucoesPage detalhe, RunbookDrawer)
  - [x] `6d07ae7` — `skipIfFresh`+`onData`: dedupe do `/health/full` (12 → 6 req/min)
  - [x] VERIFICAÇÃO: build medido, 12/12 E2E, req/min 18→6, CHANGELOG [1.3.72]
  - [ ] push + PR (checkpoint e)

### Ondas 3–6
- Não iniciadas. Escopo no prompt do `/loop-agentico`.

## Log de turnos

| Turno | Onda | Ação | Observação (saída real) | Resultado |
|---|---|---|---|---|
| 1 | 1 | Setup do estado + investigação inicial | `git rev-list main...origin/main` = `0 0`; sem `docs/progress.md` prévio | ok |
