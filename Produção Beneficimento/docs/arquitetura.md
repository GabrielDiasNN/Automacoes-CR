# Arquitetura do Beneficiamento

## Decisão

O Beneficiamento passa a ser um domínio dedicado dentro do repositório, consumido pelo Orchestrator por uma API `snapshot-first`. Essa decisão protege o Oracle: o Dashboard e os endpoints de leitura nunca fazem consulta ao banco em tempo real.

## Fluxo

1. O runner Python executa uma consulta parametrizada por período.
2. O resultado é transformado em `profile` e `analytics`.
3. Os arquivos são gravados de forma atômica em `snapshots/latest/`.
4. O Orchestrator lê os snapshots e expõe `/api/beneficiamento/dashboard`, `/health`, `/periods` e `/periods/{period}`.
5. O Dashboard renderiza KPI, ranking, qualidade, frescor e status operacional sem pressionar a conexão Oracle.

## Baseline Atual

Os snapshots promovidos em 31/05/2026 estavam com status `ok`:

| Período | Linhas | Colunas | Tempo Oracle | Observação |
| --- | ---: | ---: | ---: | --- |
| Diário | 349 | 95 | 0,1570s | Snapshot final promovido de `quality_diario.*` |
| Semanal | 5.192 | 80 | 0,7158s | Snapshot final promovido de `quality_semanal.*` |
| Mensal | 17.642 | 80 | 2,5509s | Snapshot final promovido de `quality_mensal.*` |
| Anual | 1.687 | 44 | 5,1442s | Snapshot final promovido de `quality_anual.*` |

Achado crítico: `oracle_timeout_applied=false` nos snapshots porque o Oracle Client local reportou versão 12.2, insuficiente para aplicar `call_timeout`. Por isso a arquitetura não depende só do driver: usa snapshots, janela temporal, binds, lock/corte externo e leitura sem Oracle.

## Campos de Alto Sinal

Manter prioridade para `STATUS_*`, `QT_KG`, `QT_MT`, `RENDIMENTO`, `EFIC_TEMPO`, `VELOCIDADE`, `MIN_REAL`, `MIN_PREV`, `ANO_SEM`, `LOCAL_PRODUCAO` e `NOME_UNIDADE_FABRIL`.

Campos constantes ou quase sem sinal devem ser removidos do payload público quando não forem necessários para KPI, Power BI ou análise Python.
