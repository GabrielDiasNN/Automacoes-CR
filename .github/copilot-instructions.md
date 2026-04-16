# Copilot Instructions — Automacoes Hub

Você está trabalhando em um repositório de automações operacionais críticas.

## Contexto
- O projeto usa PowerShell como orquestrador principal.
- O monitor central é `MonitorAutomacoes.ps1`.
- Algumas automações entram por `TriggerAutomation.vbs` e outras por `run.ps1`.
- A lógica de negócio ainda passa por Excel/VBA + Power Query.
- Oracle é a principal fonte de dados.
- Outlook COM é usado para e-mail.
- Node.js é usado no bridge de WhatsApp.

## Regras obrigatórias
- Preserve compatibilidade com o fluxo atual.
- Nunca faça rewrite total.
- Prefira diffs pequenos e reversíveis.
- Preserve `ExecId` ponta a ponta.
- Preserve logs humanos existentes.
- Se criar log estruturado, faça em paralelo.
- Não altere sem necessidade exit codes, retry, lock, idempotência ou modo PAIRING/AUTO.
- Não remova entrypoints legados sem camada de compatibilidade.

## Prioridades técnicas
1. Timeout e proteção contra travamento.
2. Clareza operacional de erros.
3. Watchdog e observabilidade.
4. Validação de configuração.
5. Governança e rollback simples.

## Estilo de resposta esperado
Sempre responder neste formato:

Objetivo:
[uma frase]

Arquivos:
- [arquivo]
- [arquivo]

Plano:
- [ação]
- [ação]
- [ação]

Riscos:
- [risco]
- [risco]

Validação:
- [comando/check]
- [comando/check]

Rollback:
- [como desfazer]

## O que evitar
- mudanças amplas sem necessidade
- refactor junto com migração grande
- trocar stack inteira
- remover VBA/Excel de uma vez
- respostas longas e genéricas

## Antes de concluir qualquer tarefa
- indique os arquivos tocados
- explique o menor teste seguro
- informe impacto operacional
- descreva rollback
