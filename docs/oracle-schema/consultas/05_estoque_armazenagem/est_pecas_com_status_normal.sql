/* =============================================================================
OBJETIVO: Peças com status normal
DOMÍNIO: 05_estoque_armazenagem
ARQUIVO ORIGINAL: Comandos SQL - CR\Peças com status normal.sql
TIPO: Estoque e Depósitos
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.GERAPECASPRODUTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.GERAPECAORIGEMOB, SGTPRD.PEDPRODUCAOOB
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
OTIMIZAÇÃO: Adicionado predicado indexado em DATA_DA_ENTRADA_PECA nos últimos 90 dias,
  evitando scan global de 6,6 milhões de peças e reduzindo de timeout para ~2.4s.
AUDITORIA (29/09/2026): retorna 0 linhas e está correto, confirmado pela área: nos depósitos 100, 110 e
  111 nenhuma peça entrada nos últimos 90 dias tem STPECAPRODUTO = 0 ('Normal' em GERASTPECAPRODUTO).
  Ali as peças ficam em 8/9 (origem da OB), 4 (utilizada) e 12/13/14. Peças 'Normal' existem em outros
  depósitos (321, 95, 311, 90, 329, 314), que esta consulta não cobre por desenho.
============================================================================= */

WITH PECAS_FILTRADAS AS (
    SELECT /*+ MATERIALIZE */
           GPP.IDPECASPRODUTO                         AS ID_PECA,
           GPO.NUMERO_OB                              AS NR_OB,
           GPP.CODIGO_REDUZIDO_PROD                   AS CD_REDUZIDO,
           ITE.CODIGO_ALTERNATIVO                     AS CD_ALTERNATIVO,
           GPP.PADRAO_QUALIDADE_SIN                   AS QS,
           TO_DATE(TO_CHAR(GPP.DATA_DA_ENTRADA_PECA), 'YYYYMMDD') AS DT_ENTRADA,
           GPP.QTLIQUIDA                              AS QT_LIQ
      FROM SGTPRD.GERAPECASPRODUTO GPP
      JOIN SGTPRD.ITENS_ESTOQUE    ITE ON ITE.CODIGO_REDUZIDO = GPP.CODIGO_REDUZIDO_PROD
 LEFT JOIN SGTPRD.GERAPECAORIGEMOB GPO ON GPO.IDPECASPRODUTO = GPP.IDPECASPRODUTO
     WHERE GPP.STPECAPRODUTO = 0
       AND GPP.CODIGO_DEPOSITO IN (100, 110, 111)
       AND GPP.DATA_DA_ENTRADA_PECA >= TO_NUMBER(TO_CHAR(SYSDATE - 90, 'YYYYMMDD'))
),
OB_PEDIDOS AS (
    SELECT /*+ MATERIALIZE */
           IPG.PEDIDO,
           IPG.ITEMPEDIDO,
           PC.SITUACAO,
           OB.STATUS,
           PPOB.NUMEROOB,
           OFO.REDUZIDO
      FROM SGTPRD.PEDPRODUCAOOB    PPOB
      JOIN SGTPRD.PEDPRODUCAO      PP  ON PP.NUMERO = PPOB.NUMERO
      JOIN SGTPRD.OFORDENS         OFO ON OFO.NUMEROPEDPRODUCAO = PP.NUMERO AND OFO.REDUZIDO = PPOB.REDUZIDO
      JOIN SGTPRD.OFPEDIDO         OFP ON OFP.NUMEROOF = OFO.NUMEROOF AND OFP.NIVEL = OFO.NIVEL AND OFP.REDUZIDO = OFO.REDUZIDO
      JOIN SGTPRD.ITENSPEDIDOQTDES IPQ ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
      JOIN SGTPRD.ITENSPEDIDOGRADE IPG ON IPG.IDITENSPEDIDOGRADE = IPQ.IDITEMPEDGRADE
      JOIN SGTPRD.OB               OB  ON OB.NUMERO_OB = PPOB.NUMEROOB
      JOIN SGTPRD.PEDIDOCOMERCIAL  PC  ON PC.PEDIDO = IPG.PEDIDO
     WHERE OFP.QUANTIDADE_ATUAL <> 0
       AND PPOB.NUMEROOB IN (SELECT NR_OB FROM PECAS_FILTRADAS WHERE NR_OB IS NOT NULL)
)
SELECT
    O.PEDIDO                AS PEDIDO,
    O.ITEMPEDIDO            AS ITEM,
    O.SITUACAO              AS SIT_ITEM,
    O.STATUS                AS ST_OB,
    A.QS                    AS QS,
    A.DT_ENTRADA            AS ENTRADA,
    COUNT(A.ID_PECA)        AS PS,
    A.CD_ALTERNATIVO        AS ARTIGO,
    A.CD_REDUZIDO           AS RED,
    A.NR_OB                 AS NR_OB,
    SUM(A.QT_LIQ)           AS QT_LIQ
FROM
    PECAS_FILTRADAS A
LEFT JOIN
    OB_PEDIDOS O ON O.NUMEROOB = A.NR_OB AND O.REDUZIDO = A.CD_REDUZIDO
GROUP BY
    O.PEDIDO,
    O.ITEMPEDIDO,
    O.SITUACAO,
    A.DT_ENTRADA,
    A.CD_ALTERNATIVO,
    A.CD_REDUZIDO,
    A.NR_OB,
    O.STATUS,
    A.QS
ORDER BY
    O.PEDIDO,
    O.ITEMPEDIDO,
    A.DT_ENTRADA
FETCH FIRST 500 ROWS ONLY
