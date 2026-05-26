# Execução do Plano de Melhoria do Orchestrator

> **Versão:** v9.3.2 | **Atualizado:** 2026-05-25

## Resumo

Este documento registra a execução incremental do plano de melhoria do Orchestrator com prioridade em estabilidade, fases pequenas e manutenção da arquitetura SQLite + Alembic, agora expandido com catálogo governado e visão de portfólio operacional.

## Baseline Estabilizado

- `constants.py` alinhado ao baseline `9.3.2`, contrato `2026.05.25.1` e revisão Alembic `20260524_01`.
- O worker agora grava ownership em `executions` com `claimed_at`, `worker_instance_id` e `worker_pid`.
- O Orchestrator mantém snapshots operacionais em `system_health_snapshots`, com coleta a cada 5 minutos e retenção de 30 dias.
- O diagnóstico operacional agora expõe `trend_summary`, `slo_breaches` e `queue.orphaned_running`.
- O runtime agora formaliza o baseline operacional em `GET /api/system/baseline`, em `diagnostics.operational_baseline` e em `history.baseline_status`, usando thresholds únicos para worker, fila, WAL e ownership.
- `POST /api/automations/preflight` passou a ser a validação única de cadastro antes de `create/update`, normalizando canais e confirmando o entrypoint real.
- O portfólio governado cruza `automation.manifest.json`, documentação e cadastro runtime em `GET /api/portfolio/health` e `GET /api/portfolio/drift`.
- O overview principal agora replica `portfolio.summary` em `GET /api/system/overview.portfolio`, permitindo promover drift, docs pendentes e runtime não reconciliado a sinal operacional visível no Dashboard.
- O preflight administrativo agora deve bloquear `create/update` quando a pasta já estiver governada e o payload divergir de `automation.manifest.json` ou quando faltarem runbook, README, CONTEXT, entrypoint ou smoke tests declarados.
- O scaffold oficial de novas automações deve reduzir pendências logo na origem: manifesto com owner/fila/SLA/criticidade inicial, runbook coerente e smoke test mínimo já versionável.
- O dashboard principal agora expõe criticidade, SLA, drift, documentação e dependências do catálogo governado.
- Artefatos runtime de banco de teste e scripts temporários de correção foram adicionados ao `.gitignore`.
- A regra de `anchor_time` foi centralizada em `Orchestrator/app/schemas/schedule_rules.py`, usada tanto pelo preview quanto pelo APScheduler.
- O diagnóstico operacional agora expõe execuções `RUNNING` acima de `max_runtime_minutes` em `queue.running_over_runtime`.

## Arquitetura e Estabilidade

- A evolução preserva os contratos públicos existentes; os novos campos são aditivos.
- O `schema_version` operacional passa a representar a revisão Alembic ativa, evitando drift entre banco e aplicação.
- O Dashboard mostra a contagem de execuções ativas acima do limite na aba Sistema, reduzindo investigação manual em incidentes de fila.
- Ownership do worker permite distinguir execução longa legítima de execução órfã após falha de processo ou troca de instância.
- O histórico operacional reduz dependência de logs para detectar recorrência de backlog, pressão de WAL e heartbeat instável.
- O catálogo governado reduz drift entre diretório de automação, documentação obrigatória e cadastro operacional no Orchestrator.

## Limites Para Manter SQLite

Manter SQLite + Alembic enquanto estes indicadores permanecerem controlados:

- WAL abaixo de 64 MB na operação normal e abaixo de 256 MB em pico.
- Tempo de claim de fila sem acúmulo persistente de execuções `PENDING` acima de 15 minutos.
- Ausência de contenção recorrente em escrita ou locks de banco durante execução concorrente.
- Banco operacional com crescimento compatível com a política de retenção.

Preparar avaliação de PostgreSQL apenas se dois ou mais indicadores acima virarem achados recorrentes em `/api/system/diagnostics`.

## Validação Esperada

- `pytest` do Orchestrator para agenda, diagnósticos, contratos e fluxos críticos.
- `pytest tests/test_portfolio.py -q` para validar saúde e drift do catálogo governado.
- `GET /api/system/history?hours=24` para confirmar persistência dos snapshots operacionais.
- `GET /api/system/baseline` para validar o resumo único do baseline operacional.
- `POST /api/automations/preflight` para validar `script_path`, agenda e canais antes de mutações administrativas.
- `GET /api/portfolio/health` e `GET /api/portfolio/drift` para confirmar leitura do portfólio governado.
- `Tools/Test-SourceEncoding.ps1 -RootPath .`
- `Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance`
- Playwright por último quando houver mudança front-back servida em `/dashboard/`.

## Runbook Operacional

- Referência oficial de incidente/rollback: `docs/orchestrator-incident-rollback-runbook.md`.
