---
name: enterprise-orchestration-contract
description: Use when defining or changing ExecId/trace_id propagation, idempotency, state transitions, automation entrypoints, or the execution handoff between PowerShell, Python, Node.js, Infrastructure scripts and the Orchestrator.
---

## Purpose
Fixar o contrato transversal de execução do hub: como uma automação é disparada, repetida, monitorada e auditada sem perder rastreabilidade (`trace_id` / `ExecId`) nem duplicar efeito colateral (e-mail, WhatsApp, escrita Oracle). Cobre as fronteiras entre `run.ps1`, os runtimes consumidores (Python, Node.js) e o `Orchestrator/`.

## When to Use
- Ao alterar o `run.ps1` de qualquer uma das 6 automações registradas, ou o fluxo de snapshot de `Produção Beneficimento/`.
- Ao mexer em `Infrastructure/` (ciclo de vida do Orchestrator) ou em `Orchestrator/app/` / `Orchestrator/worker.py` — aqui pelo contrato de estado, handoff e reexecução; a sintaxe e a modularização desses `.ps1` são de `powershell-automation-monitor`.
- Ao criar ou editar arquivo de estado de idempotência (`*_state.json`, `delivery_state.json`, `*_seen_state.json`).
- Ao definir regra de reexecução, retomada após timeout ou propagação de identificador de execução entre camadas.
- Ao adicionar migração em `Orchestrator/migrations/versions/` ou alterar `Orchestrator/app/models.py`.

## Do Not Use When
- Para política de segredo, Zero-Trust, encoding, severidade de log ou fronteira entre falha recuperável e terminal: use `automation-runtime-safety`.
- Para sintaxe PowerShell, escolha entre `.ps1` e `.psm1`, approved verbs ou `CmdletBinding`: use `powershell-automation-monitor`.
- Para o payload WhatsApp, execução headless Node ou bootstrap `.bat`: use `nodejs-communications`.
- Para tipagem estática Python ou o padrão dos extratores Oracle: use `python-enterprise-standard`.
- Para layout do HTML de saída ou do Dashboard: use `html-css-enterprise-standard`.

## Related Skills
- `automation-runtime-safety` — guardrails de segredo, log e classificação de falha dentro do fluxo.
- `powershell-automation-monitor` — contratos do runtime PowerShell que implementa os entrypoints.
- `python-enterprise-standard` — extratores Oracle e services do Orchestrator consumidos por este contrato.
- `nodejs-communications` — quando o handoff termina em canal WhatsApp.
- `ai-native-development-standard` — quando a mudança de contrato precisa virar documentação viva.

