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
Sai com 1 se algo falhar. Comandos individuais:

| Comando | O que faz |
|---|---|
| `health` | `GET /api/system/health` sem browser. Resumo de database/scheduler/worker. |
| `api <rota> [...]` | `GET` autenticado em rotas `/api/*`. Imprime o JSON truncado. |
| `login` | Fluxo real: digita a chave no gate, clica **Entrar →**, espera o shell. |
| `shot [rota ...]` | Injeta a chave em `sessionStorage` (pula o gate) e captura cada rota. Sem argumentos, captura todas. |
| `smoke` | Os três acima em sequência. |

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
cd Orchestrator && ..\.venv\Scripts\python -m pytest -m unitario -q
```

527 passaram em ~76 s. Marcadores: `unitario | integracao | e2e`.

## Gotchas

- **`..\.venv\Scripts\pytest.exe` quebra.** Dá
  `ModuleNotFoundError: No module named 'app'` ao carregar o `conftest.py` (exit 4),
  porque o `.exe` não coloca o cwd em `sys.path`. Use sempre
  `..\.venv\Scripts\python -m pytest`. O `CLAUDE.md` documenta a forma que falha.
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
- Console limpo é o esperado: as 6 rotas rodaram com 0 erro e 0 warning.

## Troubleshooting

| Sintoma | Causa / correção |
|---|---|
| `[FALHA] API nao respondeu em http://127.0.0.1:8000` | Orchestrator parado. `pwsh -File Infrastructure\Start-Orchestrator.ps1`. |
| `driver.py shot` sai 1 com "gate de API Key apareceu" | `ORCHESTRATOR_API_KEY` do `.env` divergente da que a API valida. Confira o `.env` — não hardcode. |
| `ModuleNotFoundError: No module named 'app'` | Rodou de fora de `Orchestrator/`, ou usou `pytest.exe` em vez de `python -m pytest`. |
| `Executable doesn't exist at ...chromium...` | `.venv\Scripts\python -m playwright install chromium`. |
| Screenshot em branco / tela antiga | Bundle velho em `Dashboard/dist/`. `cd Dashboard && npm run build` e recapture (a API não precisa reiniciar). |
