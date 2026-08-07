# Contratos de Governança (Pre-Commit Hook)

> Extraído de `CLAUDE.md` em 14/07/2026 para reduzir contexto carregado por padrão. Consultar este arquivo sob demanda (ex.: ao escrever código Python/PowerShell novo ou ajustar manifesto de automação), não é carregado automaticamente em toda sessão.

O hook executa `ValidarAutomacoes.ps1 -OnlyGovernance` a cada commit. Quando arquivos centrais (infra, lib, Tools) estão staged, o modo é `full_scan` — varre todo o repositório. **Escreva já no padrão abaixo; não tente depois.**

## Pipeline de validações (ordem de execução)

Ordem real do array `$checks` em `Tools/ValidarAutomacoes.ps1` (função `Invoke-NativeGovernanceCheck`):

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
| 9 | `Test-PlaywrightEvidence.ps1` | Evidência E2E sem URL real, console limpo ou resultado aprovado |
| 10 | `Test-AutomationCatalog.ps1` | Manifesto ausente ou campos faltando |
| 11 | `Test-ArchitectureStandard.ps1` | Oracle fora de `oracle.py`, sessão sem `session_scope` |
| 12 | `Test-DateConformidade.ps1` | Datas fora do formato DD/MM/AAAA |
| 13 | `Test-SemanticGovernance.ps1` | Drift entre monitor, constantes, docs, skills, catálogo e dependências |
| 14 | `Test-NodeCommunications.ps1` | Contrato Node.js (whatsapp-offline.test.js) + suíte de unidade de `lib/WhatsApp-Core.js` (`node:test`, gate de cobertura 90% linhas/branches/funções) |

Nota: `Test-SkillsGovernance.ps1` e `Test-DashboardTemplate.ps1` **não** fazem parte do array `$checks` acima — rodam em pontos próprios do script, via `Invoke-SkillsGovernanceCheck` e `Invoke-DashboardTemplateCheck`, respectivamente.

Nota: `Test-NodeCommunications.ps1` roda `npm test` em cada diretório com `package.json` (`Receitas Bloqueadas/`, `lib/`), exigindo `node_modules/` já instalado **apenas quando o `package.json` do diretório declara `dependencies`/`devDependencies` não vazias** — `Receitas Bloqueadas/package.json` não declara nenhuma (o teste usa só `assert`/`fs`/`path` nativos) e sempre roda sem instalação prévia; `lib/package.json` exige o pacote real `whatsapp-web.js` instalado (`require()` de topo, mesmo com os testes trocando a implementação depois via seam de DI) e `node_modules` é gitignored. Sem essa checagem condicional, um clone novo bloquearia todo commit local até alguém rodar `npm ci` manualmente em `lib/`. Diretório que declara dependências mas ainda não tem `node_modules` é pulado com `[SKIP]` no gate local — não falha o commit, mas também não valida essa suíte localmente. Rode `npm ci --prefix lib` uma vez após clonar (ou `PUPPETEER_SKIP_DOWNLOAD=true npm ci --prefix lib` para pular o download do Chromium, ~200MB, desnecessário pois a suíte só mocka o `Client`) para incluir `lib/` no gate local. O CI (job `governanca-agregada`) sempre instala via `npm ci` antes deste gate, então a cobertura real da suíte permanece obrigatória no pipeline bloqueante independentemente do estado da máquina local.

---

## Contrato Python — mypy `--strict`

Escreva **sempre** com anotações completas. O mypy roda `--strict --explicit-package-bases`.

```python
# CORRETO
from typing import Any

def processar(nome: str, dados: list[dict[str, Any]]) -> tuple[int, str]:
    ...

def buscar(fase: str, mapa: dict[str, float]) -> float | None:
    ...

# ERROS COMUNS
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

## Contrato Python — pylint

Desabilitados por padrão (não precisam ser corrigidos): `C0114` (module docstring), `C0115` (class docstring), `C0116` (function docstring), `R0801` (duplicate-code), `C0413` (wrong-import-position), `C0301` (line-too-long), `C0302` (too-many-lines), `C0411` (wrong-import-order — a detecção de first-party do pylint diverge do isort/perfil black usado no CI; isort é a fonte de verdade para ordem de imports).

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

# Inline em vez de variável intermediária
with open(PATH, "w") as f:
    json.dump({"key": val, "other": val2}, f)   # sem variável "payload"

# Extrair extração de dados em helper
def _extrair_dados(row: dict[str, Any]) -> tuple[float, bool, str]:
    ...  # remove 3+ locais da função chamadora
```

---

## Conflito isort vs ruff I001 em imports com alias

Quando um módulo tem imports **mistos** (aliased + não-aliased) na mesma instrução `from x import`, isort e ruff I001 entram em conflito irresolvível. A solução é converter para **import de namespace**:

