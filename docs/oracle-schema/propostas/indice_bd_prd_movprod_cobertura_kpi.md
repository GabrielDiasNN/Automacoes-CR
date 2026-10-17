# Proposta de índice em SGTPRD.BD_PRD_MOVPROD para os KPIs de produção

**Status:** proposta. Nada foi criado no Oracle. O DDL está em [`indice_bd_prd_movprod_cobertura_kpi.sql`](indice_bd_prd_movprod_cobertura_kpi.sql) e exige aprovação do DBA.
**Data dos fatos:** 16/10/2026. Todas as medições são de leitura.

## 1. Pedido

Criar um índice de cobertura em `SGTPRD.BD_PRD_MOVPROD` para acelerar duas consultas de KPI de produção que hoje passam de 3 segundos sob medição de mediana:

- `pcp_producao_12m_matriz_pivotada`: mediana de 3.007 ms, depois da reescrita. A linha de base era 3.964 ms.
- `pcp_producao_12m_fato_serie_temporal`: mediana entre 2.821 e 3.112 ms, conforme a execução.

O limite de 3 s foi aceito pelo usuário como referência de desempenho. Duas consultas estão na margem dessa referência, com oscilação de cerca de ±0,3 s entre medições.

## 2. Fatos verificados no Oracle

| Fato | Valor | Como foi medido |
|:---|:---|:---|
| Linhas da tabela | 60.228.251 (estatística de 14/10/2026) | `ALL_INDEXES.NUM_ROWS` |
| Linhas com `PRODUCAO_DATA` nos últimos 12 meses | 9.618.359 | `COUNT(*)` com a faixa de data |
| Linhas com `CODIGO IN (1,8)` e `NUM_TIPO_MOVIMENTO = 37` na janela | 818.540 (8,5% da janela) | `COUNT(*)` |
| Linhas com `CODIGO IN (1,8)` na janela, sem o filtro de tipo | 818.540 | `COUNT(*)` |
| Colunas usadas pela consulta | `CODIGO`, `NUM_TIPO_MOVIMENTO`, `PRODUCAO_DATA`, `PRODUCAO_TURNO`, `REDUZIDO_ITEM`, `ESTAMPADO`, `QUANTIDADE_REAL`, `IDPECASPRODUTO` | `ALL_TAB_COLUMNS`: as 8 existem |
| Índices atuais | 6 índices, todos `VALID`, todos no tablespace `COSTARICADT`, todos `LOGGING = YES` | `ALL_INDEXES` |
| Índice mais usado pela consulta | `BDMOVPR_IND_MOVPRD_DATA (CODIGO, PRODUCAO_DATA, TIPO_ITEM, TPUNIDADEMEDIDA)` | `EXPLAIN PLAN` do `medir_sql_oracle.py --explain` |
| Plano atual (fato) | Faixa de 703 mil entradas do índice, depois acesso à tabela por ROWID em lote (110 mil linhas) | mesmo plano |

Observação sobre a seletividade: o filtro `NUM_TIPO_MOVIMENTO = 37` não reduz nada dentro da janela, porque todas as linhas com `CODIGO IN (1,8)` já são do tipo 37. O filtro continua na consulta por segurança semântica, mas o índice não depende dele para a seletividade.

## 3. Hipótese técnica

O plano atual usa o índice `DATA`, que tem `PRODUCAO_DATA` como segunda coluna e `TIPO_ITEM`/`TPUNIDADEMEDIDA` no meio. Esse índice não contém `NUM_TIPO_MOVIMENTO`, `PRODUCAO_TURNO`, `REDUZIDO_ITEM`, `ESTAMPADO` nem `QUANTIDADE_REAL`. Por isso, para cada linha filtrada, o banco vai à tabela de 60 milhões de linhas buscar essas colunas.

O índice proposto `(CODIGO, NUM_TIPO_MOVIMENTO, PRODUCAO_DATA, PRODUCAO_TURNO, REDUZIDO_ITEM, ESTAMPADO, QUANTIDADE_REAL, IDPECASPRODUTO)` deve permitir **leitura só pelo índice** (index-only scan) para o trecho que a consulta usa. A ordem das colunas segue a regra usual: igualdades primeiro (`CODIGO`, `NUM_TIPO_MOVIMENTO`), faixa depois (`PRODUCAO_DATA`), colunas de cobertura por último.

