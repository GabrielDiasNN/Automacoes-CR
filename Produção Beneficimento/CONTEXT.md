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

## Estrutura de Código e Dados
- `src/beneficiamento/core/` — lógica pura: coerções, métricas, schema, turnos (sem I/O).
- `src/beneficiamento/data/` — queries SQL, schema SQLite, writer idempotente.
- `src/beneficiamento/contracts/` — implementação canônica de overview e detail.
- `src/beneficiamento/oracle.py` — única interface Oracle.
- `src/beneficiamento/runner.py` — orquestrador de refresh.
- `src/beneficiamento/snapshot_store.py` — leitura/escrita de `snapshots/latest/`.
- `sql/templates/` — SQL de **runtime** consumido pelo runner (`bnf_producao_beneficiamento_detalhado.sql`); não mover nem renomear sem ajustar `settings.py`. O acervo de consultas de referência **não** mora aqui: está em `../docs/oracle-schema/consultas/` (13 pastas por processo têxtil, catalogadas em `CATALOGO_QUERIES.md`, gerado por `Tools/oracle/gerar_catalogo_sql.py`), estruturado com atomicidade (1 query/arquivo), sem DML mutável e com desmonte de views pesadas em favor de tabelas físicas indexadas (`BD_BNF_PRODUCAO_FASE`, `GERAPECASPRODUTO`, `OB`).

## Operação
- **Sem entrypoint `run.ps1`:** o refresh é controlado pelo Orchestrator via APScheduler, não por execução direta.
- **Health:** `GET /api/beneficiamento/health` expõe `reason_code`, `recommended_action` e `issues` para triagem.
- **Períodos:** apenas `diario` e `mensal` (semanal e anual removidos em v9.4.0).
- **Consultas Operacionais Ad-hoc:** devem ser referenciadas por `pasta/arquivo.sql` (ver `docs/oracle-schema/consultas/CATALOGO_QUERIES.md`), respeitando o guardrail Zero DML e o budget de tempo de execução.

---
*Domínio sob contrato de snapshot-first, governança de parque SQL unificado e orçamento Oracle de 20s.*
