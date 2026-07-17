-- =============================================================================
-- OFST-06 — Estoque de pecas cruas disponiveis no deposito 95
-- Parametrizada por CODIGO_REDUZIDO_PROD (= OB.CODIGO_REDUZIDO_CRU).
--
-- O marcador /*IN_BINDS*/ e substituido em tempo de execucao pela lista de bind
-- variables gerada em queries.build_estoque_sql (:C0, :C1, ...). Os NOMES dos
-- binds sao gerados pelo proprio codigo e os VALORES viajam como bind — nenhum
-- dado externo e interpolado nesta string.
--
-- Confiabilidade — por que duas contagens:
--   QTD_PECAS_DISPONIVEIS = COUNT(DISTINCT IDPECASPRODUTO) -> valor autoritativo.
--   QTD_LINHAS_BRUTAS     = COUNT(IDPECASPRODUTO)          -> linhas apos os joins.
-- ITENS_ESTOQUE e TIPO_FINALIDADE_FIO entram apenas como filtro (nenhuma coluna
-- delas e projetada). Confirmado via ALL_TAB_COLUMNS + EXPLAIN PLAN em 16/07/2026:
-- IDPECASPRODUTO (GERAPECACOMPLPECA/GERAPECACRU), NUMERO_FINALIDADE (TIPO_FINALIDADE_FIO)
-- e CODIGO_REDUZIDO (ITENS_ESTOQUE) sao todos PK das tabelas do lado direito do
-- join, entao a cardinalidade e 1:1 por construcao — o proprio otimizador
-- confirma isso eliminando fisicamente o acesso a ITENS_ESTOQUE do plano (join
-- elimination via FK+PK). QTD_PECAS_DISPONIVEIS == QTD_LINHAS_BRUTAS em todos os
-- casos testados. As duas contagens permanecem como blindagem barata contra uma
-- mudanca futura de modelagem que quebre essa garantia (ex.: PK composta virar
-- 1:N) — se isso acontecer, validators.validate_estoque_row detecta a divergencia.
--
-- Plano de execucao (EXPLAIN PLAN, 16/07/2026): NESTED LOOPS com
-- INDEX RANGE SCAN (GRPCPROD_INDPECASPRODUTOSIT) + INDEX UNIQUE SCAN nas demais
-- tabelas, custo total 6 para 2 codigos. Sem full table scan.
-- =============================================================================
SELECT GPP.CODIGO_REDUZIDO_PROD,
       COUNT(DISTINCT GPP.IDPECASPRODUTO) AS QTD_PECAS_DISPONIVEIS,
       COUNT(GPP.IDPECASPRODUTO)          AS QTD_LINHAS_BRUTAS
  FROM SGTPRD.GERAPECASPRODUTO GPP
 INNER JOIN SGTPRD.GERAPECACOMPLPECA GPC
    ON GPP.IDPECASPRODUTO = GPC.IDPECASPRODUTO
 INNER JOIN SGTPRD.GERAPECACRU GCR
    ON GPC.IDPECASPRODUTO = GCR.IDPECASPRODUTO
 INNER JOIN SGTPRD.TIPO_FINALIDADE_FIO TFF
    ON GPC.FINALIDADE = TFF.NUMERO_FINALIDADE
 INNER JOIN SGTPRD.ITENS_ESTOQUE ITE
    ON GPP.CODIGO_REDUZIDO_PROD = ITE.CODIGO_REDUZIDO
 WHERE GPP.CODIGO_REGISTRO = 1
   AND GPP.STPECAPRODUTO IN (0, 16, 18)
   AND GPP.IDPESSOAFJESTOQUE = 2
   AND GPP.PADRAO_QUALIDADE_SIN = 1
   AND GPP.CODIGO_DEPOSITO IN (95)
   AND GPC.FINALIDADE = 1
   AND GPP.CODIGO_REDUZIDO_PROD IN (/*IN_BINDS*/)
 GROUP BY GPP.CODIGO_REDUZIDO_PROD
