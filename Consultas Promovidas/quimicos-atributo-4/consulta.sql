-- =============================================================================
-- OBJETIVO: Monitorar produtos quimicos com saldo positivo no atributo 4 (Deposito 20) e identificar a NF de entrada
-- DOMÍNIO: 01_beneficiamento_tingimento
-- ARQUIVO ORIGINAL: docs/oracle-schema/consultas/01_beneficiamento_tingimento/bnf_monitoramento_atributos_produtos_quimicos.sql
-- TIPO: SELECT (Auditoria/Sentinela Somente Leitura)
-- PARÂMETROS / BINDS: Nenhum (movimentos apos a data de fechamento do estoque no deposito 20, atributo 4)
-- TABELAS PRINCIPAIS: SGTPRD.GERAMOVIMENTOESTOQUE, SGTPRD.GERAPARAMSISTFILIAL, SGTPRD.ITENS_ESTOQUE,
--                     SGTPRD.LOTE_ITENS_NOTA_ENTR, SGTPRD.GERAMOVIESTOCOMP, SGTPRD.MOVTO_RECEITA,
--                     SGTPRD.UNIDADE_MEDIDA
-- CUIDADOS OPERACIONAIS: Passada unica em GERAMOVIMENTOESTOQUE via IDX_GME_01 (DTDOCUMENTO > DT_CORTE),
--                        capturando ID_ULTIMA_ENTRADA para lookup pontual de NF apenas nos itens com saldo > 0.
-- =============================================================================

WITH FECHAMENTO AS (
    SELECT /*+ MATERIALIZE */ MIN(DATA_FECHAMENTO_EST) AS DT_CORTE
    FROM SGTPRD.GERAPARAMSISTFILIAL
),
SALDO_ATRIBUTO AS (
    SELECT /*+ MATERIALIZE LEADING(F M) INDEX(M IDX_GME_01) */
           M.CDDEPOSITO                                                                          AS DEPOSITO,
           M.CDREDUZIDO                                                                          AS REDUZIDO,
           ROUND(SUM(CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END), 6)  AS QUANTIDADE,
           ROUND(SUM(CASE WHEN M.TIOPERACAO = 1 THEN M.QTMOVIMENTO ELSE 0 END), 6)               AS QT_ENTRADA_PERIODO,
           MAX(CASE WHEN M.TIOPERACAO = 1 THEN M.DTDOCUMENTO END)                                AS DT_ULTIMA_ENTRADA,
           MAX(M.DTDOCUMENTO)                                                                    AS DT_ULTIMO_MOVIMENTO,
           MAX(CASE WHEN M.TIOPERACAO = 1 THEN M.ID END) KEEP (
               DENSE_RANK LAST ORDER BY
                   CASE WHEN M.TIOPERACAO = 1 THEN M.DTDOCUMENTO END NULLS FIRST,
                   CASE WHEN M.TIOPERACAO = 1 THEN M.ID END NULLS FIRST
           )                                                                                     AS ID_ULTIMA_ENTRADA
      FROM FECHAMENTO F
      JOIN SGTPRD.GERAMOVIMENTOESTOQUE M
        ON M.DTDOCUMENTO > F.DT_CORTE
       AND M.CDDEPOSITO = 20
       AND M.IDGERAATRIESTO = 4
       AND M.STGERAESTOBLOQ = '0'
       AND M.STMOVIMENTO = 0
     GROUP BY M.CDDEPOSITO,
              M.CDREDUZIDO
    HAVING ROUND(SUM(CASE WHEN M.TIOPERACAO = 2 THEN -M.QTMOVIMENTO ELSE M.QTMOVIMENTO END), 6) > 0
),
RESERVA_RECEITAS AS (
    SELECT R.CODINSREDUZIDO AS REDUZIDO,
           ROUND(SUM(NVL(R.QUANTIDADE, 0)), 6) AS RESERVA_RECEITAS
      FROM SGTPRD.MOVTO_RECEITA R
     WHERE R.CODINSREDUZIDO IN (SELECT S.REDUZIDO FROM SALDO_ATRIBUTO S)
       AND R.DT_EMISSAO >= TRUNC(SYSDATE) - 30
       AND R.MOVCONFIRMADO = 0
       AND NVL(R.STATUSPESAGEMRECEITA, 0) <> 3
     GROUP BY R.CODINSREDUZIDO
)
SELECT NVL(
           TO_CHAR(
               COALESCE(
                   MAX(LINE.NUMERO_NOTA),
                   MAX(GMC.NRDOCUMENTO)
               )
           ),
           'SEM NF'
       )                            AS NF,
       S.DEPOSITO,
       S.REDUZIDO,
       TRIM(ITE.DESCRICAO)          AS DESCRICAO,
       S.QUANTIDADE,
       NVL(RR.RESERVA_RECEITAS, 0)  AS RESERVA_RECEITAS,
       TRIM(UM.DSSIGLA)             AS UM,
       S.QT_ENTRADA_PERIODO,
       S.DT_ULTIMA_ENTRADA,
       S.DT_ULTIMO_MOVIMENTO
  FROM SALDO_ATRIBUTO S
  JOIN SGTPRD.ITENS_ESTOQUE ITE
    ON ITE.CODIGO_REDUZIDO = S.REDUZIDO
  LEFT JOIN SGTPRD.UNIDADE_MEDIDA UM
    ON UM.IDUNIDADEMEDIDA = ITE.IDUNIDADEMEDIDA
  LEFT JOIN SGTPRD.LOTE_ITENS_NOTA_ENTR LINE
    ON LINE.NUMERO_MOVIMENTO = S.ID_ULTIMA_ENTRADA
  LEFT JOIN SGTPRD.GERAMOVIESTOCOMP GMC
    ON GMC.IDGERAMOVIESTO = S.ID_ULTIMA_ENTRADA
  LEFT JOIN RESERVA_RECEITAS RR
    ON RR.REDUZIDO = S.REDUZIDO
 GROUP BY S.DEPOSITO,
          S.REDUZIDO,
          TRIM(ITE.DESCRICAO),
          S.QUANTIDADE,
          NVL(RR.RESERVA_RECEITAS, 0),
          TRIM(UM.DSSIGLA),
          S.QT_ENTRADA_PERIODO,
          S.DT_ULTIMA_ENTRADA,
          S.DT_ULTIMO_MOVIMENTO
 ORDER BY S.QUANTIDADE DESC,
          S.REDUZIDO
