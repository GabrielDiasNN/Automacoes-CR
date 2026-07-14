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

# Aplicar migrações de schema
cd Orchestrator && .venv\Scripts\alembic upgrade head

# Rodar todos os testes
cd Orchestrator && .venv\Scripts\pytest

# Rodar teste único
cd Orchestrator && .venv\Scripts\pytest tests/test_foo.py::test_bar -v

# Rodar testes por marcador (unitario | integracao | e2e)
cd Orchestrator && .venv\Scripts\pytest -m integracao -v

# Lint Python (black, isort, bandit, mypy, pylint) — ferramentas via requirements-dev.txt
python -m black --check Orchestrator
python -m isort --check-only Orchestrator
python -m bandit -r Orchestrator/app Orchestrator/worker.py -ll
# mypy + pylint: usar o script de governança (aplica flags corretas por arquivo)
pwsh -File Tools\Test-PythonGovernance.ps1 -RootPath .

# Recompilar dependências pinadas (pip-tools)
pip-compile requirements.in -o requirements.txt

# Lint que roda no CI (bloqueante) — reproduzir localmente antes do push
python -m ruff check Orchestrator/app Orchestrator/worker.py
```

### Dashboard (React + TypeScript + Vite)
```powershell
cd Dashboard; npm ci            # instalar dependências
cd Dashboard; npm run lint      # ESLint (src/**/*.ts,tsx)
cd Dashboard; npm run build     # tsc + vite build → Dashboard/dist/
npm run lint:js                 # atalho na raiz: delega ao lint do Dashboard
```

### Governança e Quality Gate
```powershell
# Quality gate completo
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath .

# Somente governança (skills, encoding, manifesto)
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance

# Encoding dos fontes
pwsh -File Tools\Test-SourceEncoding.ps1 -RootPath .

# Skills governance (canônico vs mirror)
pwsh -File Tools\Test-SkillsGovernance.ps1 -BasePath .

# Padrão arquitetural
pwsh -File Tools\Test-ArchitectureStandard.ps1
```

### Scaffolding de nova automação
```powershell
pwsh -File Tools\New-Automation.ps1 -Name "NomeAutomacao" -Owner "equipe" -Criticidade "high"
```

## Arquitetura

### Visão Geral
Monorepo com três camadas principais:

1. **Orchestrator** (`Orchestrator/`) — FastAPI v5 + APScheduler + SQLite WAL. Motor de execução central.
2. **Dashboard** (`Dashboard/`) — SPA React + TypeScript + Vite (fontes em `Dashboard/src/`, build em `Dashboard/dist/`) servido pelo próprio FastAPI via `StaticFiles` com fallback SPA para rotas client-side. Roda em `http://127.0.0.1:8000/dashboard/`.
3. **Automações de domínio** — diretórios independentes. As automações registradas com manifesto (`Receitas Bloqueadas/`, `Receitas Emitidas/`, `Montagem de Terceirizados/`, `OBs Paradas Fase/`) usam `run.ps1` como entrypoint; `Produção Beneficimento/` é orientada a snapshot (sem `run.ps1`, ver abaixo).

### Orchestrator (`Orchestrator/app/`)
- `main.py` — startup FastAPI: registra routers, monta SPA, inicializa Alembic e jobs APScheduler. Chama `register_event_loop(asyncio.get_running_loop())` no lifespan para viabilizar wake-up thread-safe do worker.
- `worker.py` (em `Orchestrator/`, fora de `app/`) — loop de execução: consome fila, spawn de processos PowerShell, graceful shutdown.
- `runtime.py` — estado compartilhado entre `main.py`, routers e worker. Inclui `register_event_loop` + `trigger_worker_wakeup` (usa `loop.call_soon_threadsafe` — **nunca** chamar `task_queued_event.set()` diretamente de endpoint sync, pois endpoints FastAPI sync rodam em threadpool separada do event loop).
- `database.py` — engine SQLite WAL, `SessionLocal`, `session_scope` (context manager para sessões fora do FastAPI). `purge_old_executions` preserva as últimas 50 execuções por automação via subquery com `ROW_NUMBER() OVER (PARTITION BY automation_id)`.
- `models.py` — ORM SQLAlchemy: `Automation`, `Execution`, `WorkerHeartbeat`, `SystemHealthSnapshot`, `AuditLog`.
- `routers/` — um arquivo por domínio de API (`automations`, `executions`, `system`, `beneficiamento`, `portfolio`, `websocket`, `automation_config`, `automation_ide`).
- `services/` — lógica desacoplada dos routers: `system_diagnostics`, `system_history`, `operational_baseline`, `portfolio_catalog`, `scheduler_runtime`, `scoring`, `execution_decoration` (decoração de execuções com ações do operador), `execution_runtime` (requeue e validação), etc.
- `migrations/` (em `Orchestrator/`, fora de `app/`) — Alembic; `env.py` usa `render_as_batch=True` para compatibilidade SQLite.

