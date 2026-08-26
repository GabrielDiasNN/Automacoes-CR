---
name: ci-gates
description: Gates bloqueantes do pipeline de CI (.github/workflows/governanca.yml) e o histórico de por que cada cobertura foi adicionada. Use ao alterar o workflow do CI, ao investigar por que um job falhou, ao ajustar cobertura de lint/testes, ou ao decidir se um diretório novo precisa entrar em ruff/bandit/black/isort.
---

# Gates do CI

Pipeline único (`.github/workflows/governanca.yml`), roda em push para `main`/`escalar/**` e PRs.

## Gates bloqueantes

- **`lint-python`** — `ruff check Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" "OBs Restricao Branco" .claude/skills`, mais black/isort/bandit (mesmo escopo de diretórios).
- **`testes-python`** — pytest com `--cov-fail-under=84`, mais `diff-cover --fail-under=85` nas linhas alteradas do PR.
- **`testes-e2e`** — E2E Playwright.
- Gitleaks, Pester, lint+build do Dashboard e a governança agregada (`ValidarAutomacoes.ps1 -OnlyGovernance`).

O mypy bloqueante **não** é do CI: é o do pre-commit hook (`Test-PythonGovernance.ps1`).

## Histórico de cobertura

- **25/08/2026 — `OBs Restricao Branco` entrou em ruff e bandit.** ORB-07 é um novo domínio produtivo Oracle/WhatsApp e nasceu já coberto pelo gate bloqueante.
- **03/08/2026 — `.claude/skills` entrou em ruff e bandit.** `run-orchestrator/driver.py` é código executável que nasceu fora de todo gate, com um `# noqa: S310` que nenhuma ferramenta verificava e uma linha acima de 100 colunas. black/isort já o pegavam por serem aplicados ao diff, e mypy/pylint via `git ls-files "*.py"` do `Test-PythonGovernance.ps1`; ruff e bandit fecham a lacuna. `Tools/Test-SkillsGovernance.ps1` segue cobrindo só `.github/skills/` — ele valida forma de `SKILL.md` canônico vs. mirror, não Python.
- **31/07/2026 — `lib/python` e `Produção Beneficimento/src` entraram em ruff e bandit.** O primeiro é o núcleo compartilhado de extração Oracle, o segundo é o domínio que monta o SQL do histórico; ambos estavam fora de todo gate. Os 13 `# nosec B608` do Beneficiamento foram revisados um a um e quem sustenta a premissa é `tests/test_beneficiamento_sql_seguranca.py`.
- **01/07/2026** — o antigo `ci.yml` foi consolidado neste pipeline.
