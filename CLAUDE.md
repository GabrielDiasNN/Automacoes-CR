# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Herda de: `AGENTS.md`. Em caso de conflito, `AGENTS.md` prevalece salvo onde este arquivo for mais restritivo.

## Comandos Essenciais

### Orquestrador (Python/FastAPI)
```powershell
# Iniciar API + worker
pwsh -File Infrastructure\Start-Orchestrator.ps1

# Recuperar após falha
pwsh -File Infrastructure\Recover-Orchestrator.ps1

# Dirigir o app real (health, login no dashboard, screenshot, rotas /api/*).
# Cheque `health` ANTES de reiniciar: esta máquina roda o Orchestrator em produção.
# Contrato completo em .claude/skills/run-orchestrator/SKILL.md
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py smoke

# O virtualenv do projeto fica na RAIZ do repositório (.venv\), não dentro de Orchestrator/.
# Todo comando Python abaixo deve usá-lo — o Python do sistema tem versões defasadas
# do lock e não é o ambiente do projeto.

# Aplicar migrações de schema
cd Orchestrator && ..\.venv\Scripts\alembic upgrade head

# Rodar a suíte padrão (exclui e2e via addopts do pytest.ini, como o CI)
# Depende de `pythonpath = .` no pytest.ini: sem essa linha o conftest não acha `app`.
cd Orchestrator && ..\.venv\Scripts\pytest

# Rodar testes por marcador (unitario | integracao | e2e)
cd Orchestrator && ..\.venv\Scripts\pytest -m integracao -v

# Lint Python (black, isort, bandit, mypy, pylint) — ferramentas via requirements-dev.txt
.venv\Scripts\python -m black --check Orchestrator .claude/skills
.venv\Scripts\python -m isort --check-only Orchestrator .claude/skills
.venv\Scripts\python -m bandit -r Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" .claude/skills -ll
# mypy + pylint: usar o script de governança (aplica flags corretas por arquivo)
pwsh -File Tools\Test-PythonGovernance.ps1 -RootPath .

# Recompilar dependências pinadas (pip-tools)
.venv\Scripts\pip-compile requirements.in -o requirements.txt

# Sincronizar o ambiente com o lock (após pull que altere requirements*.txt)
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-test.txt -r requirements-dev.txt

# Lint que roda no CI (bloqueante) — reproduzir localmente antes do push
.venv\Scripts\python -m ruff check Orchestrator/app Orchestrator/worker.py lib/python "Produção Beneficimento/src" .claude/skills
```

### Governança, quality gate e scaffolding
Rodados pelas skills do projeto: `/quality-gate` (ValidarAutomacoes completo), `/preflight` (checklist pré-PR: encoding, skills governance, lint Python) e `/new-automation` (scaffolding com manifesto válido).

## Arquitetura

### Visão Geral
Monorepo com três camadas principais:

1. **Orchestrator** (`Orchestrator/`) — FastAPI v5 + APScheduler + SQLite WAL. Motor de execução central.
2. **Dashboard** (`Dashboard/`) — SPA React + TypeScript + Vite (fontes em `Dashboard/src/`, build em `Dashboard/dist/`) servido pelo próprio FastAPI via `StaticFiles` com fallback SPA para rotas client-side. Roda em `http://127.0.0.1:8000/dashboard/`.
3. **Automações de domínio** — diretórios independentes. As seis automações registradas com manifesto (`Receitas Bloqueadas/` RB-01, `Montagem de Terceirizados/` MT-02, `Receitas Emitidas/` RE-03, `OBs Paradas Fase/` OBP-04, `OBs Fluxo Sem Tingimento/` OFST-06, `OBs Restricao Branco/` ORB-07) usam `run.ps1` como entrypoint. `Produção Beneficimento/` é orientada a snapshot (sem `run.ps1`, ver abaixo). Criticidade, SLA e cadência canônicas: `docs/automation-criticality-map.md`.

Detalhes de módulo carregados sob demanda: `Orchestrator/CLAUDE.md` e `Produção Beneficimento/CLAUDE.md`.

### Biblioteca compartilhada Python (`lib/python/`)
- `oracle_extract.py` — núcleo compartilhado de extração Oracle: `resolve_oracle_credentials`, `init_thick_mode`, `fetch_all` (lotes), `serialize_rows` (datetime→isoformat, strip), `compute_hash`, `read_last_hash`, `write_state_tmp`. **Todos os 6 scripts de extração de domínio (`Receitas Emitidas/`, `Receitas Bloqueadas/`, `Montagem de Terceirizados/`, `OBs Paradas Fase/`, `OBs Fluxo Sem Tingimento/`, `OBs Restricao Branco/`) usam este módulo** — não duplicar o padrão fetch/serialize/hash em novos scripts. Para DSN fixo (ignorar `.env`), passe `force_dsn="dbprd"` em `resolve_oracle_credentials`.
- `oracle_client.py` — `init_oracle_thick_mode` (ativa Thick Mode do oracledb).
- `oracle_retry.py` — `make_oracle_retry()` (pybreaker + stamina) e `CircuitBreakerError`.

### Biblioteca compartilhada PowerShell (`lib/`)
- `Lib-OrchestratorRuntime.psm1` — fonte única para scripts de Infrastructure: `Get-OrchestratorRuntimeVersion` (lê `ORCHESTRATOR_VERSION` de `constants.py`), `Get-OrchestratorEnvValue` (parser de `.env`), `Stop-OrchestratorProcesses` (usa `Get-CimInstance Win32_Process` — **nunca** `Get-Process`, que não expõe `CommandLine` no PS 5.1). Todo script de `Infrastructure/` que precise de versão de runtime, leitura de `.env` ou encerramento de processos deve consumi-lo em vez de reimplementar (`Install-OrchestratorTask.ps1` é exceção legítima: só registra a tarefa agendada e não usa nenhuma dessas capacidades).
- `Lib-Config.psm1` — leitura de `.env` para scripts de automação de domínio.

