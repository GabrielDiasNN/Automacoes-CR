---
name: oracle-sql-patterns
description: Use when implementing (not just navigating) Oracle SGTPRD queries -- CTEs reutilizaveis, filtros validados em produção, anti-patterns conhecidos, performance e templates por caso de uso, mais o fluxo de validação contra o catalogo local.
---

## Purpose

Fixar os padrões de SQL Oracle usados pelas automações do Hub de Automações.
O objetivo e que qualquer query nova siga os padrões validados em produção:
CTEs reutilizaveis, filtros corretos, anti-patterns conhecidos e performance
adequada para o volume real do schema SGTPRD (ate 13M linhas em uma única tabela).

## When to Use

Usar quando precisar implementar (não apenas navegar) queries Oracle:

- Escrever SQL novo para uma automação
- Otimizar query existente que está lenta
- Revisar padrão de join ou filtro em SQL existente
- Criar nova extração de dados baseada em OBs

Pre-requisito: ler `oracle-schema-navigator` para entender os domínios.

## Do Not Use When

- Para entender quais tabelas existem e seus domínios: use `oracle-schema-navigator`.
- Para configuração de conexão Python, oracle_extract.py e batch: use `python-enterprise-standard`.
- Para seguranca de runtime, bind variables e segredos: use `automation-runtime-safety`.

## CTEs Canonicas Reutilizaveis

### CTE: Fase Atual de OBs

```sql
-- Preferir a view: JOIN SGTPRD.VW_BNF_FASEATUALOB FAS ON FAS.NUMERO_OB = OB.NUMERO_OB
-- Se precisar implementar manualmente com ROW_NUMBER:
WITH FASE_ATUAL AS (
  SELECT NUMERO_OB, SEQUENCIA, CODIGO_FASE, STATUS, TIPO_DESTINO,
         ROW_NUMBER() OVER (PARTITION BY NUMERO_OB ORDER BY SEQUENCIA DESC) AS RN
  FROM SGTPRD.OB_FASES
  WHERE NUMERO_OB IN (SELECT NUMERO_OB FROM SGTPRD.OB WHERE SITUACAO = :situacao)
)
SELECT * FROM FASE_ATUAL WHERE RN = 1
```

### CTE: UP Associada a OBs

```sql
-- NUMEROORDEMREAL liga UP a OB (não se chama NUMERO_OB!)
WITH UP_OB AS (
  SELECT UPO.NUMEROORDEMREAL AS NUMERO_OB,
         UPO.NUMEROUP,
         UNP.DESCRICAO AS DS_UP
  FROM SGTPRD.UP_ORDEM_MVTO UPO
  JOIN SGTPRD.UNIDADE_PROGRAMACAO UNP ON UNP.NUMEROUP = UPO.NUMEROUP
  WHERE UPO.NUMEROORDEMREAL IN (:ob_list)
)
```

### CTE: Pedido Comercial de uma OB (cadeia completa)

```sql
WITH PEDIDO_OB AS (
  SELECT OB.NUMERO_OB, IPG.PEDIDO, IPG.ITEMPEDIDO
  FROM SGTPRD.OB OB
  JOIN SGTPRD.PEDPRODUCAOOB PPOB ON PPOB.NUMEROOB = OB.NUMERO_OB
  JOIN SGTPRD.OFORDENS OFO
    ON OFO.NUMEROPEDPRODUCAO = PPOB.NUMERO
   AND OFO.REDUZIDO = PPOB.REDUZIDO
  JOIN SGTPRD.OFPEDIDO OFP ON OFP.NUMEROOF = OFO.NUMEROOF
  JOIN SGTPRD.ITENSPEDIDOQTDES IPQ ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
  JOIN SGTPRD.ITENSPEDIDOGRADE IPG ON IPG.IDITEMPEDGRADE = IPQ.IDITEMPEDGRADE
  WHERE OB.NUMERO_OB = :numero_ob
    AND ROWNUM = 1
)
```

### CTE: Produto Decodificado

```sql
-- BD_BAS_MASCPRODACAB mapeia CODIGO_REDUZIDO para campos semanticos legiveis
WITH PROD_DEC AS (
  SELECT BP.CODIGO_REDUZIDO,
         LPAD(BP.ARTIGO, 3, '0')  AS ARTIGO_3D,
         LPAD(BP.COR, 2, '0')     AS COR_2D,
         BP.DESCR_COR,
         BP.ESTRUTURA,
         BP.DESCR_CLASSIF_COR
  FROM SGTPRD.BD_BAS_MASCPRODACAB BP
)
```

### CTE: OBs com Classificacao de Cor (ORB-07)

```sql
WITH OBS_COR AS (
  SELECT V.NUMERO_OB, V.CD_CLASSIFICACAO_COR
  FROM SGTPRD.VW_EXC_OB_PROD_CLASS_COR V
  WHERE V.CD_CLASSIFICACAO_COR IN (6, 9)  -- 6=BRANCO, 9=BRANCO 2 FIBRAS
)
```

