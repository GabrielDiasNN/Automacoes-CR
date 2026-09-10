---
name: preflight
description: Checklist completo pré-PR — encoding, skills governance, lint Python (ruff/black/isort/bandit) e governança Python (mypy/pylint), reproduzindo o escopo bloqueante do CI. Reporte cada etapa e bloqueie se qualquer uma falhar.
disable-model-invocation: true
---

Execute as etapas abaixo **em ordem**, sempre com o Python do projeto (`.venv\Scripts\python` —
o Python do sistema tem versões defasadas do lock e produz falso verde). Relate cada resultado
com ✓ (passou) ou ✗ (falhou + mensagem de erro resumida).

**Etapa 1 — Encoding dos fontes**
```
pwsh -File Tools\Test-SourceEncoding.ps1 -RootPath .
```

**Etapa 2 — Skills governance (canônico vs mirror)**
```
pwsh -File Tools\Test-SkillsGovernance.ps1 -BasePath .
```

**Etapa 3 — Lint bloqueante do CI (ruff)** — escopo idêntico a `.github/workflows/governanca.yml`
(mantido em sincronia pela skill `ci-gates`; se divergir, `ci-gates` é a fonte):
```
.venv\Scripts\python -m ruff check Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" "OBs Restricao Branco" "Receitas Bloqueadas" "Montagem de Terceirizados" "Receitas Emitidas" "OBs Paradas Fase" "OBs Fluxo Sem Tingimento" .claude/skills Tools docs/templates
```

**Etapa 4 — Segurança estática (bandit)** — mesmo escopo do ruff, `-ll`:
```
.venv\Scripts\python -m bandit -r Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" "OBs Restricao Branco" "Receitas Bloqueadas" "Montagem de Terceirizados" "Receitas Emitidas" "OBs Paradas Fase" "OBs Fluxo Sem Tingimento" .claude/skills Tools docs/templates -ll
```

**Etapa 5 — Formatação e imports (black + isort)** — o CI roda só sobre os `.py` alterados no PR
(`@changedFiles`), não sobre um escopo fixo. Reproduza com o diff do branch:
```
pwsh -Command "$py = git diff --name-only --diff-filter=d main...HEAD -- '*.py'; if ($py) { .venv\Scripts\python -m black --check $py; .venv\Scripts\python -m isort --check-only $py } else { 'nenhum .py alterado' }"
```

**Etapa 6 — Governança Python (mypy `--strict` + pylint)** — este é o mypy **bloqueante** do
pre-commit hook; o CI não roda mypy. Limites exatos em `docs/governance-contracts.md`:
```
pwsh -File Tools\Test-PythonGovernance.ps1 -RootPath .
```

Ao final, mostre um resumo: quantas etapas passaram e quais falharam, com o que corrigir antes do PR.

**O que este preflight NÃO cobre** (rode à parte quando o diff tocar essas áreas):
- `pytest` + gate de cobertura (`--cov-fail-under=84`, `diff-cover --fail-under=85`) — use `/run-tests`
- E2E Playwright (`-m e2e`) e evidência (`Tools/Test-PlaywrightEvidence.ps1`)
- Gitleaks, Pester (`lib/tests`), lint+build do Dashboard
- Governança agregada completa (`/quality-gate`) — inclui SQL, PowerShell, arquitetura, manifesto, schema de log

Passar no preflight **não** garante CI verde: ele cobre os gates de lint/encoding/governança Python, não a suíte inteira.
