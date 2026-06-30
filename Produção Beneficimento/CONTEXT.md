# Contexto: Produção Beneficimento

## Objetivo de Negócio
Fornecer visibilidade operacional near-real-time da produção de Beneficiamento (tinturaria, acabamento, revisão) via snapshots Oracle → SQLite, consumidos pelo Dashboard e API do Orchestrator. Não é uma automação agendada com `run.ps1` — é um domínio orientado a snapshot com refresh contínuo via APScheduler.

## Arquitetura Snapshot-First
- **Oracle isolado:** toda comunicação Oracle passa exclusivamente por `src/beneficiamento/oracle.py`. Nenhum outro módulo abre conexão.
- **Runner:** `src/beneficiamento/runner.py` orquestra o ciclo Oracle → snapshot JSON → SQLite histórico, com orçamento rígido de 20s imposto pelo DBA.
- **Snapshots:** `snapshots/latest/` armazena `*.analytics.json` e `manifest.json`. A API **nunca** consulta Oracle diretamente — consome apenas esses arquivos.
- **Histórico:** `snapshots/beneficiamento_historico.db` (SQLite) mantém o histórico de produções para consultas de períodos passados.
- **Refresh automático:** jobs APScheduler `beneficiamento_live_diario` (~90s) e `beneficiamento_mensal_rollup` (~10min) em subprocesso isolado.
- **Refresh on-demand:** `POST /api/beneficiamento/refresh?period=diario|mensal`.

## Estrutura de Código
- `src/beneficiamento/core/` — lógica pura: coerções, métricas, schema, turnos (sem I/O).
- `src/beneficiamento/data/` — queries SQL, schema SQLite, writer idempotente.
- `src/beneficiamento/contracts/` — implementação canônica de overview e detail.
- `src/beneficiamento/oracle.py` — única interface Oracle.
- `src/beneficiamento/runner.py` — orquestrador de refresh.
- `src/beneficiamento/snapshot_store.py` — leitura/escrita de `snapshots/latest/`.

## Operação
- **Sem entrypoint `run.ps1`:** o refresh é controlado pelo Orchestrator via APScheduler, não por execução direta.
- **Health:** `GET /api/beneficiamento/health` expõe `reason_code`, `recommended_action` e `issues` para triagem.
- **Períodos:** apenas `diario` e `mensal` (semanal e anual removidos em v9.4.0).

---
*Domínio sob contrato de snapshot-first e orçamento Oracle de 20s desde Jun/2026.*