### Domínio Beneficiamento (`Produção Beneficimento/src/beneficiamento/`)
- `core/` — coerção, métricas, schema e turnos (lógica pura, sem I/O).
- `data/` — queries SQL, schema de dados e writer para persistência histórica.
- `contracts/` — implementação histórica canônica (`overview.py`, `detail.py`, `_queries.py`, `tingimento.py` — agregação da fase real de tingimento consumida por `GET /api/beneficiamento/tingimento`).
- `oracle.py` — única interface com Oracle; nunca abre conexão fora deste arquivo.
- `runner.py` — orquestra snapshot Oracle → SQLite histórico; orçamento de 20 s.
- `snapshot_store.py` — lê/escreve `Produção Beneficimento/snapshots/latest/`. A API **nunca** consulta Oracle diretamente; consome apenas esses snapshots.

### Biblioteca compartilhada Python (`lib/python/`)
- `oracle_extract.py` — núcleo compartilhado de extração Oracle: `resolve_oracle_credentials`, `init_thick_mode`, `fetch_all` (lotes), `serialize_rows` (datetime→isoformat, strip), `compute_hash`, `read_last_hash`, `write_state_tmp`. **Todos os 4 scripts de extração de domínio (`Receitas Emitidas/`, `Receitas Bloqueadas/`, `Montagem de Terceirizados/`, `OBs Paradas Fase/`) usam este módulo** — não duplicar o padrão fetch/serialize/hash em novos scripts. Para DSN fixo (ignorar `.env`), passe `force_dsn="dbprd"` em `resolve_oracle_credentials`.
- `oracle_client.py` — `init_oracle_thick_mode` (ativa Thick Mode do oracledb).
- `oracle_retry.py` — `make_oracle_retry()` (pybreaker + stamina) e `CircuitBreakerError`.

### Biblioteca compartilhada PowerShell (`lib/`)
- `Lib-OrchestratorRuntime.psm1` — fonte única para scripts de Infrastructure: `Get-OrchestratorRuntimeVersion` (lê `ORCHESTRATOR_VERSION` de `constants.py`), `Get-OrchestratorEnvValue` (parser de `.env`), `Stop-OrchestratorProcesses` (usa `Get-CimInstance Win32_Process` — **nunca** `Get-Process`, que não expõe `CommandLine` no PS 5.1). Todos os scripts de `Infrastructure/` devem importar este módulo.
- `Lib-Config.psm1` — leitura de `.env` para scripts de automação de domínio.

### Infrastructure (`Infrastructure/`)
Scripts PowerShell para ciclo de vida do Orchestrator: `Start-Orchestrator.ps1`, `Recover-Orchestrator.ps1`, `Diagnose-Orchestrator.ps1`, `MonitorAutomacoes.ps1`. Todos importam `Lib-OrchestratorRuntime.psm1`.

### Skills canônicas (`.github/skills/`)
Sete skills governam decisões de implementação. `.gemini/skills/` é apenas mirror. Edite sempre a fonte canônica.

## Regras Operacionais Críticas

