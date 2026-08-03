---
name: run-orchestrator
description: Sobe, dirige e tira screenshot do Orchestrator (API FastAPI + Dashboard SPA em http://127.0.0.1:8000/dashboard/). Use para rodar o app, iniciar/parar o serviço, autenticar no dashboard, capturar telas, chamar rotas /api/* autenticadas, invocar services do backend direto ou validar que uma mudança funciona no app real (não só nos testes).
---

# Rodar e dirigir o Orchestrator

O app é uma API FastAPI (`Orchestrator/app/main.py`) que serve o Dashboard React
compilado (`Dashboard/dist/`) em `http://127.0.0.1:8000/dashboard/`. Um worker
separado (`Orchestrator/worker.py`) consome a fila de execuções.

O caminho do agente é o driver **`.claude/skills/run-orchestrator/driver.py`** —
Playwright (o do `.venv`, Python) + `urllib`. Ele autentica sozinho lendo
`ORCHESTRATOR_API_KEY` do `.env`; **nunca peça a chave ao usuário**.

Todos os caminhos abaixo são relativos à raiz do repositório (`C:\Automacoes`).

## ⚠️ Esta máquina roda o Orchestrator em produção

Antes de qualquer coisa, cheque se já há uma instância viva:

```bash
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py health
```

Se responder `[OK] saudavel`, **use a instância existente** — o driver se conecta
a ela. Não rode `Start-Orchestrator.ps1`: ele faz "surgical reset", mata o worker
e aborta execuções em voo de automações reais (o worker desta máquina acumulava
3,5 dias de uptime e 130 execuções quando esta skill foi escrita).

## Pré-requisitos

Já satisfeitos nesta máquina — verifique antes de instalar qualquer coisa:

- Python do projeto em `.venv\` na **raiz** (não em `Orchestrator/`).
- Playwright Python + Chromium 148 já instalados no `.venv`.
  Se faltar o browser: `.venv\Scripts\python -m playwright install chromium`.
- Node 24 + npm 11 (só para rebuildar o Dashboard).
- `.env` na raiz com `ORCHESTRATOR_API_KEY` e `HUB_API_PORT`.

Não há Playwright em `Dashboard/node_modules` — `npx playwright` **não** resolve.

## Build (só se você mexeu em `Dashboard/src/`)

```bash
cd Dashboard && npm run build
```

`tsc && vite build` → `Dashboard/dist/` (~5 s). O FastAPI serve `dist/` via
`StaticFiles`, que lê do disco a cada request: **não precisa reiniciar a API**
depois do build, basta recarregar a página.

## Run — caminho do agente (driver)

```bash
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py smoke
```

`smoke` = `health` + `login` + varredura das 6 rotas, com relatório de console.

**Política de exit code dos comandos com browser** (`login`, `shot`, `smoke`):
sai com 1 apenas em `error` de console, `pageerror` (exceção não tratada no
bundle) ou gate de API Key aparecendo onde não devia. `warning` de console é
listado no relatório como `console (aviso)` mas **não reprova** — a alternativa
seria inflar `IGNORAR_CONSOLE` até ele deixar de detectar erro real. Cada
mensagem vem carimbada com a rota em que apareceu (`[painel] error: ...`).

Comandos individuais:

| Comando | O que faz |
|---|---|
| `health` | `GET /api/system/health` sem browser. Resumo de database/scheduler/worker. |
| `api <rota> [...]` | `GET` autenticado em rotas `/api/*`. Imprime o JSON truncado. |
| `login` | Fluxo real: digita a chave no gate, clica **Entrar →**, espera o shell. |
| `shot [rota ...]` | Injeta a chave em `sessionStorage` (pula o gate) e captura cada rota. Sem argumentos, captura todas. |
| `smoke` | Os três acima em sequência. |

Opção comum a todos: `--tag <rótulo>` sufixa os PNGs (`rota-painel--antes.png`),
para comparar antes/depois sem sobrescrever a evidência da execução anterior.
Sem `--tag`, o nome é o simples de sempre.

Exceto `health` — que bate numa rota pública — todos os comandos exigem
`ORCHESTRATOR_API_KEY` no `.env` e abortam com mensagem própria se ela faltar
(sem a chave a API responde 403).

Exemplos que rodaram nesta sessão:

```bash
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py api /api/automations /api/executions /api/system/diagnostics
```

```bash
.venv\Scripts\python .claude\skills\run-orchestrator\driver.py shot painel beneficiamento
```

Screenshots vão para **`Logs\driver\`** (`login-gate.png`, `login-painel.png`,
`rota-<nome>.png`). `Logs/` é ignorado pelo git. **Abra o PNG e olhe** — o driver
retorna 0 mesmo com uma tela visualmente quebrada, desde que não haja erro de
console nem o gate de API Key.

Rotas do SPA: `painel`, `execucoes`, `monitor`, `beneficiamento`, `automacoes`,
`sistema`. Deep-link direto (`/dashboard/execucoes`) funciona — o fallback SPA do
FastAPI cobre.

## Run — invocação direta do backend (sem subir o app)

A maioria dos PRs toca `Orchestrator/app/services/` ou `models.py`. Para isso não
precisa de browser: importe e chame, **a partir de `Orchestrator/`**.

```bash
cd Orchestrator && ..\.venv\Scripts\python -c "from app.database import session_scope; from app.models import Automation
with session_scope() as s: print([a.name for a in s.query(Automation).all()])"
```

Isso lê o **banco de produção** (`Orchestrator/automacoes.db`). Leitura é segura
sob WAL mesmo com o worker rodando; **não escreva** por esse caminho.

## Run — caminho humano

```bash
pwsh -File Infrastructure\Start-Orchestrator.ps1
```

Reset cirúrgico + worker + uvicorn + watchdog, valida `/api/system/health` por até
20 s. **Só use se `health` acusar a API fora do ar** — leia o aviso no topo.
Recuperação após falha: `pwsh -File Infrastructure\Recover-Orchestrator.ps1`.

## Testes

```bash
cd Orchestrator && ..\.venv\Scripts\pytest -m unitario -q
```

527 passaram em ~78 s. Marcadores: `unitario | integracao | e2e`. A suíte padrão exclui
`e2e` via `addopts` do `pytest.ini`; `-m e2e` sobrescreve e exige o Orchestrator no ar.

## Gotchas

- **Se `pytest` falhar com `ModuleNotFoundError: No module named 'app'`** (exit 4, no import
  do `conftest.py`), confira se `Orchestrator/pytest.ini` ainda declara `pythonpath = .`.
  Sem essa linha, o console script não põe o cwd em `sys.path` e só funcionam os caminhos
  que exportam `PYTHONPATH` por fora (CI, `Test-OrchestratorIntegrity.ps1`) ou
  `python -m pytest`. Foi assim que o repositório ficou até 03/08/2026.
- **`sessionStorage` tem que ser setado ANTES do bundle carregar.**
  `Dashboard/src/api/client.ts:6` lê a chave no carregamento do módulo, não em
  `useEffect`. Setar via `page.evaluate()` depois do `goto` deixa o gate de login
  na tela (testado: gate continua visível). O driver usa
  `context.add_init_script()` — mantenha assim.
- **A API responde 403, não 401,** para requisição sem `X-API-Key`.
- **A chave vive só em `sessionStorage`**, nunca em `localStorage` (há teste
  dedicado proibindo). Cada contexto novo do Playwright começa deslogado.
- **`Dashboard/dist/` é gitignored.** Depois de um `git clean` ou clone novo, a
  rota `/dashboard/` fica sem bundle até rodar `npm run build`.
- **Nunca execute os `run.ps1` das automações de domínio para "testar".** Eles
  disparam e-mail/Outlook e consultas Oracle de produção. Para exercitar o motor,
  enfileire pela API/dashboard e observe.
- Console limpo é o esperado: as 6 rotas rodaram com 0 erro e 0 warning. Só o
  erro reprova (ver a política de exit code acima); um warning novo aparecendo
  no relatório merece investigação mesmo saindo 0.
- **`driver.py` está nos gates de qualidade** desde 03/08/2026: ruff, black,
  isort e bandit cobrem `.claude/skills` no CI e no `CLAUDE.md`, e o
  `Test-PythonGovernance.ps1` já o pegava via `git ls-files "*.py"` (mypy
  `--strict` + pylint). Rode-os antes de commitar mudanças aqui.

## Troubleshooting

| Sintoma | Causa / correção |
|---|---|
| `[FALHA] API nao respondeu em http://127.0.0.1:8000` | Falha de **conexão** — Orchestrator parado. Só neste caso: `pwsh -File Infrastructure\Start-Orchestrator.ps1`. |
| `[FALHA] /api/system/health -> HTTP <código>` | A API **respondeu** (429 do rate limit, 500 de health degradado). Não reinicie: investigue o código e os logs. |
| `[FALHA] ORCHESTRATOR_API_KEY ausente ou vazia no .env` | O `.env` da raiz não tem a chave (ou ela foi renomeada). Não passe a chave por argumento nem peça ao usuário. |
| `driver.py shot` sai 1 com "gate de API Key apareceu" | `ORCHESTRATOR_API_KEY` do `.env` divergente da que a API valida. Confira o `.env` — não hardcode. |
| `ModuleNotFoundError: No module named 'app'` | Rodou de fora de `Orchestrator/`, ou o `pythonpath = .` sumiu do `pytest.ini`. |
| `Executable doesn't exist at ...chromium...` | `.venv\Scripts\python -m playwright install chromium`. |
| Screenshot em branco / tela antiga | Bundle velho em `Dashboard/dist/`. `cd Dashboard && npm run build` e recapture (a API não precisa reiniciar). |
