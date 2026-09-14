---
name: oracle-schema-navigator
description: Use when writing SQL against Oracle SGTPRD, navigating the ERP schema domains (OB, OB_FASES, GERAPECASPRODUTO, receitas, pecas, comercial), identifying canonical joins, or building automations that query the Oracle database.
---

## Purpose

Fornecer o mapa do schema Oracle SGTPRD para que qualquer agente (Gemini, Codex, Claude)
possa escrever SQL correto sem precisar explorar o dicionario de dados do Oracle manualmente
a cada sessao. O schema real tem 3.608 tabelas, 1.729 views e 74.095 colunas (medido em
13/09/2026); esta skill documenta os ~55 objetos criticos para as automações ativas E aponta
para o catalogo local (`Tools/oracle_catalog.py`) quando a pergunta e sobre outro objeto.

## When to Use

Ativar sempre que precisar:

- Escrever uma nova query SQL contra o Oracle SGTPRD
- Entender quais tabelas/views existem num domínio de negocio
- Identificar joins corretos entre tabelas do ERP
- Criar ou modificar automações que consultam o Oracle

## Do Not Use When

- Para padrões de implementação Python (imports, oracle_extract, batch): use `python-enterprise-standard`.
- Para seguranca de runtime, segredos e logging estruturado: use `automation-runtime-safety`.
- Para padrões de SQL com CTEs e anti-patterns detalhados: use `oracle-sql-patterns`.

## Bootstrap de Contexto

**Contrato de economia de tokens — não leia o catalogo inteiro.** O schema real
tem 3.608 tabelas; carregar isso em contexto e o oposto do que esta skill existe
para evitar. Em vez disso:

1. Se o objeto está no `domain-map.md` (~55 tabelas das automações ativas), leia
   a secao do domínio la — e a via mais barata.
2. Para qualquer outro objeto, ou para confirmar um fato pontual (coluna existe?
   tipo? PK? FK?), rode o CLI contra o catalogo local — cada chamada custa
   dezenas de linhas, não megabytes:
   ```powershell
   .venv\Scripts\python Tools\oracle_catalog.py table <NOME>
   .venv\Scripts\python Tools\oracle_catalog.py find "<termo>"
   .venv\Scripts\python Tools\oracle_catalog.py path <DE> <PARA>
   .venv\Scripts\python Tools\oracle_catalog.py cols <TABELA> --like <PADRAO>
   ```
3. Para a topologia dos objetos das automações em JSON (mesmo escopo do
   `domain-map.md`, formato programatico): `docs/oracle-schema/core-graph.json`.
4. Para diagramas Mermaid navegaveis: `docs/oracle-schema/schema-graph.md`.

O catalogo (`docs/oracle-schema/schema.db`, ~35MB, gitignored) e gerado por
`Tools/build_oracle_catalog.py` e nunca deve ser lido diretamente — sempre via
o CLI. Se `table`/`find`/`path` falharem com "Catalogo não encontrado", rode o
build (ver Repo-Specific Constraints).

**Domain-map.md pode estar desatualizado sem aviso** — ja aconteceu (ver nota
em `docs/oracle-schema/domain-map.md` sobre `CLASSIFICACAO_COR`). Para qualquer
valor de domínio (código -> descricao) usado numa decisao de negocio, confirme
com `oracle_catalog.py distinct <TABELA> <COLUNA> --with-desc` antes de confiar
no texto curado.

## Mapa Rapido de Domínios

| Domínio                | Tabelas Centrais                                                                                             |
| ---------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Produção/OB**        | `OB`, `OB_FASES`, `OB_PRODUTO`, `FASES_FLUXO`                                                                |
| **Programacao**        | `UNIDADE_PROGRAMACAO`, `UP_ORDEM_MVTO`                                                                       |
| **Pecas**              | `GERAPECASPRODUTO` (13M!), `GERAPECAORIGEMOB`, `GERAPECADESTINOOB`                                           |
| **Qualidade/Receitas** | `MOVTO_RECEITA`, `CADASTRO_RECEITAS`, `LIGA_CADREC_ITEMREC`, `LABRECEITA_BLOQUEADA`                          |
| **Classificacao**      | `CLASSIFICACAO_COR` (1=CLARA, 6=BRANCO, 9=BRANCO 2 FIBRAS), `COR_FINALIDADE`                                 |
| **Estoque/Cadastro**   | `ITENS_ESTOQUE`, `BD_BAS_MASCPRODACAB`, `PESSOASFJ`                                                          |
| **Comercial/Pedidos**  | `PEDPRODUCAOOB` - `OFORDENS` - `OFPEDIDO` - `ITENSPEDIDOQTDES` - `ITENSPEDIDOGRADE` - `ITENSPEDIDOCOMERCIAL` |
| **Engenharia**         | `ENG_PRODG_ACABADO`, `MAQUINA`, `VARIANTE_DESENHO`                                                           |