### Infrastructure (`Infrastructure/`)
Todo script de ciclo de vida do Orchestrator importa `Lib-OrchestratorRuntime.psm1`.

### Skills canônicas (`.github/skills/`)
Sete skills governam decisões de implementação. `.gemini/skills/` é apenas mirror. Edite sempre a fonte canônica.

## Regras Operacionais Críticas

### Encoding
Fonte única (não duplicar aqui): `AGENTS.md § Regras de Encoding`. Aplicado mecanicamente pelo hook `Assert-FileEncoding.ps1` a cada `Edit`/`Write` e por `Tools/Test-SourceEncoding.ps1` no pre-commit.

### Caminhos
- **Nunca use caminhos absolutos** em scripts PowerShell. Use `.\` ou `$PSScriptRoot`.
- Python: paths relativos à raiz do projeto ou derivados de `.env`.

### Banco de dados
- Todas as sessões SQLAlchemy fora do contexto FastAPI usam `session_scope` (não `SessionLocal()` diretamente).
- Migrações de schema são feitas exclusivamente via Alembic (`upgrade head` no startup).
- WAL checkpoint periódico usa modo `PASSIVE` para não bloquear writers.

### Zero-Trust
- Nenhuma credencial hardcoded. Tudo via `.env` (lido por `lib/Lib-Config.psm1` em PowerShell, `python-dotenv` em Python).
- Dashboard solicita API Key via prompt; persiste em `sessionStorage` (não sobrevive ao fechamento da aba — mais restritivo que `localStorage`, e há teste dedicado proibindo o uso deste último).

### Commits e Documentação Viva
- Idioma dos commits e regra do `CHANGELOG.md`: `AGENTS.md § Idioma e Comunicação` e `§ Colaboração com Documentação AI-Native`.
- Atualizar `docs/ai-native-context-monitor.md` quando a mudança alterar estado que futuros agentes precisam conhecer para decidir corretamente.

### Validação E2E
- Quando o Playwright é obrigatório e como validar: `AGENTS.md § Validação`. Padrão completo (critérios, evidência mínima): `docs/playwright-e2e-standard.md`.
- Registrar evidência com `Tools/Test-PlaywrightEvidence.ps1`.
- Para validação visual ad-hoc via navegador (fora do Playwright formal, ex.: conferir uma UI nova com dados reais), o login do dashboard exige a API Key — sempre lê-la de `ORCHESTRATOR_API_KEY` em `.env` (nunca peça a chave ao usuário nem a hardcode).

### Manifesto de automação
- Toda automação registrada no Orchestrator deve ter `automation.manifest.json` na sua pasta.
- `POST /api/automations/preflight` valida manifesto, docs obrigatórias e smoke tests antes de `create/update`. Desde 31/07/2026 o manifesto AUSENTE gera `incident` e **bloqueia** o `create/update`: antes gerava `attention`, e como `is_valid = status != "incident"`, não ter manifesto era a forma mais fácil de escapar de toda a governança (os demais checks só rodam quando o arquivo existe). O caminho canônico não é afetado — `Tools/New-Automation.ps1` sempre gera o manifesto a partir de `_Template`.
- Fixtures de teste que cadastram automações sintéticas recebem o manifesto automaticamente pelo wrapper `com_manifesto` do `client` (`Orchestrator/tests/conftest.py`); ele nunca sobrescreve um manifesto que o próprio teste criou. Para testar o bloqueio, use a fixture `sem_governanca_automatica`.

### CI (GitHub Actions — `.github/workflows/governanca.yml`)
Pipeline único, roda em push para `main`/`escalar/**` e PRs. Gates bloqueantes, cobertura de cada diretório e o histórico das decisões: skill `ci-gates` (`.claude/skills/ci-gates/SKILL.md`). O mypy bloqueante é o do pre-commit hook (`Test-PythonGovernance.ps1`), não o do CI.

## Contratos de Governança (Pre-Commit Hook)

O hook executa `ValidarAutomacoes.ps1 -OnlyGovernance` a cada commit (15 validações: zero-trust, SQL, mypy/pylint, PowerShell, encoding, JSON, Playwright, manifesto, arquitetura, datas, semântica, Node, schema de evento de log). Regras detalhadas (limites exatos de mypy/pylint, formato de manifesto, contratos PowerShell, snippets corretos/errados) estão em **[docs/governance-contracts.md](docs/governance-contracts.md)** — consulte antes de escrever código Python/PowerShell novo ou editar `automation.manifest.json`.

## Princípios Comportamentais

**1. Pensar Antes de Executar** — Declare assunções explicitamente. Se incerto, pergunte. Se existirem múltiplas interpretações, apresente-as — não escolha silenciosamente.

**2. Simplicidade Primeiro** — Mínimo de código que resolve o problema. Sem features além do pedido, sem abstrações para uso único.

**3. Mudanças Cirúrgicas** — Toque apenas o necessário. Não "melhore" código adjacente. Cada linha alterada deve ser rastreável ao pedido.

**4. Execução Orientada a Metas** — Transforme tarefas em metas verificáveis. Para múltiplos passos, declare plano e critérios de sucesso antes de implementar.