## Filtros Validados em Produção

```sql
-- OBs Abertas
WHERE OB.SITUACAO = 'A'

-- Receitas bloqueadas atualmente
WHERE NVL(LRB.CBRECEITALIBERADA, 'N') = 'N'

-- Receitas ativas em produção
WHERE CR.PROCESSO_ATIVO_PRODU = 'S'

-- Deposito 95 (fio externo) com finalidades claras/branco
WHERE GPP.CODIGO_DEPOSITO = 95
  AND TFF.IDFINALIDADE IN (3, 4)
```

## Padrões de Subquery

```sql
-- MAX com ROWNUM (compativel Oracle 11g+)
(SELECT OB3.TOTAL_PECAS_CONFIRM
 FROM SGTPRD.OB_PRODUTO OB3
 WHERE OB3.NUMERO_OB = OBE.NUMERO_OB
 AND ROWNUM = 1)

-- DECODE (sintaxe Oracle legada)
DECODE(O3.TOTAL_PECAS_CONFIRM, 0,
  ROUND(O3.KILOS_PROGRAMADOS / NVL(PESO_PAD, 1), 0),
  O3.TOTAL_PECAS_CONFIRM)

-- CASE WHEN (mais legivel para lógica nova)
CASE WHEN SGTPRD.FNC_ESP_REC_PES(BASE.NUMERO_OB) = 0 THEN 'NAO' ELSE 'SIM' END AS PESADA

-- Agregacao de strings (padrão do projeto)
(SELECT SGTPRD.optstraggrsemvirgula(TRIM(UPPER(C.TEXTO)))
 FROM SGTPRD.OBSERVACAO C
 WHERE C.CODIGO = OBE.CODIGO_OBSERVACAO) AS OBS_OB
```

## Dicas de Performance

```sql
-- RUIM: full scan de 13M linhas
SELECT * FROM SGTPRD.GERAPECASPRODUTO WHERE CODIGO_REDUZIDO_PROD = :red

-- BOM: via GERAPECAORIGEMOB filtrado por OB
SELECT GPP.*
FROM SGTPRD.GERAPECAORIGEMOB GPO
JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.IDPECASPRODUTO = GPO.IDPECASPRODUTO
WHERE GPO.NUMERO_OB = :numero_ob
```

```python
# Sempre sincronizar arraysize e fetchmany para reduzir round-trips
cursor.arraysize = batch_size  # padrão do projeto: 5000
cursor.execute(sql, params)
rows = cursor.fetchmany(batch_size)  # 1 round-trip por batch
```

## Template: OBs com Status de Fase

```sql
SELECT
  OB.NUMERO_OB,
  OB.CODPRO_REDUZIDO,
  ITE.DESCRICAO AS DS_PRODUTO,
  OBF.SEQUENCIA,
  OBF.CODIGO_FASE,
  FFL.DESCRICAO AS DS_FASE,
  ENS.DESCRICAO AS DS_STATUS,
  OBF.CODIGO_PLACA AS NR_KANBAN
FROM SGTPRD.OB OB
JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OB.NUMERO_OB
JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = OB.CODPRO_REDUZIDO
LEFT JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
LEFT JOIN SGTPRD.VW_ENU_STATUS_OB_FASES ENS ON ENS.STATUS = OBF.STATUS
WHERE OB.SITUACAO = 'A'
  AND OBF.CODIGO_FASE IN (:fases)
ORDER BY OB.NUMERO_OB, OBF.SEQUENCIA
```

## Anti-Patterns Conhecidos

| Anti-Pattern                                                   | Problema                                | Correcao                                          |
| -------------------------------------------------------------- | --------------------------------------- | ------------------------------------------------- |
| `FROM SGTPRD.GERAPECASPRODUTO WHERE CODIGO_REDUZIDO_PROD = :x` | Full scan 13M                           | Filtrar via `GERAPECAORIGEMOB.NUMERO_OB` primeiro |
| `WHERE NUMERO_OB = '12345'` (string)                           | Conversao implicita, inibicao de índice | `WHERE NUMERO_OB = 12345` (NUMBER)                |
| `LISTAGG` sem limite                                           | ORA-01489 se resultado > 4000 chars     | Usar `SGTPRD.OPTSTRAGGRSEMVIRGULA`                |
| `SELECT *` em OB_FASES                                         | 1.3M x 30+ colunas = overhead           | Selecionar apenas colunas necessarias             |
| `NUMEROORDEMREAL = NUMERO_OB` no código                        | Confusao de nomes                       | `UP_ORDEM_MVTO.NUMEROORDEMREAL = OB.NUMERO_OB`    |

## Non-Negotiable Rules

