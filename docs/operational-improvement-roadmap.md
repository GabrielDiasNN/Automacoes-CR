# Roadmap de Melhoria Operacional

Este roteiro mantém a direção escolhida: operação estável, fases pequenas e validação auditável.

## Fase 1 — Baseline e higiene

- Manter snapshot técnico por entrega relevante.
- Evitar alterações sobre trabalho local não relacionado sem inspeção.
- Manter `pytest` sem dependência de cache local no Orchestrator.

## Fase 2 — Observabilidade acionável

- Evoluir diagnósticos com impacto, prioridade e ação estruturada.
- Padronizar `contract_version`, `checks` mínimos de runtime e recovery em duas camadas como contrato público do diagnóstico.
- Priorizar achados de worker, scheduler, WAL, fila parada e falhas recorrentes.
- Manter `operator_actions` como contrato para botões do Dashboard.

## Fase 3 — Recovery e requeue

- Preservar `failure_reason`, `recovery_action`, `retry_count`, `max_retries` e `queue_group` em toda execução.
- Requeue deve exigir motivo operacional, respeitar limite de retry e gerar nova execução rastreável.
- Requeue deve bloquear concorrência no mesmo `queue_group` quando outro fluxo já estiver ativo.
- Falhas terminais devem orientar revisão de logs antes de nova tentativa, com classificação explícita para sessão WhatsApp expirada, falha de entrega de canal e erro genérico.

## Fase 4 — Console de operação

- Dashboard deve continuar clássico, denso e empresarial.
- Migrar ações fixas da interface para registro controlado (`data-action`) sem quebrar IDs e handlers legados exigidos pela SPA.
- Fluxos principais: executar, parar, reenfileirar, filtrar, abrir logs, recuperar worker, sincronizar agenda e executar checkpoint.
- Playwright deve ser a última validação quando a UI ou contrato front-back mudar.

## Fase 5 — Escala controlada

- Converter recorrências de incidentes em validadores, testes ou documentação viva.
- Avaliar retenção de logs, métricas históricas, alertas de saúde e backup/restore antes de qualquer troca de banco.
- Considerar evolução além de SQLite apenas com evidência de volume, contenção ou limite operacional real.
