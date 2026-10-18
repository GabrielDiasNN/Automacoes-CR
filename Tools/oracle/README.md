# Tools/oracle/

Ferramentas Python do acervo e do catálogo Oracle (SGTPRD). Rodar sempre da raiz do repositório, com o `.venv` do projeto: `.venv\Scripts\python Tools\oracle\<ferramenta>.py`.

| Ferramenta | Para quê |
|---|---|
| `oracle_catalog.py` / `build_oracle_catalog.py` | Consultar e reconstruir o catálogo local do schema (`docs/oracle-schema/schema.db`) |
| `gerar_core_graph.py` | Gerar `docs/oracle-schema/core-graph.json` |
| `validar_sql_oracle.py` | Guard + parse + execução de 1 linha das consultas do acervo; define `CONSULTAS_ROOT` (fonte única do caminho do acervo) |
| `validar_partes_oracle.py` | Conferir trechos críticos de consultas pesadas |
| `medir_sql_oracle.py` / `auditar_acervo_sql.py` | Medir o custo do fetch completo e varrer o acervo |
| `comparar_equivalencia.py` | Provar que uma reescrita devolve a mesma saída |
| `gerar_catalogo_sql.py` | Gerar `docs/oracle-schema/consultas/CATALOGO_QUERIES.md` (`--check` roda no pytest) |
| `guard_sql.py` | Wrapper versionado do guard SQL (aceita CTE com lista de colunas); delega ao guard canônico da skill `oracle-sql`, que é a fonte única da regra de `GROUP BY GROUPING SETS (` |
| `mcp_server.py` | Servidor MCP nativo JSON-RPC 2.0 (STDIO) para Oracle (ERP SGT / Data Center Unifique) com driver adaptativo Thin/Thick, WAN tuning, watchdog e proteção Read-Only |
| `Install-InstantClient19c.ps1` | Instala o Instant Client 19c a partir de um ZIP já baixado (não baixa nada), replica `tnsnames.ora`/`sqlnet.ora` e atualiza `ORACLE_CLIENT_LIB_DIR`, `ORACLE_CLIENT_PATH` e `TNS_ADMIN` no `.env` (backup fora do repositório). `-DryRun` mostra o plano |

Fluxo completo de validação: `docs/oracle-schema/consultas/README.md`. Saídas soltas de execução vão em `Tools/evidencias/` (ignorada pelo git).
