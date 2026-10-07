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

## Referências (carregue só o que o caso pede)

| Arquivo | Quando ler |
|---|---|
| `references/ctes-canonicas.md` | Precisa de fase atual de OB, UP, pedido comercial, produto decodificado, classificação de cor, genealogia de peças, rastreio de lote de NF ou janelas temporais longas: copie a CTE do caso |
| `references/filtros-e-subqueries.md` | Vai filtrar por status/fase/destino/reprocesso ou montar subquery de tupla atômica, turno principal ou prazo comercial |
| `references/performance-e-anti-patterns.md` | Consulta lenta, `ORA-00028`, ou revisão final de SQL novo: tabela completa de anti-patterns e protocolo de benchmark |

## Regras de Ouro (resumo dos anti-patterns mais caros)

- Nunca `TRUNC`/`TO_CHAR`/`TRIM`/`TO_DATE` sobre a coluna em `WHERE`/`JOIN`: faixa direta na coluna. Datas NUMBER `YYYYMMDD` (ex.: `DATA_DA_ENTRADA_PECA`) comparam com `TO_NUMBER(TO_CHAR(data, 'YYYYMMDD'))`.
- Janela de data **dentro** de cada CTE de fato, nunca só no calendário final: senão a CTE agrega o histórico inteiro (`BD_PRD_MOVPROD` tem ~56 mi linhas).
- CTEs de **um consumidor** cada, unidas por `LEFT JOIN`: o CBO as funde num plano pior — `/*+ MATERIALIZE */` em cada uma. Com **2+ consumidores**, não force o hint (o CBO já materializa).
- `BD_BNF_PRODUCAO_FASE` não tem índice por `NUMERO_OB`: nada de `EXISTS` correlacionado por OB; monte o conjunto pequeno antes e cheque uma vez com `IN`.
- Agregue movimentos antes de juntar cadastro (`ITENS_ESTOQUE`, `ENGEITEMESTONIVELGE9`, `LIKE`).
- `x / NULLIF(y, 0)` sempre; `LISTAGG(... ON OVERFLOW TRUNCATE)`; `NUMERO_OB` é NUMBER (sem aspas).
- "0 linhas" não é conformidade; `FETCH FIRST N` em auditoria trunca anomalias em silêncio.
- Unidade de tempo: `OB`/`OB_FASES` a partir de 01/01/1996; `UNIDADE_PROGRAMACAO` a partir de 30/12/1899.
- A rede derruba a sessão em ~4-6 s: a consulta inteira precisa caber nisso.

## Related Skills

- `oracle-schema-navigator` para mapa de domínios, joins canonicos e convenções de nomenclatura SGTPRD.
- `python-enterprise-standard` para configuração de conexão Oracle, oracle_extract.py e batch.
- `automation-runtime-safety` para seguranca de runtime, tratamento de erros e logging estruturado.
- `enterprise-orchestration-contract` para o papel das queries dentro do fluxo de execucao.

## Non-Negotiable Rules

- Toda query DEVE prefixar com `SGTPRD.<objeto>` - ausencia causa ORA-00942 em produção.
- Toda query DEVE usar bind variables (`:`) - nunca interpolação de valores em strings.
- Nunca acessar `GERAPECASPRODUTO` sem filtro seletivo indexado - 13M linhas: por OB via `GERAPECAORIGEMOB`/`GERAPECADESTINOOB`, ou por faixa de `DATA_DA_ENTRADA_PECA` (NUMBER `YYYYMMDD`, índice `GRPCPROD_INDIDATAENTRPECA`; compare com `TO_NUMBER(TO_CHAR(data, 'YYYYMMDD'))`, nunca aplique `TO_DATE` na coluna).
- O campo `NUMERO_OB` em `OB` corresponde a `NUMEROOB` em `PEDPRODUCAOOB` e a `NUMEROORDEMREAL` em `UP_ORDEM_MVTO` - não assumir nome igual.
- O campo `OB_FASES.NUMEROORDEMMOVIMENTO` liga a `MOVTO_RECEITA.NUMEROORDEM` - campos com nomes diferentes.
- Agregacao de strings: `LISTAGG(... ON OVERFLOW TRUNCATE)`; `SGTPRD.OPTSTRAGGR*` só ao manter código legado que já o usa (ver anti-pattern de `LISTAGG`).
- Conexão Oracle DEVE usar a lib `lib/python/oracle_extract.py` - nunca recriar a lógica de conexão.

## Repo-Specific Constraints

- SQLs das automações ficam nos arquivos `extract_oracle.py`, `extract_obs.py`, `extract_ofst.py`, `extract_orb.py`, `processar_receitas.py` de cada automação, e em `Produção Beneficimento/src/beneficiamento/contracts/_queries*.py`.
- Não espalhar SQL inline nos runners PowerShell nem nos routers FastAPI.
- CTEs complexas podem ser pre-definidas como strings em `contracts/_queries*.py` e importadas.
- Toda query nova do acervo (`docs/oracle-schema/consultas/`) passa por `Tools/oracle/validar_sql_oracle.py --file <arquivo>` (guard + parse + execução de 1 linha) e entra no catálogo com `gerar_catalogo_sql.py --evidencia <saida.json>`; o `--check` do catálogo roda no pytest do CI. O `.py` que embute SQL passa pelo ruff/bandit/mypy descritos na skill `ci-gates` (não existe linter de SQL no CI).

