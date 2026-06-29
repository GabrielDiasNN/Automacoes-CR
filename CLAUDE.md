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

## Contratos de Governança (Pre-Commit Hook)

O hook executa `ValidarAutomacoes.ps1 -OnlyGovernance` a cada commit. Quando arquivos centrais (infra, lib, Tools) estão staged, o modo é `full_scan` — varre todo o repositório. **Escreva já no padrão abaixo; não tente depois.**

### Pipeline de validações (ordem de execução)

| # | Script | O que reprova |
|---|--------|---------------|
| 1 | `Test-ZeroTrust.ps1` | Credenciais hardcoded, tokens, IPs privados |
| 2 | `Test-SqlPerformance.ps1` | `SELECT *`, `FULL TABLE SCAN` sem hint |
| 3 | `Test-PythonGovernance.ps1` | mypy `--strict` + pylint (ver abaixo) |
| 4 | `Test-PowerShellGovernance.ps1` | `catch\s*{` genérico em qualquer linha |
| 5 | `Test-PowerShellApprovedVerbs.ps1` | Verbos não aprovados em funções PS |
| 6 | `Test-PortablePaths.ps1` | Caminhos absolutos em `.ps1` |
| 7 | `Test-SourceEncoding.ps1` | `.ps1` sem BOM; `.py/.json` com BOM |
| 8 | `Test-JsonConfig.ps1` | JSON inválido em qualquer `*.json` staged |
| 9 | `Test-AutomationCatalog.ps1` | Manifesto ausente ou campos faltando |
| 10 | `Test-ArchitectureStandard.ps1` | Oracle fora de `oracle.py`, sessão sem `session_scope` |
| 11 | `Test-NodeCommunications.ps1` | Contrato Node.js (whatsapp-offline.test.js) |
| 12 | Outros | Encoding, Playwright, Skills, Semântica, Datas |

---

### Contrato Python — mypy `--strict`

Escreva **sempre** com anotações completas. O mypy roda `--strict --explicit-package-bases`.

```python
# ✅ CORRETO
from typing import Any

def processar(nome: str, dados: list[dict[str, Any]]) -> tuple[int, str]:
    ...

def buscar(fase: str, mapa: dict[str, float]) -> float | None:
    ...

# ❌ ERROS COMUNS
def processar(nome, dados):          # falta anotações de param e retorno
def buscar(fase: str) -> dict:       # dict sem type args
def items() -> list:                 # list sem type args
val = json.load(f).get("k", "")     # retorna Any → cast: str(json.load(f).get("k", ""))
```

**Regras rápidas:**
- Todo parâmetro: `: Tipo`
- Todo retorno: `-> Tipo` (inclusive `-> None`)
- Generics sempre com args: `list[str]`, `dict[str, Any]`, `tuple[int, str]`
- `json.load()` retorna `Any` — ao atribuir a variável tipada, use `str(...)` ou `cast()`
- `from typing import Any` quando usar `Any`

---

### Contrato Python — pylint

Desabilitados por padrão (não precisam ser corrigidos): `C0114` (module docstring), `C0116` (function docstring), `R0801` (duplicate-code), `C0413` (wrong-import-position), `C0301` (line-too-long), `C0302` (too-many-lines).

**Limites que reprovam:**

| Código | Regra | Limite | Como contar | Solução |
|--------|-------|--------|-------------|---------|
| `R0914` | too-many-locals | **15** | Parâmetros + variáveis no corpo (inclusive loop vars e `as f`) | Extrair helper; inlinar variáveis de passagem |
| `R0912` | too-many-branches | **12** | `if/elif/else/for/while/try/except` | Extrair lógica de filtro em funções dedicadas |
| `R0915` | too-many-statements | **50** | Cada linha de código executável | Extrair blocos em helpers |
| `R0917` | too-many-positional-arguments | **5** | Parâmetros posicionais | Agrupar em `dict[str, Any]` ou dataclass |
| `C0415` | import-outside-toplevel | **0** | Import dentro de função | Mover para o topo do arquivo |
| `pylint: disable=all` | proibido em arquivos novos | — | — | Permitido só se estiver em `Tools/pylint-disable-all-baseline.txt` |

