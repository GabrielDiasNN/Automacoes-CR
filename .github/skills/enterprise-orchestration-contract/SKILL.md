---
name: enterprise-orchestration-contract
description: Use when defining or changing ExecId propagation, idempotency, state transitions, entrypoints, and cross-runtime execution contracts between PowerShell, Python, Node.js, Infrastructure scripts, and the Orchestrator.
---

## Purpose
Definir o contrato transversal de execucao do hub para que automacoes possam ser disparadas, repetidas, monitoradas e auditadas sem quebrar rastreabilidade ou duplicar efeitos colaterais.

## When to Use
- Use ao alterar `run.ps1` de qualquer automacao.
- Use ao mexer em `Infrastructure/`, `Orchestrator/` ou em handoffs entre PowerShell, Python e Node.js.
- Use ao criar ou revisar arquivos de estado como `*_state.json`, `delivery_state.json` e mecanismos de supressao de duplicidade.
- Use ao definir regras de reexecucao, retomada ou timeout operacional.

## Do Not Use When
- Nao use para politicas de segredo, encoding ou severidade de log; nesses casos use `automation-runtime-safety`.
- Nao use para detalhe de sintaxe PowerShell, organizacao de modulo ou approved verbs; nesses casos use `powershell-automation-monitor`.
- Nao use para estilo visual do dashboard ou HTML de saida; nesses casos use `html-css-enterprise-standard`.

## Related Skills
- `automation-runtime-safety` para seguranca e guardrails de falha.
- `powershell-automation-monitor` para contratos do runtime PowerShell que implementa os entrypoints.
- `nodejs-communications` quando o handoff envolver envio por WhatsApp ou bootstrap `.bat`.

## Non-Negotiable Rules
- Todo fluxo executavel deve ter `ExecId` rastreavel de ponta a ponta quando fizer parte da esteira corporativa.
- O entrypoint de cada automacao continua sendo `run.ps1` dentro da propria pasta da automacao.
- Reexecucao deve ser segura: o fluxo nao pode duplicar notificacao, corromper estado ou marcar sucesso sem confirmacao real do canal.
- Transicoes de estado devem ser atomicas o bastante para impedir falso positivo de entrega ou processamento.
- Caminhos devem permanecer relativos ao repositorio ou ao diretorio da automacao; o contrato nao admite path absoluto embutido.

## Repo-Specific Constraints
- Trate `Infrastructure/Start-Orchestrator.ps1`, `Infrastructure/MonitorAutomacoes.ps1` e `Infrastructure/Recover-Orchestrator.ps1` como pontos canonicos da camada de controle.
- Trate `Orchestrator/app/` e `Orchestrator/worker.py` como a fonte de verdade da API, persistencia e execucao assistida.
- Use os `run.ps1` de `Receitas Bloqueadas/`, `Receitas Emitidas/`, `Montagem de Terceirizados/` e `OBs Paradas Fase/` como padrao de entrypoint por automacao.
- Preserve a estrategia de idempotencia via arquivos como `receitas_state.json`, `delivery_state.json` e similares existentes em cada dominio.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-OrchestratorIntegrity.ps1 -RootPath .` quando a mudanca tocar `Infrastructure/` ou `Orchestrator/`.
- Revise manualmente se o `ExecId` entra no `run.ps1`, atravessa o runtime consumidor e aparece em logs ou estados relevantes.

## Troubleshooting
- Se o fluxo perder rastreabilidade, identifique a primeira camada que deixa de receber ou propagar `ExecId`.
- Se houver duplicidade de notificacao, revise a ordem entre calculo de estado, confirmacao do canal e persistencia do `*_state.json`.
- Se uma automacao passar fora do orquestrador, confirme se isso e realmente um fluxo local legitimo ou uma quebra do contrato corporativo.
- Se a reexecucao falhar apos timeout, compare os estados persistidos com os logs do `Orchestrator/Logs/` antes de alterar o retry.

## Pre-Delivery Checklist
- Confirme que `ExecId` continua propagado de ponta a ponta.
- Confirme que a automacao continua iniciando pelo `run.ps1` correto.
- Confirme que a estrategia de estado previne duplicidade.
- Confirme que nenhum path absoluto ou bypass do orquestrador foi introduzido.
