# Arquitetura do Beneficiamento

## Decisão

O Beneficiamento é um domínio dedicado dentro do repositório, consumido pelo Orchestrator por uma API local-first. Essa decisão protege o Oracle: o Dashboard e os endpoints de leitura nunca fazem consulta ao banco em tempo real.

## Fluxo

1. O runner Python executa uma consulta parametrizada por período.
2. O resultado é transformado em `profile`, `analytics` e registros históricos normalizados.
3. Os arquivos são gravados de forma atômica em `snapshots/latest/` e o histórico é consolidado em `snapshots/beneficiamento_historico.db`.
4. O Orchestrator lê o SQLite histórico e expõe `GET /api/beneficiamento/overview` como contrato V1 principal do Dashboard.
5. `GET /api/beneficiamento/detail` centraliza o drill-down de produto, máquina/fase, fase, turno e OB para o modal local da UI.
6. `GET /api/beneficiamento/historico` permanece para rastreabilidade compacta de OB/produto.
7. Contratos legados de snapshots podem continuar disponíveis para compatibilidade, mas a UI V1 não depende deles.
8. `GET /api/beneficiamento/health` consolida a leitura dos snapshots com causa operacional estruturada (`reason_code`), ação recomendada, `issues`, `summary`, `latest_period` e mapa determinístico de arquivos por período.

## Otimização do Histórico

O schema v2 separa o domínio em `core/`, `data/` e `contracts/`. A implementação de overview, detalhe e analytics vive em `contracts/`; `overview_v1.py` reexporta esses contratos somente para consumidores legados. O histórico SQLite mantém colunas tipadas e derivadas persistidas para acelerar os filtros mais usados pela UI:

- `TURNO_ID` e `TURNO_LABEL`
- `MAQUINA_KEY`
- `FASE_KEY`
- `CODIGO_KEY`

Esses campos são preenchidos no `salvar_historico`, que usa especificações declarativas e `executemany`. Consultas regulares projetam colunas tipadas; `DADOS_COMPLETOS` é lido apenas no detalhe com `include_raw=true`.

Ao detectar schema anterior ao v2, `init_db` recria a tabela para evitar backfill parcial ou dependência do blob. A base deve ser repopulada pelo runner retroativo antes da promoção operacional.

## Contrato V1 do Dashboard

`GET /api/beneficiamento/overview` aceita `dt_inicio`, `dt_fim`, `maquina`, `fase`, `turno`, `alternativo` e `q`.

Quando `dt_inicio` e `dt_fim` não são informados, o backend calcula a janela padrão como os últimos 30 dias encerrados em `MAX(DATA_FIM)` do SQLite. Isso evita drift por data do sistema quando o refresh não acompanha o dia corrente.

A resposta expõe:

- `generated_at`, `filters.effective`, `health`, `kpis`, `rankings`, `series`, `filter_options`, `turnos`, `tingimento` e `interaction`.
- `kpis`: OBs distintas, fases concluídas, KG, MT, eficiência de tempo, reprocesso KG, desvio em minutos e produtividade KG/h.
- `rankings`: gargalos por máquina/fase, fases críticas e produtos principais.
- `series`: volume diário e eficiência diária calculados no SQLite.
- `filter_options`: máquinas, fases, turnos e alternativos disponíveis no recorte.
- `turnos`: visão geral operacional do Beneficiamento por turno com volume, eficiência, reprocesso e produtividade.
- `tingimento`: bloco dedicado da fase `03 - TINGIMENTO`, com médias, percentuais e rankings por Alternativo e máquina.
- `interaction`: metadados mínimos de drill-down para a UI.

No baseline atual do domínio, a montagem direta do overview pelo módulo Python ficou na faixa de centenas de milissegundos para a base local promovida, com reaproveitamento do mesmo recorte filtrado para todos os blocos analíticos.

O indicador de tela deve ser chamado de **Eficiência de tempo**. Ele é proxy operacional calculado por `MIN_PREV / MIN_REAL * 100` e não deve ser apresentado como OEE industrial completo.

## Drill-down Operacional

`GET /api/beneficiamento/detail` aceita `target_type`, os filtros comuns do recorte e chaves do alvo como `alternativo`, `maquina`, `fase`, `turno` ou `ob`.

A resposta expõe:

- `target`: tipo e rótulo do item clicado.
- `summary`: resumo operacional do alvo.
- `records`: lista curada com campos de operação e rastreabilidade.
- `trace`: timeline agrupada por OB.
- `pagination`: paginação do detalhe.
- `raw_records`: payload bruto original somente quando `include_raw=true`.

## Normalização de Turno

O turno de operação deve ser extraído preferencialmente de `TURNO_DESC` e, quando necessário, reconstruído a partir de `TURNO_PROD`. O contrato público não deve depender mais de `turno`/`TURNO` legados se esses campos estiverem vazios no histórico.

## Baseline Atual

Os snapshots promovidos em 31/05/2026 estavam com status `ok`:

| Período | Linhas | Colunas | Tempo Oracle | Observação |
| --- | ---: | ---: | ---: | --- |
| Diário | 349 | 95 | 0,1570s | Snapshot final promovido de `quality_diario.*` |
| Semanal | 5.192 | 80 | 0,7158s | Snapshot final promovido de `quality_semanal.*` |
| Mensal | 17.642 | 80 | 2,5509s | Snapshot final promovido de `quality_mensal.*` |
| Anual | 1.687 | 44 | 5,1442s | Snapshot final promovido de `quality_anual.*` |

Achado crítico: `oracle_timeout_applied=false` nos snapshots porque o Oracle Client local reportou versão 12.2, insuficiente para aplicar `call_timeout`. Por isso a arquitetura não depende só do driver: usa snapshots, janela temporal, binds, lock/corte externo e leitura sem Oracle.

No estado atual, `attention` no health não deve mais ser tratado como alerta genérico. O contrato passou a diferenciar explicitamente:

- `snapshot_missing`: arquivos não promovidos ou ausentes;
- `snapshot_invalid`: arquivos presentes, porém incompletos ou inválidos;
- `snapshot_stale`: snapshot acima da idade operacional esperada;
- `historico_partial_failure`: refresh terminou sem consolidar o histórico SQLite;
- `quality_blocked` ou `quality_attention`: risco vindo do quality gate;
- `oracle_timeout_unapplied`: snapshot utilizável, mas com risco operacional no client Oracle.

## Campos de Alto Sinal

Manter prioridade para `STATUS_*`, `QT_KG`, `QT_MT`, `MIN_REAL`, `MIN_PREV`, `EFIC_TEMPO`, `REPROCESSO`, `ANO_SEM`, máquina, fase, produto, artigo, cor, `LOCAL_PRODUCAO`, `UND_FAB` e `NOME_UNIDADE_FABRIL`.

Campos constantes ou quase sem sinal devem ser removidos do payload público quando não forem necessários para KPI, Power BI ou análise Python.
