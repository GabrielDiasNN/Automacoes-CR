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
- **Terminal state:** em progresso
- **Melhor commit conhecido da onda:** (nenhum ainda — baseline `c1c707d`)
- **Iteração:** 1

## Histórico por onda

### Onda 1 — Gates e fundação de build
- **Status:** em progresso
- **Critério de pronto:** lint verde com `no-floating-promises`/`no-misused-promises`/`await-thenable` em `error`; typecheck verde com `noUncheckedIndexedAccess`+`exactOptionalPropertyTypes`; chunk `index` < 70 KB gzip com `uplot` em chunk próprio; 4 screenshots sem regenerar baseline
- **Ações tentadas:** —
- **Gaps:** —

### Ondas 2–6
- Não iniciadas. Escopo em `.claude/skills/loop-agentico` / prompt do `/loop-agentico`.

## Log de turnos

| Turno | Onda | Ação | Observação (saída real) | Resultado |
|---|---|---|---|---|
| 1 | 1 | Setup do estado + investigação inicial | `git rev-list main...origin/main` = `0 0`; sem `docs/progress.md` prévio | ok |