```python
# CONFLITO IRRESOLVÍVEL — isort e ruff discordam na ordenação
from ..services.system_runtime import build_health_payload, get_worker_status
from ..services.system_runtime import get_worker_status as get_worker_status_service

# CORRETO — elimina o conflito usando namespace import
from ..services import system_runtime

# chamadas: system_runtime.build_health_payload(...), system_runtime.get_worker_status(...)
```

---

## PowerShell 5.1 — inspeção de processos

`Get-Process` **não expõe `CommandLine`** no Windows PowerShell 5.1. A propriedade existe no objeto mas é sempre `$null`. Use `Get-CimInstance Win32_Process` para filtrar processos por linha de comando:

```powershell
# NUNCA funciona no PS 5.1
Get-Process python | Where-Object { $_.CommandLine -match "worker" }

# CORRETO
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "python" -and $_.CommandLine -match "worker"
}
```

---

## Contrato PowerShell — catch tipado

O script detecta `catch\s*\{` com regex — **qualquer** catch sem tipo no arquivo reprova.

```powershell
# ERRADO — qualquer uma dessas formas reprova
} catch { ... }
try { ... } catch { }
catch { Write-Log "aviso: $_" }

# CORRETO — mínimo aceitável
} catch [System.Exception] { ... }
try { ... } catch [System.Exception] { }
catch [System.IO.IOException] { Write-Log "aviso: $_" }   # mais específico, melhor
```

---

## Contrato PowerShell — paths portáveis

```powershell
# ERRADO — caminho com letra de drive (reprova portabilidade)
# $file = "<DRIVE>:\Projeto\lib\config.json"

# CORRETO — sempre relativo ao script ou à raiz do projeto
$file = Join-Path $PSScriptRoot "..\lib\config.json"
$file = Join-Path $projectRoot "lib\config.json"
```

---

## Contrato — Manifesto de Automação (`automation.manifest.json`)

Campos obrigatórios para `preflight` aceitar:

```json
{
  "id": "XXX-00",
  "name": "Nome Legível",
  "slug": "nome-automacao",
  "criticality": "high",
  "script_path": "Nome Dir/run.ps1",
  "entrypoint": "run.ps1",
  "runtime": "powershell",
  "channels": ["whatsapp"],
  "owner_area": "Equipe / Area",
  "max_runtime_minutes": 15,
  "max_retries": 0,
  "schedule_summary": "Seg-Sex às 07:00 e 13:30",
  "schedule": "{\"schedule_version\":2,\"schedule_type\":\"cron\",\"cron_expression\":\"30 7,13 * * 1-5\",\"timezone\":\"America/Sao_Paulo\"}",
  "runbook_path": "docs/runbooks/nome-runbook.md",
  "context_path": "Nome Dir/CONTEXT.md",
  "readme_path": "Nome Dir/README.md",
  "orchestrator": {
    "script_path": "./Nome Dir/run.ps1"
  },
  "dependencies": {
    "oracle": false,
    "outlook": false,
    "whatsapp": true
  },
  "smoke_tests": ["Orchestrator/tests/test_nome.py"]
}
```

**Campos obrigatórios validados por `Test-AutomationCatalog.ps1`:** `id`, `name`, `slug`, `criticality`, `owner_area`, `entrypoint`, `runtime`, `channels`, `max_runtime_minutes`, `max_retries`, `schedule_summary`, `runbook_path`, `context_path`, `readme_path`, `orchestrator` (com `orchestrator.script_path`), `dependencies`, `smoke_tests`.

Atenção: o campo é **`criticality`** (inglês), não `criticidade`. `schedule` e `script_path` no nível raiz são adicionais para o preflight, mas `orchestrator.script_path` e `entrypoint` são exigidos pelo catalogador.

`schedule` é uma **string JSON** (não objeto). Sem trailing comma. Sem comentários.

---

## Contrato — Testes Python (smoke tests)

```python
# Todo teste precisa de anotação de retorno -> None
def test_algo() -> None:          # correto
    assert ...

def test_algo():                  # mypy reprova (missing return type)
    assert ...
```

---

## Verificação rápida antes do commit

```powershell
# Python — verificar um arquivo específico (usar as mesmas flags do hook de governança)
$env:MYPYPATH = "Orchestrator;.;lib\python"
.venv\Scripts\mypy "Pasta\arquivo.py" --strict --explicit-package-bases --namespace-packages
python -m pylint "Pasta\arquivo.py" 2>&1 | Where-Object { $_ -match "R0[0-9]|C0415" }

# PowerShell — verificar catch genérico
Select-String -Path "Pasta\run.ps1" -Pattern 'catch\s*\{'

# Governança completa (demora ~3 min)
pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance
```
