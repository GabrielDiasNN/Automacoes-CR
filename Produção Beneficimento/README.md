# Produção Beneficimento

Domínio dedicado para a API de produção, snapshots analíticos e histórico SQLite de Beneficiamento.

## Contrato

- A API do Orchestrator é local-first: requisições `GET` leem snapshots locais ou o SQLite histórico em `snapshots/beneficiamento_historico.db` e não abrem conexão Oracle.
- O contrato operacional V1 do Dashboard é `GET /api/beneficiamento/overview`, com filtros `dt_inicio`, `dt_fim`, `maquina`, `fase`, `turno`, `alternativo` e `q`.
- Quando datas não são informadas, `/overview` usa a janela de 30 dias encerrada em `MAX(DATA_FIM)` do SQLite, não a data do sistema.
- `GET /api/beneficiamento/detail` concentra o drill-down por produto, máquina/fase, fase, turno e OB para o modal da UI, com paginação e `include_raw` opcional.
- `GET /api/beneficiamento/historico` permanece como busca compacta de rastreabilidade de OB/produto.
- `GET /api/beneficiamento/health` mantém o resumo por períodos e agora também expõe `reason_code`, `recommended_action`, `issues`, `summary`, `latest_period` e `snapshot_files` para que uma atenção operacional nunca fique opaca.
- Turno operacional deve ser normalizado a partir de `TURNO_DESC` e `TURNO_PROD` do payload histórico; a UI não deve depender mais de `turno`/`TURNO` legados quando esses campos estiverem vazios.
- O Oracle só deve ser acessado por refresh controlado via `analise_producao_diaria_beneficiamento.py` ou módulos em `src/beneficiamento/`.
- O orçamento operacional é rígido: `BENEFICIAMENTO_ORACLE_TIMEOUT_MS=18000` e corte externo de 19 segundos, abaixo do limite de 20 segundos aplicado pelo DBA.
- Se o `call_timeout` do Oracle Client não for aplicado, o snapshot continua utilizável, mas a API marca o período como `attention`.
- O runner agora expõe o estado final do refresh como `ok`, `attention` ou `partial_failure`; falha na escrita do histórico SQLite não deve ficar silenciosa.
- O health agora distingue explicitamente `snapshot_missing`, `snapshot_invalid`, `snapshot_stale`, `historico_partial_failure`, `quality_blocked`, `quality_attention`, `oracle_timeout_unapplied`, `snapshot_no_data` e `healthy`.
- O histórico v2 lê colunas tipadas e índices por padrão; `DADOS_COMPLETOS` só é desserializado quando `include_raw=true`.
- A migração para o schema v2 recria `beneficiamento_historico.db`. Após promover o código, execute a recarga retroativa descrita no runbook.
- O acervo SQL de consultas de chão de fábrica e inteligência industrial em `docs/oracle-schema/consultas/` é governado e catalogado em [CATALOGO_QUERIES.md](../docs/oracle-schema/consultas/CATALOGO_QUERIES.md): consultas atômicas organizadas em 13 pastas por domínio industrial, escritas sobre tabelas físicas indexadas em vez de views legadas pesadas. Inventário e status de validação no Oracle ficam só no catálogo, gerado por `Tools/oracle/gerar_catalogo_sql.py`.

## Estrutura

- `src/beneficiamento/`: código Python modular do domínio.
- `src/beneficiamento/core/`: coerções, aliases, turnos e métricas compartilhadas.
- `src/beneficiamento/data/`: schema SQLite, writer idempotente e consultas tipadas.
- `src/beneficiamento/contracts/`: imports canônicos de overview, detail e tingimento.
- `sql/templates/`: SQL de runtime do runner (`bnf_producao_beneficiamento_detalhado.sql`). O acervo de consultas (13 pastas, `01_beneficiamento_tingimento` a `13_utilitarios_snippets`) vive em [`docs/oracle-schema/consultas/`](../docs/oracle-schema/consultas/README.md), com o catálogo mestre [CATALOGO_QUERIES.md](../docs/oracle-schema/consultas/CATALOGO_QUERIES.md).
- `sql/templates/bnf_producao_beneficiamento_detalhado.sql`: consulta mestra analítica consumida pelo runner Python via binds `:dt_inicio` e `:dt_fim`.
- `docs/oracle-schema/consultas/11_views_referencia_sgt/`: definições DDL de views corporativas preservadas para auditoria e conferência.
- `docs/oracle-schema/consultas/12_manutencao_dml_restrito/`: scripts de manutenção em quarentena de segurança (Zero DML).
- `snapshots/latest/`: última versão aprovada dos arquivos `*.analytics.json`. O `*.profile.json` não é mais gerado nem servido (ver [runbook](docs/runbook-refresh.md)).
- `snapshots/beneficiamento_historico.db`: base SQLite histórica consumida por `/api/beneficiamento/overview`, `/detail` e `/historico`.
- `docs/`: arquitetura, baseline e runbook operacional.

## Refresh manual

```powershell
.\.venv\Scripts\python.exe '.\Produção Beneficimento\analise_producao_diaria_beneficiamento.py' --period diario
```

Períodos válidos: `diario` e `mensal`. `semanal` e `anual` foram descontinuados (ver [runbook](docs/runbook-refresh.md)).
O JSON final do runner inclui `status` e `refresh_status`, e a escrita no histórico SQLite aparece em `snapshot.historico_write_status`.

A política de cadência do refresh, o orçamento do Oracle e a validação pós-refresh estão no [runbook de refresh](docs/runbook-refresh.md).

## Candidata de faturamento mensal por cliente

A [V2.2](../docs/oracle-schema/consultas/09_pcp_kpis_gestao/pcp_faturamento_mensal_cliente_prazo_expedicao_v2_2.sql) preserva o contrato funcional da V2.1 e está **não promovida por instabilidade operacional** (última série integral 4/5). A V2.1 permanece preservada e não promovida.
