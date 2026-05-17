---
name: nodejs-communications
description: Use when changing WhatsApp automation, headless communication flows, or BAT/CMD bootstrap layers implemented in Node.js without expanding Node into general orchestration responsibilities.
---

## Purpose
Restringir e padronizar o uso de Node.js no hub para comunicacao automatizada, bootstrap local e fluxos headless que dependem de confirmacao real antes de encerrar a execucao.

## When to Use
- Use ao alterar `Receitas Bloqueadas/sendWhatsApp.js`, `Receitas Bloqueadas/RunWhatsApp.bat` ou `lib/WhatsApp-Core.js`.
- Use ao revisar fluxo de envio por WhatsApp, confirmacao de ack, retry de canal ou inicializacao via `.bat`/`.cmd`.
- Use ao definir como PowerShell ou Python chamam um processo Node.js que atua apenas como ponte de comunicacao.

## Do Not Use When
- Nao use Node.js para orquestracao geral do hub, controle de jobs ou ownership de estado corporativo; nesses casos use `enterprise-orchestration-contract`.
- Nao use para governanca detalhada de PowerShell, monitoramento central ou modulos compartilhados `.psm1`; nesses casos use `powershell-automation-monitor`.
- Nao use para e-mail, dashboard ou outras apresentacoes HTML; esses dominios pertencem a outras skills.

## Related Skills
- `enterprise-orchestration-contract` para definir quem dispara o canal e como o estado de entrega e preservado.
- `automation-runtime-safety` para segredos, logs e classificacao de falhas.
- `powershell-automation-monitor` quando o fluxo Node for encapsulado por scripts PowerShell.

## Non-Negotiable Rules
- Use `async/await` e trate falhas explicitamente; nao esconda erro de canal atras de callback implicito ou processo zumbi.
- Nao marque entrega como concluida antes da confirmacao real do canal ou ack persistido.
- Scripts `.bat` e `.cmd` devem sair com `errorlevel` coerente para que o chamador consiga detectar sucesso ou falha.
- Limite a responsabilidade do Node ao canal de comunicacao e ao bootstrap necessario; ownership de agendamento, estado corporativo e governanca permanece fora dele.
- Nao introduza segredo hardcoded em JS, BAT ou JSON auxiliar.

## Repo-Specific Constraints
- Use `Receitas Bloqueadas/sendWhatsApp.js` e `lib/WhatsApp-Core.js` como referencia do canal WhatsApp atual.
- Preserve a integracao com `Receitas Bloqueadas/RunWhatsApp.bat` quando houver bootstrap por shell legado de entrada.
- Mantenha a persistencia de entrega alinhada aos arquivos de estado do dominio, em vez de criar estado paralelo apenas no Node.
- Quando o Node for chamado por PowerShell, devolva saida e codigo de retorno que permitam correlacao com `ExecId` no fluxo superior.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` apos alterar contratos do canal.
- Valide manualmente o fluxo entre `RunWhatsApp.bat`, `sendWhatsApp.js` e o chamador PowerShell para confirmar propagacao de erro e encerramento limpo.
- Revise se os arquivos alterados continuam compativeis com o controle de estado existente em `Receitas Bloqueadas/`.

## Troubleshooting
- Se o processo Node terminar sem confirmar envio, revise primeiro o ponto em que o ack e persistido antes de olhar timeout.
- Se o BAT aparentar sucesso com falha no Node, revise `errorlevel`, `exit code` e repasse de stderr/stdout.
- Se o canal estiver assumindo responsabilidades de orquestracao, mova a decisao de fluxo para PowerShell ou Orchestrator e mantenha o Node como ponte.
- Se faltar rastreabilidade, garanta que o chamador injeta contexto suficiente e que o Node o devolve nos logs ou erros.

## Pre-Delivery Checklist
- Confirme que Node continua restrito ao dominio de comunicacao/bootstrap.
- Confirme que envio so e marcado como concluido apos ack real.
- Confirme que o processo retorna codigo de saida util ao chamador.
- Confirme que o fluxo continua alinhado ao estado persistido do dominio.