### Encoding
- `.ps1` / `.psm1` → **UTF-8 com BOM** (obrigatório para PowerShell 5.1 com acentuação PT-BR).
- `.py`, `.js`, `.json`, `.html`, `.css`, `.md`, `.sql`, `.txt` → **UTF-8 sem BOM**.

### Caminhos
- **Nunca use caminhos absolutos** em scripts PowerShell. Use `.\` ou `$PSScriptRoot`.
- Python: paths relativos à raiz do projeto ou derivados de `.env`.

### Banco de dados
- Todas as sessões SQLAlchemy fora do contexto FastAPI usam `session_scope` (não `SessionLocal()` diretamente).
- Migrações de schema são feitas exclusivamente via Alembic (`upgrade head` no startup).
- WAL checkpoint periódico usa modo `PASSIVE` para não bloquear writers.

### Zero-Trust
- Nenhuma credencial hardcoded. Tudo via `.env` (lido por `lib/Lib-Config.psm1` em PowerShell, `python-dotenv` em Python).
- Dashboard solicita API Key via prompt; persiste em `localStorage`.

### Commits e Documentação Viva
- Mensagens de commit em **Português do Brasil** (mesmo padrão de `CHANGELOG.md` e ADRs).
- Atualizar `CHANGELOG.md` quando a mudança alterar comportamento, contrato operacional, governança ou arquitetura.
- Atualizar `docs/ai-native-context-monitor.md` quando a mudança alterar estado que futuros agentes precisam conhecer para decidir corretamente.

### Validação E2E
- Para mudanças em rotas FastAPI consumidas pelo Dashboard ou em `Dashboard/src/`, a validação final obrigatória é Playwright contra `http://127.0.0.1:8000/dashboard/`.
- Registrar evidência com `Tools/Test-PlaywrightEvidence.ps1`.
- Padrão completo (critérios, evidência mínima): `docs/playwright-e2e-standard.md`.

### Manifesto de automação
- Toda automação registrada no Orchestrator deve ter `automation.manifest.json` na sua pasta.
- `POST /api/automations/preflight` valida manifesto, docs obrigatórias e smoke tests antes de `create/update`.

### CI (GitHub Actions — `.github/workflows/governanca.yml`)
Pipeline único, roda em push para `main`/`escalar/**` e PRs. Gates bloqueantes: `ruff check Orchestrator/app Orchestrator/worker.py`, black/isort/bandit (job `lint-python`), pytest com `--cov-fail-under=84` (job `testes-python`), além de `diff-cover --fail-under=85` nas linhas alteradas do PR, E2E Playwright (job `testes-e2e`), Gitleaks, Pester, lint+build do Dashboard e a governança agregada (`ValidarAutomacoes.ps1 -OnlyGovernance`). O mypy bloqueante é o do pre-commit hook (`Test-PythonGovernance.ps1`). O antigo `ci.yml` foi consolidado neste pipeline em 01/07/2026.

## Contratos de Governança (Pre-Commit Hook)

O hook executa `ValidarAutomacoes.ps1 -OnlyGovernance` a cada commit (14 validações: zero-trust, SQL, mypy/pylint, PowerShell, encoding, JSON, Playwright, manifesto, arquitetura, datas, semântica, Node). Regras detalhadas (limites exatos de mypy/pylint, formato de manifesto, contratos PowerShell, snippets corretos/errados) estão em **[docs/governance-contracts.md](docs/governance-contracts.md)** — consulte antes de escrever código Python/PowerShell novo ou editar `automation.manifest.json`.

## Princípios Comportamentais

**1. Pensar Antes de Executar** — Declare assunções explicitamente. Se incerto, pergunte. Se existirem múltiplas interpretações, apresente-as — não escolha silenciosamente.

**2. Simplicidade Primeiro** — Mínimo de código que resolve o problema. Sem features além do pedido, sem abstrações para uso único.

**3. Mudanças Cirúrgicas** — Toque apenas o necessário. Não "melhore" código adjacente. Cada linha alterada deve ser rastreável ao pedido.

**4. Execução Orientada a Metas** — Transforme tarefas em metas verificáveis. Para múltiplos passos, declare plano e critérios de sucesso antes de implementar.
