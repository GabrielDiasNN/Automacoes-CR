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

- **Onda em curso:** 1 — Gates e fundação de build
- **Terminal state:** Human Review Required — checkpoint (c) `npm run build` + (d) reinício/E2E
- **Melhor commit conhecido da onda:** `e40e17a` (6 etapas de código completas, gates verdes)
- **Iteração:** 1
- **Bloqueio:** medição de bundle exige build (= deploy); E2E dos 4 screenshots exige subir a instância de teste. Aguardando OK humano.

## Histórico por onda

### Onda 1 — Gates e fundação de build
- **Status:** em progresso — 4 de 6 etapas commitadas (branch `escalar/frontend-rodada2-onda1`)
- **Critério de pronto:** lint verde com `no-floating-promises`/`no-misused-promises`/`await-thenable` em `error`; typecheck verde com `noUncheckedIndexedAccess`+`exactOptionalPropertyTypes`; chunk `index` < 70 KB gzip com `uplot` em chunk próprio; 4 screenshots sem regenerar baseline
- **Etapas:**
  - [x] 1.1 `d71e2c0` — TimeSeries fora do barrel de ui
  - [x] 1.2 `dd4157b` — vite.config: manualChunks/target/sourcemap/warnLimit
  - [x] 1.3 `e4deac3` — noUncheckedIndexedAccess + exactOptionalPropertyTypes (71 erros resolvidos; 2 latentes em logParser/useFocusTrap)
  - [x] 1.4 `16d2b18` — ESLint type-aware (3 regras `error` + 4 `warn`; 31 erros de promise, todos `void` no call site)
  - [x] 1.5 `720217f` — unions do backend viram tipos literais (ExecutionStatus, OperationalState, SlaStatus/SlaState, HealthStatus); achado: `attentionRank` comparava `sla_state` contra valores mortos
  - [x] 1.6 `e40e17a` — contract tests getOverview + listExecutions (fixtures reais; 138 testes)
  - [ ] CHECKPOINT (c): `npm run build` para medir bundle
  - [ ] CHECKPOINT (d): `pytest -m e2e` (4 screenshots sem regenerar) + `driver.py smoke`
- **Observação (lint/typecheck/test):** lint 0 erros / 0 warnings, typecheck 0, 138 testes vitest verdes, coverage exit 0
- **Gaps:** medição de bundle e E2E pendentes de checkpoint humano

### Ondas 2–6
- Não iniciadas. Escopo em `.claude/skills/loop-agentico` / prompt do `/loop-agentico`.

## Log de turnos

| Turno | Onda | Ação | Observação (saída real) | Resultado |
|---|---|---|---|---|
| 1 | 1 | Setup do estado + investigação inicial | `git rev-list main...origin/main` = `0 0`; sem `docs/progress.md` prévio | ok |