## Validation

Antes de considerar um SQL novo pronto, valide-o contra o catalogo/Oracle sem
executa-lo por completo — os dois comandos abaixo custam segundos e não tocam
dados:

```powershell
# Nomes e sintaxe (cursor.parse, não executa a query)
.venv\Scripts\python Tools\oracle\oracle_catalog.py check meu_arquivo.sql

# Plano de execucao (EXPLAIN PLAN, não executa a query) — confirma que não vai
# fazer full scan numa tabela grande antes de rodar de verdade
.venv\Scripts\python Tools\oracle\oracle_catalog.py explain meu_arquivo.sql

# Custo real: fetch completo, mediana de 5 execuções (conexão nova em cada), dump do resultado
.venv\Scripts\python Tools\oracle\medir_sql_oracle.py meu_arquivo.sql --runs 5 --dump base.json --out base.report.json

# Depois da reescrita: mesma medição + decisão contra a baseline (MELHORA/NEUTRO/PIOR)
.venv\Scripts\python Tools\oracle\medir_sql_oracle.py meu_arquivo.sql --runs 5 --dump nova.json --baseline base.report.json

# Provar que a reescrita não mudou o resultado (exige --chaves ou --metricas)
.venv\Scripts\python Tools\oracle\comparar_equivalencia.py --controle base.json --candidata nova.json --chaves NUMERO_OB

# Varredura do acervo: FALHA, LENTA, VAZIA, TETO_ATINGIDO...
.venv\Scripts\python Tools\oracle\auditar_acervo_sql.py --out varredura.json

# Verificar governança de skills apos modificar esta skill
pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SkillsGovernance.ps1 -BasePath .

# Executar testes de integracao Oracle (requer VPN/rede produtiva)
.venv\Scripts\pytest -m integracao --co -q

# Smoke test rapido: conectar e rodar 1 query simples
.venv\Scripts\python -c "from oracle_extract import resolve_oracle_credentials; print(resolve_oracle_credentials(None, 'test'))"
```

Limites do ambiente (medidos em 29/09/2026): o usuário de leitura **não enxerga** `V$SQL`,
`V$MYSTAT` nem `DBMS_XPLAN.DISPLAY_CURSOR` (ORA-00942), então `buffer_gets` não existe e a métrica
de performance é o tempo de parede do fetch completo; `EXPLAIN PLAN` é só hipótese. O banco é
Oracle 12.2 Standard Edition, o client é 12.2 (sem `call_timeout`) e a rede derruba sessões longas
(`ORA-00028`/`DPY-1001`, em ~4 a 6 s): abra conexão nova por medição e repita em queda de rede.

## Troubleshooting

- **ORA-01489 (result too long)**: acrescentar `ON OVERFLOW TRUNCATE` ao `LISTAGG`.
- **ORA-00932 (inconsistent datatypes)**: NUMERO_OB eh NUMBER, não VARCHAR2 - remover aspas.
- **Query lenta em GERAPECASPRODUTO**: ver regra de performance acima - sempre filtrar por OB antes.
- **Campo não encontrado em OB_FASES**: `oracle_catalog.py cols OB_FASES --like <padrão>` confirma se existe e o nome exato.
- **NVL em campo DATE não funciona**: usar `COALESCE` ou garantir que o tipo do literal seja compativel.
- **ORA-00028 / ORA-03113 (sessao/conexão encerrada)**:
  - *Em comandos rápidos (`sample`/`check`/`explain`)*: a rede até o Oracle desta máquina derruba conexões contínuas após poucos segundos — o comando já tenta de novo automaticamente (mesmo retry dos extratores); se persistir, rode de novo.
  - *Em queries analíticas com range longo (ex.: faturamento 12+ meses sob concorrência)*: o CBO acumula recursos e a sessão é morta intermitentemente na 4ª/5ª execução. Mitigação arquitetural validada: aplicar a **Decomposição Temporal Disjunta via UNION ALL** na CTE de fatos (`[DT_INICIO, DT_CORTE) UNION ALL [DT_CORTE, DT_FIM)`), que reduz o custo unitário por branch e eleva o sucesso a 100% (5/5).
  - *Em CTEs de parâmetros consumidas por múltiplos fatos analíticos*: se o CBO materializar a CTE de parâmetros (`TEMP TABLE TRANSFORMATION`), ele desativa o pushdown de predicados temporais nas transacionais massivas (`BD_PRD_MOVPROD`), gerando varreduras desnecessárias de milhões de linhas e estouro de sessão (`ORA-00028`). Solução: injetar `/*+ INLINE */` diretamente na CTE de parâmetros e forçar `/*+ LEADING(J UPR) USE_NL(UPR) */` nos blocos consumidores.
## Pre-Delivery Checklist

- O SQL usa prefixo `SGTPRD.` em todos os objetos?
- Os parâmetros usam bind variables (`:`) em vez de interpolação?
- Se acessa `GERAPECASPRODUTO`: existe filtro previo por `NUMERO_OB`?
- Os campos `NUMERO_OB`/`NUMEROOB`/`NUMEROORDEMREAL` estão corretos para cada tabela?
- O campo `NUMEROORDEMMOVIMENTO` foi mapeado corretamente para `NUMEROORDEM`?
- A query foi testada com `--filter-automations` no extrator ou equivalente?
- O arquivo `.py` que usa o SQL passa no gate de lint da skill `ci-gates`?
