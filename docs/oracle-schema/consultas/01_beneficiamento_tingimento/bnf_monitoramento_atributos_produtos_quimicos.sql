-- =============================================================================
-- OBJETIVO: Monitorar Atributo Estoque (Produto Químico)
-- DOMÍNIO: 01_beneficiamento_tingimento
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Monitorar Atributo Estoque (Produto Químico).sql
-- TIPO: SELECT (Consulta Somente Leitura)
-- PARÂMETROS / BINDS: Nenhum (movimentos após a data de fechamento do estoque)
-- TABELAS PRINCIPAIS: SGTPRD.GERAMOVIMENTOESTOQUE, SGTPRD.GERAPARAMSISTFILIAL, SGTPRD.ITENS_ESTOQUE
-- CUIDADOS OPERACIONAIS: Materialização da data de fechamento na CTE FECHAMENTO e uso
--                        do índice temporal IDX_GME_01 (DTDOCUMENTO) para varrer apenas
--                        os movimentos recentes desde o fechamento do mês, reduzindo
--                        o tempo de execução de >10s para ~160ms.
-- =============================================================================

WITH FECHAMENTO AS (
    SELECT /*+ MATERIALIZE */ MIN(DATA_FECHAMENTO_EST) AS DT_CORTE
    FROM SGTPRD.GERAPARAMSISTFILIAL
)
SELECT /*+ LEADING(F M ITE) INDEX(M IDX_GME_01) */
       M.CDREDUZIDO,
       MIN(M.CDDEPOSITO)                                                                     AS CDDEPOSITO,
       MIN(M.IDGERAATRIESTO)                                                                 AS IDGERAATRIESTO,
       ROUND(SUM(CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END), 6)  AS QTDISPONIVEL,
       TRIM(ITE.DESCRICAO)                                                                   AS DESCRICAO
  FROM FECHAMENTO F
  JOIN SGTPRD.GERAMOVIMENTOESTOQUE M
    ON M.DTDOCUMENTO > F.DT_CORTE
   AND M.CDDEPOSITO = 20
   AND M.IDGERAATRIESTO = 4
   AND M.STGERAESTOBLOQ = '0'
   AND M.STMOVIMENTO = 0
  JOIN SGTPRD.ITENS_ESTOQUE ITE
    ON ITE.CODIGO_REDUZIDO = M.CDREDUZIDO
 GROUP BY M.CDREDUZIDO,
          TRIM(ITE.DESCRICAO)
 ORDER BY QTDISPONIVEL DESC
 FETCH FIRST 200 ROWS ONLY