## Joins Canonicos

```sql
-- 1. OB_FASES - OB (sempre por NUMERO_OB)
JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OB.NUMERO_OB

-- 2. Fase Atual (sem subquery MAX)
JOIN SGTPRD.VW_BNF_FASEATUALOB FAS ON FAS.NUMERO_OB = OB.NUMERO_OB

-- 3. UP - OB (campo diferente: NUMEROORDEMREAL != NUMERO_OB)
JOIN SGTPRD.UP_ORDEM_MVTO UPO ON UPO.NUMEROORDEMREAL = OBF.NUMERO_OB

-- 4. Movimentacao de receita (campos com nomes DIFERENTES!)
JOIN SGTPRD.MOVTO_RECEITA M ON M.NUMEROORDEM = OBF.NUMEROORDEMMOVIMENTO

-- 5. Cadeia comercial completa (OB - Pedido)
JOIN SGTPRD.PEDPRODUCAOOB PPOB ON PPOB.NUMEROOB = OB.NUMERO_OB
JOIN SGTPRD.OFORDENS OFO ON OFO.NUMEROPEDPRODUCAO = PPOB.NUMERO AND OFO.REDUZIDO = PPOB.REDUZIDO
JOIN SGTPRD.OFPEDIDO OFP ON OFP.NUMEROOF = OFO.NUMEROOF
JOIN SGTPRD.ITENSPEDIDOQTDES IPQ ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
JOIN SGTPRD.ITENSPEDIDOGRADE IPG ON IPG.IDITEMPEDGRADE = IPQ.IDITEMPEDGRADE

-- 6. Pecas de origem - GERAPECASPRODUTO
JOIN SGTPRD.GERAPECAORIGEMOB GPO ON GPO.NUMERO_OB = OB.NUMERO_OB
JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.IDPECASPRODUTO = GPO.IDPECASPRODUTO

-- 7. Decodificador de produto (ARTIGO, COR, ESTRUTURA)
LEFT JOIN SGTPRD.BD_BAS_MASCPRODACAB BP ON BP.CODIGO_REDUZIDO = OB.CODPRO_REDUZIDO

-- 8. Status legivel de OB_FASES
JOIN SGTPRD.VW_ENU_STATUS_OB_FASES ENS ON ENS.STATUS = OBF.STATUS

-- 9. Lookup de usuario
LEFT JOIN SGTPRD.VW_SIS_SENHA_USUARIO VSU ON VSU.CODREDUSUARIO = LCR.USUARIO_ALTEROU
```

## Volumes de Produção

| Tabela              | Linhas | Aviso                                               |
| ------------------- | ------ | --------------------------------------------------- |
| `GERAPECASPRODUTO`  | 13.4M  | Sempre filtrar antes via GERAPECAORIGEMOB/DESTINOOB |
| `GERAPECAORIGEMOB`  | 5.1M   | Filtrar por NUMERO_OB                               |
| `GERAPECADESTINOOB` | 5.1M   | Filtrar por NUMERO_OB                               |
| `UP_ORDEM_MVTO`     | 1.5M   | Filtrar por NUMEROORDEMREAL                         |
| `MOVTO_RECEITA`     | 1.3M   | Filtrar por NUMEROORDEM                             |
| `OB_FASES`          | 1.3M   | Filtrar por NUMERO_OB                               |
| `OB`                | 177K   | Filtrar por SITUACAO ou data                        |
| `ITENS_ESTOQUE`     | 24.9K  | Master pequeno, JOIN seguro                         |
| `FASES_FLUXO`       | 38     | Tabela referência, JOIN sempre seguro               |

## Funcoes Built-in Uteis

| Funcao                               | Uso                                |
| ------------------------------------ | ---------------------------------- |
| `SGTPRD.FNC_ESP_REC_PES(:ob)`        | 0=não pesada, 1=pesada             |
| `SGTPRD.optstraggrsemvirgula(texto)` | Agrega strings sem virgula         |
| `SGTPRD.optstraggr(texto)`           | Agrega com separador               |
| `SGTPRD.WM_CONCAT(coluna)`           | Concatenacao compativel com legado |

## Regras Criticas de SQL

```
SEMPRE:
  - Prefixar com SGTPRD.<objeto>
  - Usar bind variables (:param), nunca interpolação
  - Fechar conexão apos uso (context manager)
  - Usar arraysize >= batch_size para reduzir round-trips

NUNCA:
  - Acessar GERAPECASPRODUTO sem filtro previo por NUMERO_OB
  - Assumir que NUMERO_OB = NUMEROOB (depende da tabela!)
  - SELECT * em tabelas de alto volume
  - Esquecer o prefixo SGTPRD. (causa ORA-00942)
  - Interpolar valores em strings SQL
```

