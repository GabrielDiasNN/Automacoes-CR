# docs/oracle-schema/

Grafo de contexto e catálogo local do schema Oracle SGTPRD. Existe para que
nenhuma sessão precise reexplorar o dicionário de dados do Oracle (3.608
tabelas, 1.729 views, 74.095 colunas) para escrever SQL novo.

## O que é versionado e o que não é

| Arquivo | Versionado? | Como é gerado |
|---|---|---|
| `domain-map.md` | Sim | Curadoria humana; números e valores de domínio verificados contra `schema.db` |
| `schema-graph.md` | Sim | Curadoria humana (diagramas Mermaid); mesmo escopo de `domain-map.md` |
| `core-graph.json` | Sim | Gerado — objetos referenciados via `SGTPRD.<nome>` pelos `.sql` do repo + FKs entre eles |
| `schema.db` | **Não** (gitignored, ~35MB) | Gerado — catálogo completo do schema real |

`schema.db` nunca deve ser lido diretamente por um agente — é grande demais
para caber em contexto com proveito. A interface é sempre
`Tools/oracle_catalog.py`, que devolve só o que foi pedido.

## Como reconstruir

```powershell
# Catalogo completo (schema.db) — ~30s, uma conexao Oracle por query
.venv\Scripts\python Tools\build_oracle_catalog.py

# Build rapido, sem o texto das views
.venv\Scripts\python Tools\build_oracle_catalog.py --skip-view-source

# Regenerar core-graph.json a partir do schema.db + .sql do repo
# (nao ha script dedicado ainda; hoje e feito ad-hoc lendo schema.db e
# Tools/oracle_catalog.py usage — ver a secao "usage" do CLI)
```

Rode o rebuild quando o ERP mudar de forma perceptível (nova automação usa
tabela desconhecida, `Tools/oracle_catalog.py usage` reporta drift, ou uma
coluna/tabela documentada em `domain-map.md` não é encontrada pelo CLI).

## Como consultar

Ver `Tools/oracle_catalog.py --help` e a skill `oracle-schema-navigator`
(`.github/skills/oracle-schema-navigator/SKILL.md`) para o contrato completo.
Resumo:

```powershell
.venv\Scripts\python Tools\oracle_catalog.py table OB
.venv\Scripts\python Tools\oracle_catalog.py find "receita bloqueada"
.venv\Scripts\python Tools\oracle_catalog.py path OB ITENSPEDIDOGRADE
.venv\Scripts\python Tools\oracle_catalog.py distinct CLASSIFICACAO_COR CODIGO_CLASSIFICACAO --with-desc
.venv\Scripts\python Tools\oracle_catalog.py usage
```

## Nota sobre a rede até o Oracle

A conexão desta máquina ao Oracle de produção é derrubada
(`ORA-00028`/`ORA-03113`) após poucos segundos de uso contínuo,
independentemente de haver atividade — medido durante a construção deste
catálogo. Por isso `build_oracle_catalog.py` e os comandos online de
`oracle_catalog.py` abrem uma conexão nova por query (nunca reusam uma
conexão entre chamadas) e decoram cada chamada com o mesmo circuit
breaker + retry (`lib/python/oracle_retry.make_oracle_retry`) usado pelos
6 extratores de domínio em produção. Isso não é uma escolha de design — é
uma restrição desta rede, aprendida por tentativa e erro.

## MCP `oracledb` (via Antigravity) como alternativa pontual

Existe um servidor MCP (`oracledb`, MCP Toolbox for Databases) configurado
para o Antigravity/Gemini em `~/.gemini/config/mcp_config.json`, apontando
para o mesmo banco. Ele expõe `execute_sql`, `list_tables`, `get_query_plan`
e afins — útil para exploração ad-hoc ou para pegar um plano de execução real
vindo do banco, mas **não substitui o catálogo**: `execute_sql` roda o SQL
que você já escreveu, não ajuda a descobrir schema, e cada ferramenta MCP
declarada custa tokens em toda sessão mesmo sem uso. O caminho padrão
continua sendo o CLI. Se for registrar esse MCP no Claude Code, use escopo
local (nunca `.mcp.json` do projeto — a config do Antigravity traz usuário e
senha em texto puro) e mantenha-o desabilitado por padrão, ligando via `/mcp`
só quando precisar.
