# Runbook Operacional: Receitas Emitidas

[⬅️ Voltar para o Hub Central](../../README.md)

## Ficha Técnica

- Componente: `Receitas Emitidas`
- Criticidade: `MÉDIA`
- SLA de recuperação: `6 horas`
- Horário de disparo: `Sex às 07:05`
- Área de negócio: `Planejamento / Tinturaria / PCP`
- Entrypoint operacional: `Receitas Emitidas/run.ps1`

## Objetivo

Gerar e distribuir o relatório de receitas emitidas para apoiar o planejamento da cozinha de químicos e a sequência de tingimento.

## Dependências

- Oracle para extração via `extract_oracle.py`
- Python para geração do HTML adaptativo
- Outlook COM para distribuição do e-mail

## Procedimento de Triagem

1. Validar no dashboard se a automação ficou sem sucesso recente ou com atraso operacional.
2. Conferir `Receitas Emitidas/Logs/` para separar falha de extração Oracle, geração do HTML ou envio por Outlook.
3. Quando houver `Exit Code 2`, tratar como idempotência e não como falha operacional.
4. Reexecutar apenas se o último estado não tiver sido consolidado com sucesso.

## Ação Manual de Contingência

1. Entrar em `Receitas Emitidas/`.
2. Executar `run.ps1`.
3. Confirmar a geração do payload extraído, do HTML final e o envio do e-mail.

## Sinais de Atenção

- Timeouts ou instabilidade do Oracle.
- Drift de encoding entre PowerShell e Python no pipeline StdIO.

## Evidência de SLA (verificação periódica)

SLA declarado no manifesto: **360 minutos**. Última execução `SUCCESS` verificada em 05/07/2026 contra o banco real do Orchestrator: duração de **~0,2 min**, concluída em `03/07/2026 07:05:16` — dentro do SLA com folga ampla. Consulta usada (via `Orchestrator/automacoes.db`, somente leitura):
```sql
SELECT e.duration_seconds, e.finished_at FROM executions e
JOIN automations a ON a.id = e.automation_id
WHERE a.name = 'Receitas Emitidas' AND e.status = 'SUCCESS'
ORDER BY e.finished_at DESC LIMIT 1;
```

## Drill de Falha (simulado, isolado de produção)

Drill executado em 05/07/2026 contra uma cópia isolada em memória do schema real (nunca contra `automacoes.db` de produção nem disparando e-mail real), usando a config real desta automação (`max_retries=0`): injetada uma execução `ERROR` sintética e uma execução `SUCCESS` com duração 15 min acima do SLA (375 min), e chamadas as funções reais `collect_sla_breaches`/`check_sla_breaches` e `prepare_requeue`.

**Resultado:** SLA breach detectado corretamente (finding `WARN` gerado). Auto-retry **corretamente bloqueado** (`RequeueValidationError: Limite de retry excedido para esta execução: 0/0`) — comportamento esperado, pois `max_retries=0` é decisão deliberada do operador para esta automação (ver manifesto `RE-03`): falhas exigem intervenção manual via Dashboard/PowerShell (seção "Ação Manual de Contingência" acima), não recuperação automática.

Nota: RE-03 compartilha `queue_group="oracle"` com as outras 3 automações em produção — retries concorrentes do mesmo grupo são serializados por design.
- Falha de Outlook COM após geração correta do relatório.
