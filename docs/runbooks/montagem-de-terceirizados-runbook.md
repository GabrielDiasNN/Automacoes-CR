# Runbook Operacional: Montagem de Terceirizados

[⬅️ Voltar para o Hub Central](../../README.md)

## Ficha Técnica

- Componente: `Montagem de Terceirizados`
- Criticidade: `ALTA`
- SLA de recuperação: `3 horas`
- Horários de disparo: `Seg-Sáb, a cada 30 min, 05:00 às 22:00, em horários redondos`
- Área de negócio: `Faturamento / Controladoria / Expedição de Terceirizados`
- Entrypoint operacional: `Montagem de Terceirizados/run.ps1`

## Objetivo

Validar o vínculo fiscal entre NF e OB na montagem terceirizada, destacando divergências que podem gerar erro de estoque, atraso de expedição ou inconsistência fiscal.

## Dependências

- Oracle para extração via `extract_oracle.py`
- PowerShell para orquestração e logging
- Outlook COM para entrega do relatório

## Procedimento de Triagem

1. Confirmar o estado da automação no dashboard e verificar `/api/system/diagnostics`.
2. Abrir os logs da execução falha e confirmar se a falha está na extração Oracle, validação HTML ou entrega por Outlook.
3. Conferir `Montagem de Terceirizados/Logs/` e a presença dos artefatos HTML esperados.
4. Se a falha for transitória, usar **Requeue** no dashboard após validar que não há outra execução ativa no mesmo `queue_group`.

## Ação Manual de Contingência

1. Entrar em `Montagem de Terceirizados/`.
2. Executar `run.ps1`.
3. Confirmar no log se a extração Oracle, a validação e o envio por Outlook finalizaram com `Exit Code 0`.

## Sinais de Atenção

- Credenciais Oracle inválidas ou ambiente local stale.
- Divergência recorrente na quantidade de peças erradas por NF.
- Falha de Outlook COM na entrega do e-mail.