- Toda query DEVE prefixar com `SGTPRD.<objeto>` - ausencia causa ORA-00942 em produção.
- Toda query DEVE usar bind variables (`:`) - nunca interpolação de valores em strings.
- Nunca acessar `GERAPECASPRODUTO` sem filtro previo via `GERAPECAORIGEMOB` ou `GERAPECADESTINOOB` - 13M linhas.
- O campo `NUMERO_OB` em `OB` corresponde a `NUMEROOB` em `PEDPRODUCAOOB` e a `NUMEROORDEMREAL` em `UP_ORDEM_MVTO` - não assumir nome igual.
- O campo `OB_FASES.NUMEROORDEMMOVIMENTO` liga a `MOVTO_RECEITA.NUMEROORDEM` - campos com nomes diferentes.
- Agregacao de strings: usar `SGTPRD.OPTSTRAGGRSEMVIRGULA` em vez de `LISTAGG` para compatibilidade legada.
- Conexão Oracle DEVE usar a lib `lib/python/oracle_extract.py` - nunca recriar a lógica de conexão.

## Pre-Delivery Checklist

- O SQL usa prefixo `SGTPRD.` em todos os objetos?
- Os parâmetros usam bind variables (`:`) em vez de interpolação?
- Se acessa `GERAPECASPRODUTO`: existe filtro previo por `NUMERO_OB`?
- Os campos `NUMERO_OB`/`NUMEROOB`/`NUMEROORDEMREAL` estão corretos para cada tabela?
- O campo `NUMEROORDEMMOVIMENTO` foi mapeado corretamente para `NUMEROORDEM`?
- A query foi testada com `--filter-automations` no extrator ou equivalente?
- O arquivo `.py` que usa o SQL passa no gate de lint da skill `ci-gates`?

## Related Skills

- `oracle-schema-navigator` para mapa de domínios, joins canonicos e convenções de nomenclatura SGTPRD.
- `python-enterprise-standard` para configuração de conexão Oracle, oracle_extract.py e batch.
- `automation-runtime-safety` para seguranca de runtime, tratamento de erros e logging estruturado.
- `enterprise-orchestration-contract` para o papel das queries dentro do fluxo de execucao.

## Repo-Specific Constraints

- SQLs das automações ficam nos arquivos `extract_oracle.py`, `extract_obs.py`, `extract_ofst.py`, `extract_orb.py`, `processar_receitas.py` de cada automação, e em `Produção Beneficimento/src/beneficiamento/contracts/_queries*.py`.
- Não espalhar SQL inline nos runners PowerShell nem nos routers FastAPI.
- CTEs complexas podem ser pre-definidas como strings em `contracts/_queries*.py` e importadas.
- Toda query nova deve passar pelo linter SQL da skill `ci-gates` antes do merge.

## Validation

Antes de considerar um SQL novo pronto, valide-o contra o catalogo/Oracle sem
executa-lo por completo — os dois comandos abaixo custam segundos e não tocam
dados:

```powershell
# Nomes e sintaxe (cursor.parse, não executa a query)
.venv\Scripts\python Tools\oracle_catalog.py check meu_arquivo.sql

# Plano de execucao (EXPLAIN PLAN, não executa a query) — confirma que não vai
# fazer full scan numa tabela grande antes de rodar de verdade
.venv\Scripts\python Tools\oracle_catalog.py explain meu_arquivo.sql

# Verificar governança de skills apos modificar esta skill
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SkillsGovernance.ps1 -BasePath .

# Executar testes de integracao Oracle (requer VPN/rede produtiva)
.venv\Scripts\pytest -m integracao --co -q

# Smoke test rapido: conectar e rodar 1 query simples
.venv\Scripts\python -c "from oracle_extract import resolve_oracle_credentials; print(resolve_oracle_credentials(None, 'test'))"
```

## Troubleshooting

- **ORA-01489 (result too long)**: substituir `LISTAGG` por `SGTPRD.OPTSTRAGGRSEMVIRGULA`.
- **ORA-00932 (inconsistent datatypes)**: NUMERO_OB eh NUMBER, não VARCHAR2 - remover aspas.
- **Query lenta em GERAPECASPRODUTO**: ver regra de performance acima - sempre filtrar por OB antes.
- **Campo não encontrado em OB_FASES**: `oracle_catalog.py cols OB_FASES --like <padrão>` confirma se existe e o nome exato.
- **NVL em campo DATE não funciona**: usar `COALESCE` ou garantir que o tipo do literal seja compativel.
- **ORA-00028 / ORA-03113 (sessao/conexão encerrada) ao rodar `sample`/`check`/`explain`**: a rede ate o Oracle desta máquina derruba conexoes continuas apos poucos segundos — normal, o comando ja tenta de novo automaticamente (mesmo retry dos extratores de produção); se persistir, rode de novo.
