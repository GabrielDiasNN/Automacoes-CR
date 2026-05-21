# Execução do Plano de Melhoria do Orchestrator

> **Versão:** v9.1.0 | **Atualizado:** 2026-05-21

## Resumo

Este documento registra a execução incremental do plano de melhoria do Orchestrator com prioridade em estabilidade, fases pequenas e manutenção da arquitetura SQLite + Alembic.

## Baseline Estabilizado

- `constants.py` alinhado ao baseline `9.1.0`, contrato `2026.05.20.1` e revisão Alembic `a5b212d4418f`.
- Artefatos runtime de banco de teste e scripts temporários de correção foram adicionados ao `.gitignore`.
- A regra de `anchor_time` foi centralizada em `Orchestrator/app/schemas/schedule_rules.py`, usada tanto pelo preview quanto pelo APScheduler.
- O diagnóstico operacional agora expõe execuções `RUNNING` acima de `max_runtime_minutes` em `queue.running_over_runtime`.

## Arquitetura e Estabilidade

- A evolução preserva os contratos públicos existentes; os novos campos são aditivos.
- O `schema_version` operacional passa a representar a revisão Alembic ativa, evitando drift entre banco e aplicação.
- O Dashboard mostra a contagem de execuções ativas acima do limite na aba Sistema, reduzindo investigação manual em incidentes de fila.

## Limites Para Manter SQLite

Manter SQLite + Alembic enquanto estes indicadores permanecerem controlados:

- WAL abaixo de 64 MB na operação normal e abaixo de 256 MB em pico.
- Tempo de claim de fila sem acúmulo persistente de execuções `PENDING` acima de 15 minutos.
- Ausência de contenção recorrente em escrita ou locks de banco durante execução concorrente.
- Banco operacional com crescimento compatível com a política de retenção.

Preparar avaliação de PostgreSQL apenas se dois ou mais indicadores acima virarem achados recorrentes em `/api/system/diagnostics`.

## Validação Esperada

- `pytest` do Orchestrator para agenda, diagnósticos, contratos e fluxos críticos.
- `Tools/Test-SourceEncoding.ps1 -RootPath .`
- `Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance`
- Playwright por último quando houver mudança front-back servida em `/dashboard/`.

## Runbook Operacional

- Referência oficial de incidente/rollback: `docs/orchestrator-incident-rollback-runbook.md`.