## Non-Negotiable Rules
- Entrypoint das 6 automações registradas é `run.ps1` na própria pasta: `Receitas Bloqueadas/` (RB-01), `Montagem de Terceirizados/` (MT-02), `Receitas Emitidas/` (RE-03), `OBs Paradas Fase/` (OBP-04), `OBs Fluxo Sem Tingimento/` (OFST-06), `OBs Restricao Branco/` (ORB-07). Automação nova sem `run.ps1` só é aceitável se seguir o modelo de snapshot (ver Repo-Specific Constraints) — não invente um terceiro padrão de entrypoint.
- `Produção Beneficimento/` é a exceção ao contrato de entrypoint: não tem `run.ps1`. `src/beneficiamento/runner.py` orquestra Oracle -> SQLite com orçamento de 20 s; `snapshot_store.py` grava `Produção Beneficimento/snapshots/latest/`; a API lê apenas o snapshot. Não adicione `run.ps1` nem faça a API consultar Oracle direto — há `Produção Beneficimento/CLAUDE.md` próprio.
- Todo fluxo executado carrega identificador de execução de ponta a ponta: `ExecId` no runtime PowerShell, `trace_id` no runtime Python / Orchestrator. Linha de log sem esse campo reprova em `Tools/Test-LogEventSchema.ps1`.
- Reexecução é idempotente: o `run.ps1` lê o `*_state.json` do domínio antes de agir e só persiste sucesso após confirmação real do canal. Ordem obrigatória: calcular delta -> enviar -> confirmar -> persistir estado. Inverter essa ordem produz notificação duplicada na próxima execução.
- Migração de schema só via Alembic (`alembic upgrade head` roda no startup). `render_as_batch=True` em `Orchestrator/migrations/env.py` obriga `op.batch_alter_table` para alterar coluna ou tabela existente; `op.alter_column` / `op.drop_column` solto quebra no SQLite. O subagente `alembic-reviewer` audita PRs que tocam `migrations/versions/` ou `models.py`.
- Caminho absoluto (`C:\`, `D:\`) é proibido em qualquer camada do fluxo; use `$PSScriptRoot` ou caminho relativo à raiz. `Tools/Test-PortablePaths.ps1` bloqueia.

## Repo-Specific Constraints
- Camada de controle canônica: `Infrastructure/Start-Orchestrator.ps1`, `Infrastructure/MonitorAutomacoes.ps1`, `Infrastructure/Recover-Orchestrator.ps1`, `Infrastructure/Install-OrchestratorTask.ps1`. Todos (exceto `Install-OrchestratorTask.ps1`, que só registra a tarefa agendada) importam `lib/Lib-OrchestratorRuntime.psm1`, fonte única de: versão de runtime (lê `ORCHESTRATOR_VERSION` de `Orchestrator/app/constants.py`), parser de `.env` e encerramento de processo (`Get-CimInstance Win32_Process`, nunca `Get-Process`, que não expõe `CommandLine` no PowerShell 5.1).
- Fonte de verdade do motor: `Orchestrator/app/` (FastAPI + APScheduler + SQLite WAL) e `Orchestrator/worker.py` (consumidor da fila). Sessão SQLAlchemy fora do contexto FastAPI usa `session_scope`, nunca `SessionLocal()` direto.
- Estado de idempotência por domínio, já existente — não renomeie nem consolide: `Receitas Bloqueadas/receitas_state.json` + `email_state.json`; `Receitas Emitidas/receitas_state.json` + `delivery_state.json`; `OBs Paradas Fase/obs_state.json` + `obs_seen_state.json` + `delivery_state.json`; `OBs Fluxo Sem Tingimento/ofst_state.json`; `OBs Restricao Branco/orb_state.json`.
- Módulos PowerShell compartilhados a reusar antes de duplicar: `lib/Lib-Config.psm1`, `Lib-Logging.psm1`, `Lib-LogEvent.psm1`, `Lib-Process.psm1`, `Lib-Retry.psm1`, `Lib-Email.psm1`, `Lib-Idempotency.psm1`, `Lib-Oracle.psm1`, `Lib-OrchestratorRuntime.psm1`. Núcleo Python de extração Oracle: `lib/python/oracle_extract.py` (usado pelos 6 extratores de domínio), `oracle_client.py`, `oracle_retry.py` — não reimplemente fetch/serialize/hash.
- Manifesto obrigatório: cada automação registrada tem `automation.manifest.json` (o campo de severidade é `criticality`, em inglês). `POST /api/automations/preflight` valida antes de `create` / `update`; desde 31/07/2026 manifesto AUSENTE gera `incident` e BLOQUEIA `create` / `update`. `Tools/New-Automation.ps1` gera o manifesto a partir de `_Template/`.
- Logging estruturado: `docs/logging-standard.md` + `docs/log-event.schema.json`. Evento fora do schema reprova via `Tools/Test-LogEventSchema.ps1`. Correlação por `trace_id` (Python) / `ExecId` (PowerShell); criticidade, SLA e cadência canônicas em `docs/automation-criticality-map.md`.
- Acesso remoto do Orchestrator é via `tailscale serve`; o uvicorn segue em `127.0.0.1`. Não exponha porta nova nem faça o app escutar `0.0.0.0`.

## Validation
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-OrchestratorIntegrity.ps1 -RootPath .` quando a mudança tocar `Infrastructure/` ou `Orchestrator/`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-LogEventSchema.ps1 -RootPath .` quando alterar linha de log ou a propagação de `trace_id` / `ExecId`.
- `cd Orchestrator && ..\.venv\Scripts\pytest` (suíte padrão do CI) após mexer em `app/` ou `worker.py`; `..\.venv\Scripts\alembic upgrade head` após nova migração.
- Revisão manual: confirme que o identificador de execução entra no `run.ps1`, atravessa o runtime consumidor e aparece no log e no `*_state.json` relevantes.

## Troubleshooting
- Rastreabilidade perdida: ache a primeira camada que não recebe nem repassa `ExecId` / `trace_id` — em geral é um `Start-Process` sem repassar o argumento ou um subprocess Python sem herdar o ambiente.
- Notificação duplicada: revise a ordem no `run.ps1`; persistir o `*_state.json` antes da confirmação do canal é a causa mais comum.
- Migração falha no startup com erro de SQLite em `ALTER`: faltou `op.batch_alter_table`; veja `Orchestrator/CLAUDE.md` e acione `alembic-reviewer`.
- `create` / `update` de automação retorna 422: `POST /api/automations/preflight` achou manifesto ausente ou inválido; gere via `Tools/New-Automation.ps1`.
- Automação executou fora do orquestrador: confirme se é fluxo local legítimo (ex.: snapshot do Beneficiamento) ou quebra de contrato — o Orchestrator não registrou `trace_id` para ela.
- Reexecução após timeout diverge: compare o `*_state.json` persistido com `Orchestrator/Logs/` antes de mexer no retry.

## Pre-Delivery Checklist
- `ExecId` / `trace_id` propagado de ponta a ponta e presente no log final.
- Automação inicia pelo `run.ps1` correto (ou segue o modelo de snapshot, sem `run.ps1`, se for o Beneficiamento).
- Ordem calcular -> enviar -> confirmar -> persistir preservada; `*_state.json` do domínio não foi renomeado nem consolidado.
- Nenhuma migração com `alter` / `drop` fora de `op.batch_alter_table`.
- Nenhum caminho absoluto, nenhuma porta nova, uvicorn ainda em `127.0.0.1`.
- Manifesto válido para automação nova ou alterada (`preflight` verde).