**Estratégia para R0914 (mais comum):**
```python
# Contar locais = params + body vars (inclui: loop vars, with-as vars, tuple unpack)
# Função com 5 params + 10 vars = 15 → exatamente no limite
# Para reduzir: inlinar vars de passagem, extrair bloco em helper

# ✅ Inline em vez de variável intermediária
with open(PATH, "w") as f:
    json.dump({"key": val, "other": val2}, f)   # sem variável "payload"

# ✅ Extrair extração de dados em helper
def _extrair_dados(row: dict[str, Any]) -> tuple[float, bool, str]:
    ...  # remove 3+ locais da função chamadora
```

---

### Contrato PowerShell — catch tipado

O script detecta `catch\s*\{` com regex — **qualquer** catch sem tipo no arquivo reprova.

```powershell
# ❌ ERRADO — qualquer uma dessas formas reprova
} catch { ... }
try { ... } catch { }
catch { Write-Log "aviso: $_" }

# ✅ CORRETO — mínimo aceitável
} catch [System.Exception] { ... }
try { ... } catch [System.Exception] { }
catch [System.IO.IOException] { Write-Log "aviso: $_" }   # mais específico, melhor
```

---

### Contrato PowerShell — paths portáveis

```powershell
# ❌ ERRADO — caminho com letra de drive (reprova portabilidade)
# $file = "<DRIVE>:\Projeto\lib\config.json"

# ✅ CORRETO — sempre relativo ao script ou à raiz do projeto
$file = Join-Path $PSScriptRoot "..\lib\config.json"
$file = Join-Path $projectRoot "lib\config.json"
```

---

### Contrato — Manifesto de Automação (`automation.manifest.json`)

Campos obrigatórios para `preflight` aceitar:

```json
{
  "id": "XXX-00",
  "name": "Nome Legível",
  "script_path": "Nome Dir/run.ps1",
  "runtime": "powershell",
  "channels": ["whatsapp"],
  "criticidade": "high",
  "runbook_path": "docs/runbooks/nome-runbook.md",
  "context_path": "Nome Dir/CONTEXT.md",
  "readme_path": "Nome Dir/README.md",
  "smoke_tests": ["Orchestrator/tests/test_nome.py"],
  "schedule": "{\"schedule_version\":2,\"schedule_type\":\"cron\",\"cron_expression\":\"30 7,13 * * 1-5\",\"timezone\":\"America/Sao_Paulo\"}"
}
```

`schedule` é uma **string JSON** (não objeto). Sem trailing comma. Sem comentários.

---

### Contrato — Testes Python (smoke tests)

```python
# Todo teste precisa de anotação de retorno -> None
def test_algo() -> None:          # ✅
    assert ...

def test_algo():                  # ❌ mypy reprova (missing return type)
    assert ...
```

---

### Verificação rápida antes do commit

```powershell
# Python — verificar um arquivo específico
python -m mypy "Pasta\arquivo.py" --ignore-missing-imports
python -m pylint "Pasta\arquivo.py" 2>&1 | Where-Object { $_ -match "R0[0-9]|C0415" }

# PowerShell — verificar catch genérico
Select-String -Path "Pasta\run.ps1" -Pattern 'catch\s*\{'

# Governança completa (demora ~3 min)
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance
```

## Princípios Comportamentais

**1. Pensar Antes de Executar** — Declare assunções explicitamente. Se incerto, pergunte. Se existirem múltiplas interpretações, apresente-as — não escolha silenciosamente.

**2. Simplicidade Primeiro** — Mínimo de código que resolve o problema. Sem features além do pedido, sem abstrações para uso único.

**3. Mudanças Cirúrgicas** — Toque apenas o necessário. Não "melhore" código adjacente. Cada linha alterada deve ser rastreável ao pedido.

**4. Execução Orientada a Metas** — Transforme tarefas em metas verificáveis. Para múltiplos passos, declare plano e critérios de sucesso antes de implementar.
