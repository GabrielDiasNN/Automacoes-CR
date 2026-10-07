/* =============================================================================
OBJETIVO: Ordens de Malharia em Aberto
DOMÍNIO: 03_malharia_teares
ARQUIVO ORIGINAL: Comandos SQL - CR\Ordens de Malharia em Aberto.sql
TIPO: Malharia e Teares
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ORDEM_PRODUCAO_MALHA, SGTPRD.XX2_ENUMERATES, SGTPRD.XX2_ENUMITEM
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

WITH STATUS_OPM AS (
    SELECT ENI.SEQUENCE AS STATUS,
           ENI.DESCRIPTION AS DESCRICAO
      FROM SGTPRD.XX2_ENUMERATES ENU
      JOIN SGTPRD.XX2_ENUMITEM ENI
        ON ENI.IDENUMERATE = ENU.ID
     WHERE ENU.NAME LIKE 'TESTATUSORDEMMALHA%'
)
SELECT O.CODIGO_REDUZIDO_PROD,
       O.STATUS,
       ST.DESCRICAO,
       TO_CHAR(O.NUMERO_ORDEM) NUMERO_ORDEM,
       O.NUMERO_MAQUINA,
       O.QUANTIDADE_PROGRAMAD,
       O.QUANTIDADE_CONFIRMAD,
       O.QTD_PECAS_BALANCA,
       O.NUMERO_ETIQUETAS_IMP,
       O.LOTE_PRODUTO_CRU,
       O.RPM,
       O.NUMERO_PEDIDO,
       O.VOLTAS_POR_PECA
  FROM SGTPRD.ORDEM_PRODUCAO_MALHA O
  JOIN STATUS_OPM ST
    ON ST.STATUS = O.STATUS
 WHERE O.STATUS <> 0
   --AND O.CODIGO_REDUZIDO_PROD = 133
   AND SUBSTR(O.NUMERO_MAQUINA, 6, 5) = 'TC044'
 ORDER BY 2