**Isto é hipótese, não medição.** O ganho só vale se o plano realmente usar o índice sem voltar à tabela. A validação da seção 5 é o critério de aceite.

## 4. Riscos e custos

- **Escrita:** a tabela recebe inserções de produção contínuas. Cada índice novo aumenta o custo de INSERT/UPDATE. A tabela já tem 6 índices, então o acréscimo é de mais um. O DBA deve avaliar o impacto na carga de escrita.
- **Espaço:** o tamanho do índice não foi medido. Os índices atuais também não têm tamanho verificado nesta sessão, porque a consulta de `USER_SEGMENTS` não retornou dados para a tabela. A pré-checagem 1b do DDL mede o espaço livre antes da criação.
- **Construção:** `ONLINE` evita bloqueio de DML, mas a construção sobre 60 milhões de linhas consome I/O e CPU. Recomenda-se janela de baixa carga.
- **Semântica:** o índice não altera resultado. É uma estrutura de acesso. A equivalência deve ser conferida mesmo assim (seção 5c).
- **Permissão:** a criação exige privilégio que o usuário de leitura não tem. A execução é do DBA.
- **Impacto em outras consultas:** o índice pode ser escolhido pelo otimizador em consultas que filtram `CODIGO` e `PRODUCAO_DATA` de outra forma. Revisar o plano das consultas que usam `BD_PRD_MOVPROD` depois da criação. Antes da criação, levantar no acervo a lista de consultas que leem `BD_PRD_MOVPROD` (busca por nome da tabela nos `.sql`) e medir as principais antes e depois.

## 5. Critério de aceite

1. **Plano:** `medir_sql_oracle.py --explain` das duas consultas mostra `BDMOVPR_IND_KPI_COBERTURA` no trecho do filtro, sem `TABLE ACCESS BY INDEX ROWID` em `BD_PRD_MOVPROD` para esse trecho.
2. **Desempenho:** mediana de 3 execuções, com a linha de base de hoje como controle. Ganho acima do ruído medido (cerca de 300 ms) para considerar a proposta efetiva. Se a mediana não cair de forma clara, o índice não compensa seu custo de escrita, e o rollback é aplicado.
3. **Resultado:** `comparar_equivalencia.py` com as chaves do grão de cada consulta, sem diferença, no mesmo instante da medição original (os dados do mês corrente mudam ao longo do dia).
4. **Regressão:** medir as consultas de KPI que usam `BD_PRD_MOVPROD` (lista no catálogo) e confirmar que nenhuma piorou.

## 6. Alternativas consideradas

- **Não criar o índice e aceitar 3 s como ruído.** Opção que o usuário escolheu para o encerramento do loop. Continua válida; o custo é deixar as duas consultas na margem.
- **Reescrita adicional das consultas.** Já foram feitas a consolidação da janela (`FASES_RAW`) e a retirada de leituras repetidas. O experimento sem `MATERIALIZE` piorou o tempo. Não há outra reescrita read-only com ganho demonstrado.
- **Índice só em `(CODIGO, PRODUCAO_DATA, PRODUCAO_TURNO, REDUZIDO_ITEM, QUANTIDADE_REAL)`.** Menor, mas sem `NUM_TIPO_MOVIMENTO` e `ESTAMPADO`. A consulta precisaria do acesso à tabela para `ESTAMPADO`, o que anula parte do ganho. Não foi escolhida pela mesma razão.

## 7. Sequência sugerida

1. DBA confere a proposta e roda a pré-checagem do DDL (seção 1 do `.sql`).
2. Criação em janela de baixa carga, com `ONLINE`.
3. Coleta de estatísticas do índice (seção 2b do `.sql`).
4. Validação pelo critério da seção 5, usando o acervo de KPI e as ferramentas de medição do repositório.
5. Se aprovado, registrar a mudança em `REGRAS_NEGOCIO.md` e no `KPI_CATALOGO.md`. Se reprovado, executar o rollback do `.sql`.
