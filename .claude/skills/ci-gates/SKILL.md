---
name: ci-gates
description: Gates bloqueantes do pipeline de CI (.github/workflows/governanca.yml) e o histórico de por que cada cobertura foi adicionada. Use ao alterar o workflow do CI, ao investigar por que um job falhou, ao ajustar cobertura de lint/testes, ou ao decidir se um diretório novo precisa entrar em ruff/bandit/black/isort.
---

# Gates do CI

Pipeline único (`.github/workflows/governanca.yml`), roda em push para `main`/`escalar/**` e PRs.

## Gates bloqueantes

- **`lint-python`** — `ruff check Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" "OBs Restricao Branco" "Receitas Bloqueadas" "Montagem de Terceirizados" "Receitas Emitidas" "OBs Paradas Fase" "OBs Fluxo Sem Tingimento" .claude/skills`, mais black/isort/bandit (mesmo escopo de diretórios).
- **`testes-python`** — pytest com `--cov-fail-under=84`, mais `diff-cover --fail-under=85` nas linhas alteradas do PR.
- **`testes-e2e`** — E2E Playwright.
- Gitleaks, Pester, lint+build do Dashboard e a governança agregada (`ValidarAutomacoes.ps1 -OnlyGovernance`).

O mypy bloqueante **não** é do CI: é o do pre-commit hook (`Test-PythonGovernance.ps1`).

## Histórico de cobertura

- **26/08/2026 — as 5 automações de domínio mais antigas entraram em ruff e bandit.** `Receitas Bloqueadas` (RB-01), `Montagem de Terceirizados` (MT-02), `Receitas Emitidas` (RE-03), `OBs Paradas Fase` (OBP-04) e `OBs Fluxo Sem Tingimento` (OFST-06) nunca tinham entrado nesta lista — código de produção com cron ativo ficou sem lint/bandit bloqueante desde sempre. Achado em code review. 86 violações de ruff corrigidas antes da inclusão (estilo/modernização — `UP006`/`UP015`/`UP035`/`UP045`/`SIM102`/`SIM105`/`B007`/`C401`; nenhuma era bug funcional) e 1 finding de bandit (B324, MD5 em `validate_and_generate_html.py`, resolvido com `usedforsecurity=False` sem trocar algoritmo nem invalidar hashes já persistidos). Suíte completa dessas 5 automações (84 testes) rodada após as correções. **Cuidado ao rodar `ruff check --fix` em lote:** ele removeu 4 imports de `OBs Paradas Fase/generate_phase_cards.py` (`get_fase_config`, `_codigo_fase_key`, `_resolve_contato`, `_load_contatos_from_env`) que existem só para expor atributos que `Orchestrator/tests/test_obs_paradas_fase.py` acessa dinamicamente via `importlib` — o `# pylint: disable=unused-import` já presente não suprime o F401 do ruff. Corrigido com `# noqa: F401` no mesmo import.
- **25/08/2026 — `OBs Restricao Branco` entrou em ruff e bandit.** ORB-07 é um novo domínio produtivo Oracle/WhatsApp e nasceu já coberto pelo gate bloqueante.
- **03/08/2026 — `.claude/skills` entrou em ruff e bandit.** `run-orchestrator/driver.py` é código executável que nasceu fora de todo gate, com um `# noqa: S310` que nenhuma ferramenta verificava e uma linha acima de 100 colunas. black/isort já o pegavam por serem aplicados ao diff, e mypy/pylint via `git ls-files "*.py"` do `Test-PythonGovernance.ps1`; ruff e bandit fecham a lacuna. `Tools/Test-SkillsGovernance.ps1` segue cobrindo só `.github/skills/` — ele valida forma de `SKILL.md` canônico vs. mirror, não Python.
- **31/07/2026 — `lib/python` e `Produção Beneficimento/src` entraram em ruff e bandit.** O primeiro é o núcleo compartilhado de extração Oracle, o segundo é o domínio que monta o SQL do histórico; ambos estavam fora de todo gate. Os 13 `# nosec B608` do Beneficiamento foram revisados um a um e quem sustenta a premissa é `tests/test_beneficiamento_sql_seguranca.py`.
- **01/07/2026** — o antigo `ci.yml` foi consolidado neste pipeline.
