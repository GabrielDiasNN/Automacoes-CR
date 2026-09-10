---
name: python-enterprise-standard
description: Use when writing or reviewing Python in this repo (Orchestrator FastAPI/SQLAlchemy, the six Oracle extractors, the Beneficiamento snapshot pipeline) and the repo's strict-typing, lint, coverage and encoding gates must pass.
---

## Purpose
Fixar as decisões de implementação Python do monorepo: qual interpretador rodar, onde a extração Oracle é centralizada, como as sessões de banco são abertas, qual mypy é bloqueante e quais gates de lint e cobertura o CI exige. O objetivo é que a mudança passe no pre-commit hook e no `governanca.yml` sem retrabalho.

## When to Use
- Ao editar módulos em `Orchestrator/app/` (routers, `services/`, `models.py`, schemas Pydantic) ou `Orchestrator/worker.py`.
- Ao mexer em qualquer um dos 6 extratores Oracle: `Receitas Bloqueadas/processar_receitas.py`, `Montagem de Terceirizados/extract_oracle.py`, `Receitas Emitidas/extract_oracle.py`, `OBs Paradas Fase/extract_obs.py`, `OBs Fluxo Sem Tingimento/extract_ofst.py`, `OBs Restricao Branco/extract_orb.py`.
- Ao alterar o pipeline de snapshot em `Produção Beneficimento/src/beneficiamento/` (`runner.py`, `snapshot_store.py`, SQL em `contracts/_queries*.py`).
- Ao criar migração Alembic em `Orchestrator/migrations/versions/` ou escrever/rever testes `pytest`.

## Do Not Use When
- Para decidir topologia de execução, propagação de `ExecId` ou ownership de estado entre PowerShell e Python: use a skill enterprise-orchestration-contract.
- Para política de segredo, severidade de log, degradação segura ou classificação recuperável versus terminal: use a skill automation-runtime-safety.
- Para sintaxe, verbos e modularização de scripts PowerShell que chamam esses `.py`: use a skill powershell-automation-monitor.
- Para alinhar `CHANGELOG.md`, `docs/ai-native-context-monitor.md` e demais documentos vivos após uma mudança estrutural do backend: use a skill ai-native-development-standard.

## Related Skills
- `enterprise-orchestration-contract` para o papel do código Python dentro do fluxo de execuções e o contrato de estado.
- `automation-runtime-safety` para Zero Trust, logging estruturado e as regras de encoding que o Python herda.
- `ai-native-development-standard` para atualizar documentação viva quando o backend muda de contrato.
- `powershell-automation-monitor` quando o mesmo PR toca o `run.ps1` que dispara o extrator.

