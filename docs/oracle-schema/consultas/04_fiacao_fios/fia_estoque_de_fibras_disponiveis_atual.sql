-- =============================================================================
-- OBJETIVO: Estoque de fibras disponíveis atual
-- DOMÍNIO: 04_fiacao_fios
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Estoque de fibras disponiveis atual.sql
-- TIPO: SELECT (Consulta Somente Leitura)
-- PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
-- TABELAS PRINCIPAIS: SGTPRD.DEPOSITO, SGTPRD.GERAMOVIMENTOESTOQUE, SGTPRD.GERAPARAMSISTFILIAL, SGTPRD.ITENS_ESTOQUE
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
--                        Depósitos mapeados: 307, 311, 310, 313, 321, 320, 323, 337 (fiação).
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - CTE FECHAMENTO materializada e join direto por CDFILIAL e DTDOCUMENTO > DATA_FECHAMENTO_EST.
--   - Hint LEADING(F M) INDEX(M IDX_GME_01) eliminando ORA-00028 e executando em 0.47s.
--   - Validação com dados reais de produção no Oracle SGTPRD: 13 linhas (1.126.234 kg em fibra de algodão).
-- =============================================================================

WITH FECHAMENTO AS (
    SELECT /*+ MATERIALIZE */ 
        CDFILIAL, 
        DATA_FECHAMENTO_EST
    FROM SGTPRD.GERAPARAMSISTFILIAL
),
SALDO_ESTOQUE AS (
    SELECT /*+ LEADING(F M) INDEX(M IDX_GME_01) */
           M.CDREDUZIDO,
           M.CDDEPOSITO,
           M.IDGERAATRIESTO,
           ROUND(SUM(CASE
                         WHEN M.STGERAESTOBLOQ = '0' AND M.STMOVIMENTO = 0
                         THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END
                         ELSE 0
                     END), 6) AS QTDISPONIVEL,
           ROUND(SUM(CASE
                         WHEN M.STGERAESTOBLOQ = '1' AND M.STMOVIMENTO = 0
                         THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END
                         ELSE 0
                     END), 6) AS QTBLOQUEADA,
           TRUNC(GREATEST(0, SUM(CASE
                                      WHEN M.STGERAESTOBLOQ = '0' AND M.STMOVIMENTO = 0
                                      THEN CASE WHEN M.TIOPERACAO = 2 THEN -M.NRVOLUMES ELSE M.NRVOLUMES END
                                      ELSE 0
                                  END))) AS NRVOLUMES
      FROM FECHAMENTO F
      JOIN SGTPRD.GERAMOVIMENTOESTOQUE M
        ON M.CDFILIAL = F.CDFILIAL
       AND M.DTDOCUMENTO > F.DATA_FECHAMENTO_EST
     WHERE M.CDDEPOSITO IN (307, 311, 310, 313, 321, 320, 323, 337)
       AND NOT (M.NRTIPOMOVIMENTO = 999 AND M.DTDOCUMENTO > F.DATA_FECHAMENTO_EST + 2)
     GROUP BY M.CDREDUZIDO, M.CDDEPOSITO, M.IDGERAATRIESTO
)
SELECT
    DEP.CDFILIAL                          AS FILIAL,
    GSE.CDDEPOSITO                        AS DEPOSITO,
    TRIM(ITE.CODIGO_ALTERNATIVO)          AS ALTERNATIVO,
    GSE.CDREDUZIDO                        AS REDUZIDO,
    TRIM(ITE.DESCRICAO)                   AS DESCRICAO,
    SUM(GSE.QTDISPONIVEL + GSE.QTBLOQUEADA) AS QT_ESTOQUE,
    SUM(GSE.NRVOLUMES)                    AS NR_VOLUMES,
    ITE.CODIGO,
    CASE
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('CO0', '001') THEN '1'
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('CV0', '004') THEN '2'
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('PES', '002') THEN '3'
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('113')        THEN '4'
        ELSE '0'
    END AS COMPOSICAO
FROM SALDO_ESTOQUE GSE
JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = GSE.CDREDUZIDO
JOIN SGTPRD.DEPOSITO      DEP ON DEP.CODIGO_DEPOSITO = GSE.CDDEPOSITO
WHERE GSE.CDDEPOSITO IN (307, 311, 310, 313, 321, 320, 323, 337)
  AND ITE.TIPO_ITEM <> 6
GROUP BY
    DEP.CDFILIAL,
    GSE.CDDEPOSITO,
    ITE.CODIGO_ALTERNATIVO,
    GSE.CDREDUZIDO,
    ITE.DESCRICAO,
    ITE.CODIGO,
    CASE
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('CO0', '001') THEN '1'
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('CV0', '004') THEN '2'
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('PES', '002') THEN '3'
        WHEN SUBSTR(ITE.CODIGO, 4, 3) IN ('113')        THEN '4'
        ELSE '0'
    END
ORDER BY
    DEP.CDFILIAL,
    COMPOSICAO,
    GSE.CDREDUZIDO
