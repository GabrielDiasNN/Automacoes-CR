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

# Lint Python (black, isort, bandit) — ferramentas via requirements-dev.txt
python -m black --check Orchestrator
python -m isort --check-only Orchestrator
python -m bandit -r Orchestrator/app Orchestrator/worker.py -ll

# Recompilar dependências pinadas (pip-tools)
pip-compile requirements.in -o requirements.txt
```

### Dashboard (JS)
```powershell
npm run lint:js          # eslint em Dashboard/js/**
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
2. **Dashboard** (`Dashboard/`) — SPA estático (HTML/CSS/JS puro) servido pelo próprio FastAPI via `StaticFiles`. Roda em `http://127.0.0.1:8000/dashboard/`.
3. **Automações de domínio** — diretórios independentes. As automações registradas com manifesto (`Receitas Bloqueadas/`, `Receitas Emitidas/`, `Montagem de Terceirizados/`) usam `run.ps1` como entrypoint; `Produção Beneficimento/` é orientada a snapshot (sem `run.ps1`, ver abaixo).

### Orchestrator (`Orchestrator/app/`)
- `main.py` — startup FastAPI: registra routers, monta SPA, inicializa Alembic e jobs APScheduler.
- `worker.py` (em `Orchestrator/`, fora de `app/`) — loop de execução: consome fila, spawn de processos PowerShell, graceful shutdown.
- `runtime.py` — estado compartilhado entre `main.py`, routers e worker (scheduler, wake-up, helpers de execução).
- `database.py` — engine SQLite WAL, `SessionLocal`, `session_scope` (context manager para sessões fora do FastAPI).
- `models.py` — ORM SQLAlchemy: `Automation`, `Execution`, `WorkerHeartbeat`, `SystemHealthSnapshot`, `AuditLog`.
- `routers/` — um arquivo por domínio de API (`automations`, `executions`, `system`, `beneficiamento`, `portfolio`, `websocket`, `automation_config`, `automation_ide`).
- `services/` — lógica desacoplada dos routers: `system_diagnostics`, `system_history`, `operational_baseline`, `portfolio_catalog`, `scheduler_runtime`, `scoring`, etc.
- `migrations/` (em `Orchestrator/`, fora de `app/`) — Alembic; `env.py` usa `render_as_batch=True` para compatibilidade SQLite.

### Domínio Beneficiamento (`Produção Beneficimento/src/beneficiamento/`)
- `core/` — coerção, métricas, schema e turnos (lógica pura, sem I/O).
- `data/` — queries SQL, schema de dados e writer para persistência histórica.
- `contracts/` — implementação histórica canônica (`overview.py`, `detail.py`, `_queries.py`).
- `oracle.py` — única interface com Oracle; nunca abre conexão fora deste arquivo.
- `runner.py` — orquestra snapshot Oracle → SQLite histórico; orçamento de 20 s.
- `snapshot_store.py` — lê/escreve `Produção Beneficimento/snapshots/latest/`. A API **nunca** consulta Oracle diretamente; consome apenas esses snapshots.

### Infrastructure (`Infrastructure/`)
Scripts PowerShell para ciclo de vida do Orchestrator: `Start-Orchestrator.ps1`, `Recover-Orchestrator.ps1`, `Diagnose-Orchestrator.ps1`, `MonitorAutomacoes.ps1`.

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

### Validação E2E
- Para mudanças em rotas FastAPI consumidas pelo Dashboard ou em `Dashboard/js/`, a validação final obrigatória é Playwright contra `http://127.0.0.1:8000/dashboard/`.
- Registrar evidência com `Tools/Test-PlaywrightEvidence.ps1`.

### Manifesto de automação
- Toda automação registrada no Orchestrator deve ter `automation.manifest.json` na sua pasta.
- `POST /api/automations/preflight` valida manifesto, docs obrigatórias e smoke tests antes de `create/update`.

## Princípios Comportamentais

**1. Pensar Antes de Executar** — Declare assunções explicitamente. Se incerto, pergunte. Se existirem múltiplas interpretações, apresente-as — não escolha silenciosamente.

**2. Simplicidade Primeiro** — Mínimo de código que resolve o problema. Sem features além do pedido, sem abstrações para uso único.

**3. Mudanças Cirúrgicas** — Toque apenas o necessário. Não "melhore" código adjacente. Cada linha alterada deve ser rastreável ao pedido.

**4. Execução Orientada a Metas** — Transforme tarefas em metas verificáveis. Para múltiplos passos, declare plano e critérios de sucesso antes de implementar.