## Non-Negotiable Rules
- O virtualenv do projeto fica na **raiz do repositório** (`.venv\` no topo, não em `Orchestrator/`). Todo comando roda por `.venv\Scripts\python` / `.venv\Scripts\pytest`; o Python do sistema tem versões defasadas do lock e produz falso verde. Nunca invoque `python`/`pytest` puro.
- Extração Oracle nova reutiliza `lib/python/oracle_extract.py` (`resolve_oracle_credentials`, `init_thick_mode`, `fetch_all`, `serialize_rows`, `compute_hash`, `read_last_hash`, `write_state_tmp`) — não reimplemente o ciclo fetch/serialize/hash. Para DSN fixo, passe `force_dsn="dbprd"` em `resolve_oracle_credentials`. Retry e circuit breaker vêm de `lib/python/oracle_retry.py` (`make_oracle_retry()` sobre pybreaker+stamina, `CircuitBreakerError`); Thick Mode isolado também em `lib/python/oracle_client.py` (`init_oracle_thick_mode`).
- Sessão SQLAlchemy fora do contexto de request do FastAPI usa `session_scope`, nunca `SessionLocal()` direto — reprovado por `Tools/Test-ArchitectureStandard.ps1`.
- Acesso a Oracle vive apenas no `oracle.py` de cada domínio (Beneficiamento: `Produção Beneficimento/src/beneficiamento/oracle.py`); router ou `service` que importa `oracledb` reprova na revisão arquitetural.
- Schema do banco do Orchestrator muda só por Alembic. Como `render_as_batch=True`, toda operação de coluna passa por `op.batch_alter_table` (o subagente `alembic-reviewer` verifica).
- O mypy bloqueante é o do pre-commit (`Tools/Test-PythonGovernance.ps1`), não o do CI. Passar o `governanca.yml` não substitui rodar o hook antes do commit.
- Os limites numéricos exatos de mypy e pylint que reprovam estão em `docs/governance-contracts.md § Contrato Python — mypy \`--strict\`` e `§ Contrato Python — pylint` — consulte antes de refatorar; não presuma os valores.

## Repo-Specific Constraints
- O hook invoca mypy com `--strict --explicit-package-bases --namespace-packages` e `MYPYPATH=Orchestrator;.;lib\python`. Módulo que importa `app` ou `oracle_extract` só tipa com esse MYPYPATH — reproduza pelo script, não chamando `mypy` cru.
- Lint Python bloqueante do CI = `ruff` + `bandit`; `black`/`isort` rodam só sobre os arquivos alterados do PR. O conjunto exato de diretórios cobertos muda com o tempo — pegue o escopo atual na skill `ci-gates`, não transcreva a lista aqui.
- Cobertura bloqueante: `--cov-fail-under=84` no total e `diff-cover --fail-under=85` nas linhas alteradas do PR. Código novo sem teste derruba o segundo mesmo com o primeiro folgado.
- Suíte padrão: `cd Orchestrator && ..\.venv\Scripts\pytest`. Marcadores `unitario | integracao | e2e | benchmark`; o `addopts` do `pytest.ini` exclui `e2e`. `pythonpath = .` em `Orchestrator/pytest.ini` é obrigatório, senão o `conftest` não acha `app`.
- `Produção Beneficimento/` não tem `run.ps1` — é orientada a snapshot. SQL fica isolado em `src/beneficiamento/contracts/_queries*.py`; não espalhe query solta pelos módulos de cálculo.
- Encoding de `.py`: contrato em `AGENTS.md § Regras de Encoding`, aplicado por `Assert-FileEncoding.ps1` a cada Edit/Write e por `Tools/Test-SourceEncoding.ps1` no pre-commit. Não repita o valor aqui.

## Validation
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PythonGovernance.ps1 -RootPath .` (mypy `--strict` + pylint — o gate que bloqueia o commit).
- `.venv\Scripts\python -m ruff check <escopo da skill ci-gates>` e `.venv\Scripts\python -m bandit -r <mesmo escopo> -ll` para reproduzir o CI localmente.
- `cd Orchestrator && ..\.venv\Scripts\pytest` para a suíte padrão; adicione `-m e2e` só quando o Playwright for exigido.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath .` para o gate de encoding (`AGENTS.md § Regras de Encoding`).

## Troubleshooting
- `ModuleNotFoundError: No module named 'app'` no pytest (exit 4, na importação do `conftest.py`): a suíte rodou fora de `Orchestrator/`, ou `pythonpath = .` sumiu de `Orchestrator/pytest.ini`.
- mypy verde no seu terminal mas o hook reprova: você rodou o mypy do CI ou `mypy` cru; use `Test-PythonGovernance.ps1`, que aplica `MYPYPATH` e as flags por arquivo.
- Migração recusada pelo `alembic-reviewer`: envolva o `op.add_column`/`op.drop_column`/`op.alter_column` em `op.batch_alter_table`.
- Script Oracle novo repetindo fetch/serialize/hash: troque pelas funções de `lib/python/oracle_extract.py`; para ignorar o `.env` e cravar o banco, `force_dsn="dbprd"`.
- `ruff`/`bandit` verde local e vermelho no CI: seu escopo local está mais estreito que o do pipeline; pegue a lista atual na skill `ci-gates`.
- `pytest` usando pacotes defasados: confirme que chamou `.venv\Scripts\pytest`, não o do sistema.

## Pre-Delivery Checklist
- `Test-PythonGovernance.ps1` verde (mypy `--strict` + pylint dentro dos limites de `docs/governance-contracts.md § Contrato Python — pylint`).
- `ruff` + `bandit` verdes sobre o escopo da skill `ci-gates`, não só sobre os arquivos que você alterou.
- Suíte `pytest` verde rodada de `Orchestrator/` com o interpretador do `.venv`.
- Nenhuma cópia nova de fetch/serialize/hash — `lib/python/oracle_extract.py` reutilizado; sessão fora do FastAPI via `session_scope`.
- Encoding conforme `AGENTS.md § Regras de Encoding` (verificado por `Tools/Test-SourceEncoding.ps1`).