## Conexão Python (padrão do projeto)

```python
from oracle_extract import resolve_oracle_credentials, init_thick_mode, fetch_all, serialize_rows

creds = resolve_oracle_credentials(log, exec_id)
if not creds:
    return
init_thick_mode(creds, log, exec_id)

sql = """
SELECT OB.NUMERO_OB, OBF.STATUS
FROM SGTPRD.OB OB
JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OB.NUMERO_OB
WHERE OB.SITUACAO = :situacao
"""
cols, rows = fetch_all(creds, sql, exec_id, log, params={"situacao": "A"})
data = serialize_rows(cols, rows)
```

## Non-Negotiable Rules

- Sempre ler `docs/oracle-schema/domain-map.md` antes de escrever SQL novo.
- Sempre prefixar objetos com `SGTPRD.` - ausencia causa ORA-00942 em produção.
- Sempre usar bind variables - nunca interpolar valores em strings SQL.
- Nunca acessar `GERAPECASPRODUTO` sem filtro previo por `NUMERO_OB` (13M linhas).
- Conexão Oracle DEVE usar `lib/python/oracle_extract.py` - nunca recriar a lógica.

## Pre-Delivery Checklist

- O domínio do problema foi identificado em `domain-map.md`?
- Os joins usam os campos corretos (especialmente `NUMEROORDEMREAL`, `NUMEROORDEMMOVIMENTO`)?
- O prefixo `SGTPRD.` está em todos os objetos SQL?
- Bind variables foram usadas em vez de interpolação?
- Para queries em tabelas grandes (>1M linhas): existe filtro seletivo no WHERE?

## Related Skills

- `oracle-sql-patterns` para CTEs, templates SQL e anti-patterns de implementação.
- `python-enterprise-standard` para padrões de conexão Oracle via oracle_extract.py.
- `automation-runtime-safety` para seguranca de runtime, bind variables e logging.
- `ai-native-development-standard` para atualizar documentação viva apos mudancas no schema.

## Repo-Specific Constraints

- Camada curada (versionada): `docs/oracle-schema/domain-map.md`, `schema-graph.md`,
  `core-graph.json`. Camada completa (gitignored, ~35MB): `docs/oracle-schema/schema.db`.
- Para reconstruir o catalogo apos mudancas no ERP: `.venv\Scripts\python Tools\build_oracle_catalog.py`
  (usa `lib/python/oracle_extract.py` + `oracle_retry.py` — mesma conexão/retry dos 6 extratores de produção;
  a rede ate o Oracle e instavel o bastante para exigir uma conexão nova por query, ja tratado no script).
- Mirrors desta skill estão em `.gemini/skills/oracle-schema-navigator/` e `.claude/skills/oracle-schema-navigator/` (junctions, não editar).
- O schema real (3.608 tabelas) so e consultavel via `Tools/oracle_catalog.py` contra `schema.db`; as skills documentam apenas os ~55 objetos usados pelas automações ativas.
- Automações usam a lib em `lib/python/oracle_extract.py` - nunca recriar a lógica de conexão.
- Ha tambem um MCP `oracledb` (MCP Toolbox for Databases) configurado no Antigravity
  (`~/.gemini/config/mcp_config.json`), mesmo banco. Pode ser registrado no Claude Code em
  escopo local para exploracao ad-hoc, mas o CLI continua sendo o caminho padrão — o MCP
  não sabe navegar o schema, so executa o SQL que voce ja escreveu.

## Validation

```powershell
# Verificar se as skills estão com mirrors sincronizados
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/New-SkillMirrors.ps1

# Validar governança completa de skills
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SkillsGovernance.ps1 -BasePath .

# Confirmar que o catalogo local responde (sem ir ao Oracle)
.venv\Scripts\python Tools\oracle_catalog.py table OB

# Reconstruir o catalogo contra o Oracle (online, ~30s)
.venv\Scripts\python Tools\build_oracle_catalog.py
```

## Troubleshooting

- **ORA-00942**: prefixo SGTPRD. ausente. Adicionar `SGTPRD.` antes do objeto.
- **ORA-01031**: usuario sem privilegio em `ALL_*` views. Verificar permissoes com DBA.
- **Resultado vazio em GERAPECASPRODUTO**: filtro por CODIGO_REDUZIDO_PROD sem passar antes por GERAPECAORIGEMOB - ver "Volumes de Produção" acima.
- **Campo NUMEROORDEMREAL não encontrado**: está em `UP_ORDEM_MVTO`, não em `OB` - ver "Joins Canonicos".
- **Erro de connexao Thick Mode**: verificar `ORACLE_CLIENT_PATH` no `.env` e se o Instant Client está instalado.
