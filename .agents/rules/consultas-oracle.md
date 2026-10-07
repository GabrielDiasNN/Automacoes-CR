---
trigger: glob
globs: docs/oracle-schema/consultas/**
---

# Regra de Workspace: Acervo de Consultas Oracle

Aplica-se ao acervo em `docs/oracle-schema/consultas/` (catálogo, `NN_*` e evidência de validação). Visão geral, dono e regra de promoção: `docs/oracle-schema/consultas/README.md`.

## Governança do Acervo de Consultas SQL

- **Organização por Domínio:** as consultas SQL vivem em 13 pastas temáticas canônicas (`01_beneficiamento_tingimento` a `13_utilitarios_snippets`), catalogadas em `CATALOGO_QUERIES.md`.
- **Catálogo gerado:** `CATALOGO_QUERIES.md` é produzido por `Tools/oracle/gerar_catalogo_sql.py` (inventário do disco, `OBJETIVO:`/`TIPO:` do cabeçalho, binds do SQL, status de `docs/oracle-schema/consultas/validacao_status.json`). Nunca editar à mão; após adicionar/alterar SQL, validar, regerar com `--evidencia` e conferir com `--check`. Contagens e status não são repetidos em outros documentos.
- **Atomicidade Estrita:** cada arquivo `.sql` das pastas de consulta deve conter exatamente 1 consulta; arquivos multi-query são proibidos. Exceção: roteiros manuais de `12_manutencao_dml_restrito/` (ver `AVISO_SEGURANCA.md`).
- **Zero DML Guardrail:** scripts de manutenção com `UPDATE`/`DELETE` residem exclusivamente em `12_manutencao_dml_restrito/` e nunca devem ser executados em rotinas automáticas de produção.
- **Performance e Schema Físico:** consultas de produção devem priorizar tabelas físicas indexadas (`BD_BNF_PRODUCAO_FASE`, `GERAPECASPRODUTO`, `OB`, etc.) evitando views legadas pesadas, e aplicar filtros temporais indexados e, quando ajudar, CTEs com `/*+ MATERIALIZE */` para respeitar o budget de execução do Oracle. A materialização é decidida caso a caso e validada no Oracle: em `MOV_RETALHO_OB` (`qld_monitoramento_nf_entrada_ciclo_completo.sql`) o hint dispara `ORA-00979` no Oracle 12c, por isso ela fica sem `MATERIALIZE` (ver CHANGELOG 1.3.102). Em consultas de genealogia física multigeracional (`GERAPECAORIGEMOB`, `GERAPECADESTINOOB`, `GERAPECAORIGEM`), aplicar obrigatoriamente a arquitetura de duas fases (expansão recursiva de ordens com `CYCLE` + materialização em `UniversoOrdens` + junções com `USE_NL`), evitando Hash Joins globais que disparam `ORA-00028` / Resource Manager kill.
- **Encoding:** todos os arquivos `.sql` e `.md` devem ser mantidos estritamente em `UTF-8 sem BOM`.

