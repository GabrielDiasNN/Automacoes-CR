---
name: preflight
description: Checklist completo pré-PR — encoding, skills governance, lint Python (ruff/black/isort/bandit), governance Python. Reporte os resultados e bloqueie se qualquer etapa falhar.
disable-model-invocation: true
---

Execute as etapas abaixo **em ordem** e relate cada resultado com ✓ (passou) ou ✗ (falhou + mensagem de erro).

**Etapa 1 — Encoding dos fontes**
```
pwsh -File Tools\Test-SourceEncoding.ps1 -RootPath .
```

**Etapa 2 — Skills governance (canônico vs mirror)**
```
pwsh -File Tools\Test-SkillsGovernance.ps1 -BasePath .
```

**Etapa 3 — Lint bloqueante do CI (ruff)**
```
python -m ruff check Orchestrator/app Orchestrator/worker.py
```

**Etapa 4 — Formatação Python (black)**
```
python -m black --check Orchestrator
```

**Etapa 5 — Ordenação de imports (isort)**
```
python -m isort --check-only Orchestrator
```

**Etapa 6 — Segurança estática (bandit)**
```
python -m bandit -r Orchestrator/app Orchestrator/worker.py -ll
```

**Etapa 7 — Governança Python (mypy + pylint)**
```
pwsh -File Tools\Test-PythonGovernance.ps1 -RootPath .
```

Ao final, mostre um resumo: quantas etapas passaram e quais falharam.
Se qualquer etapa falhar, liste explicitamente o que precisa ser corrigido antes de abrir o PR.
