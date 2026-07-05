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

O e-mail operacional de divergências também expõe a placa kanban por OB quando o Oracle retornar `NR_KANBAN`, para acelerar a localização física do lote na triagem.

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
- Placa kanban ausente (`N/A`) no e-mail indica ausência do valor na origem Oracle, não falha de renderização do HTML.
- Falha de Outlook COM na entrega do e-mail.

## Evidência de SLA (verificação periódica)

SLA declarado no manifesto: **180 minutos**. Última execução `SUCCESS` verificada em 05/07/2026 contra o banco real do Orchestrator: duração de **~0,1 min**, concluída em `04/07/2026 22:00:16` — dentro do SLA com folga ampla. Consulta usada (via `Orchestrator/automacoes.db`, somente leitura):
```sql
SELECT e.duration_seconds, e.finished_at FROM executions e
JOIN automations a ON a.id = e.automation_id
WHERE a.name = 'Montagem de Terceirizados' AND e.status = 'SUCCESS'
ORDER BY e.finished_at DESC LIMIT 1;
```

## Drill de Falha (simulado, isolado de produção)

Drill executado em 05/07/2026 contra uma cópia isolada em memória do schema real (nunca contra `automacoes.db` de produção nem disparando WhatsApp/e-mail/Outlook real): injetada uma execução `ERROR` sintética e uma execução `SUCCESS` com duração 15 min acima do SLA (195 min), e chamadas as funções reais `collect_sla_breaches`/`check_sla_breaches` e `prepare_requeue`.

**Resultado:** SLA breach detectado corretamente; execução `ERROR` elegível para auto-retry (nova execução `PENDING` criada). Confirma que o mecanismo de recuperação automática funciona para esta automação.

Nota: MT-02 compartilha `queue_group="oracle"` com as outras 3 automações em produção — retries concorrentes do mesmo grupo são serializados por design.
