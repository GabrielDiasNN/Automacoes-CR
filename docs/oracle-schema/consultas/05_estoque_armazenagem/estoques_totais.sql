/* =============================================================================
OBJETIVO: Estoques Totais
DOMÍNIO: 05_estoque_armazenagem
ARQUIVO ORIGINAL: Comandos SQL - CR\Estoques Totais.sql
TIPO: Estoque e Depósitos
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.GERAPECACOMPLPECA, SGTPRD.GERAPECACRU, SGTPRD.GERAPECASPRODUTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.TIPO_FINALIDADE_FIO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
REVISÃO (20/09/2026 - Onda 4): projeção da subconsulta BASE explicitada nas
  nove colunas consumidas; joins e agregações preservados.
============================================================================= */

 SELECT BASE.CODIGO_DEPOSITO DEP,
        CASE
           WHEN BASE.CODIGO_DEPOSITO = 90  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO IN (0,18)  THEN                                                                                           '1 - MALHARIA'
           WHEN BASE.CODIGO_DEPOSITO = 95  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO IN (0,18) AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') AND BASE.TIDOCUMENTOENTRADA <> 8 THEN      '2 - TINTURARIA (PRPRIO)'
           WHEN BASE.CODIGO_DEPOSITO = 95  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 0 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') AND BASE.TIDOCUMENTOENTRADA = 8 THEN             '2 - TINTURARIA (FACO)'
           WHEN BASE.CODIGO_DEPOSITO = 95  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 0 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCT') THEN                                                    '2 - TINTURARIA (TERCEIROS)'
           WHEN BASE.CODIGO_DEPOSITO = 100 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 9 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') THEN                                             '3 - EM PROCESSO (PRPRIO)'
           WHEN BASE.CODIGO_DEPOSITO = 100 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 9 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') AND BASE.TIDOCUMENTOENTRADA = 8 THEN             '2 - EM PROCESSO (FACO)'
           WHEN BASE.CODIGO_DEPOSITO = 100 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 9 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCT') THEN                                                    '3 - EM PROCESSO (TERCEIROS)'
           WHEN BASE.CODIGO_DEPOSITO = 110 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNF','BNR')  AND BASE.STPECAPRODUTO = 14 AND SUBSTR(BASE.CODIGO, 18, 6) <> '999999' THEN '4 - ACABADO (RESERVA PEDIDO VENDA)'
           WHEN BASE.CODIGO_DEPOSITO = 110 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNF','BNR')  AND BASE.STPECAPRODUTO = 13 AND SUBSTR(BASE.CODIGO, 18, 6) <> '999999' THEN '4 - ACABADO (RESERVA ROMANEIO SADA)'
           WHEN BASE.CODIGO_DEPOSITO = 110 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNF','BNR')  AND BASE.STPECAPRODUTO <> 0 AND SUBSTR(BASE.CODIGO, 18, 6) = '999999' THEN  '4 - ESTAMPADO'
           WHEN BASE.CODIGO_DEPOSITO = 111 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNT')  THEN                                                                              '4 - ACABADO TERCEIROS'
           WHEN BASE.PADRAO_QUALIDADE_SIN IN (2, 3) AND BASE.TIDOCUMENTOENTRADA <> 8 THEN                                                                                                                         '5 - SEGUNDA QUALIDADE (PRPRIO)'
           WHEN BASE.PADRAO_QUALIDADE_SIN IN (2, 3) AND BASE.TIDOCUMENTOENTRADA = 8  THEN                                                                                                                         '5 - SEGUNDA QUALIDADE (FACO)'
           WHEN BASE.CODIGO_DEPOSITO = 30 THEN                                                                                                                                                                    '6 - REPROCESSO'
           WHEN BASE.STPECAPRODUTO = 0 THEN                                                                                                                                                                       '7 - STATUS NORMAL'
           WHEN BASE.STPECAPRODUTO = 16 THEN                                                                                                                                                                      '8 - ALOCADA INVENTRIO'
           ELSE ''
        END AS ANALISE,
        COUNT(BASE.STPECAPRODUTO) PEAS,
        RTRIM(TO_CHAR(SUM(BASE.QTLIQUIDA), '999G999G990D00')) PESO_LIQ
  FROM (
        SELECT
               GPP.CODIGO_DEPOSITO,
               GPP.PADRAO_QUALIDADE_SIN,
               GPP.STPECAPRODUTO,
               GPP.TIDOCUMENTOENTRADA,
               GPP.QTLIQUIDA,
               GPP.TISITUACAOESTOQUE,
               ITE.CODIGO,
               ITE.IDMASCARATIPOINSUMO,
               ITE.TIPO_ITEM
          FROM SGTPRD.GERAPECASPRODUTO GPP
         LEFT JOIN SGTPRD.GERAPECACOMPLPECA GPC
            ON GPP.IDPECASPRODUTO = GPC.IDPECASPRODUTO
         LEFT JOIN SGTPRD.GERAPECACRU GCR
            ON GPC.IDPECASPRODUTO = GCR.IDPECASPRODUTO
         LEFT JOIN SGTPRD.TIPO_FINALIDADE_FIO TFF
            ON GPC.FINALIDADE = TFF.NUMERO_FINALIDADE
         LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE
            ON GPP.CODIGO_REDUZIDO_PROD = ITE.CODIGO_REDUZIDO
        ) BASE
 WHERE BASE.TISITUACAOESTOQUE IN (0, 1)
   AND BASE.TIPO_ITEM IN (9,10)
 GROUP BY BASE.CODIGO_DEPOSITO,
          CASE
           WHEN BASE.CODIGO_DEPOSITO = 90  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO IN (0,18)  THEN                                                                                           '1 - MALHARIA'
           WHEN BASE.CODIGO_DEPOSITO = 95  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO IN (0,18) AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') AND BASE.TIDOCUMENTOENTRADA <> 8 THEN      '2 - TINTURARIA (PRPRIO)'
           WHEN BASE.CODIGO_DEPOSITO = 95  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 0 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') AND BASE.TIDOCUMENTOENTRADA = 8 THEN             '2 - TINTURARIA (FACO)'
           WHEN BASE.CODIGO_DEPOSITO = 95  AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 0 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCT') THEN                                                    '2 - TINTURARIA (TERCEIROS)'
           WHEN BASE.CODIGO_DEPOSITO = 100 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 9 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') THEN                                             '3 - EM PROCESSO (PRPRIO)'
           WHEN BASE.CODIGO_DEPOSITO = 100 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 9 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') AND BASE.TIDOCUMENTOENTRADA = 8 THEN             '2 - EM PROCESSO (FACO)'
           WHEN BASE.CODIGO_DEPOSITO = 100 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  BASE.STPECAPRODUTO = 9 AND TRIM(BASE.IDMASCARATIPOINSUMO) IN ('MCT') THEN                                                    '3 - EM PROCESSO (TERCEIROS)'
           WHEN BASE.CODIGO_DEPOSITO = 110 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNF','BNR')  AND BASE.STPECAPRODUTO = 14 AND SUBSTR(BASE.CODIGO, 18, 6) <> '999999' THEN '4 - ACABADO (RESERVA PEDIDO VENDA)'
           WHEN BASE.CODIGO_DEPOSITO = 110 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNF','BNR')  AND BASE.STPECAPRODUTO = 13 AND SUBSTR(BASE.CODIGO, 18, 6) <> '999999' THEN '4 - ACABADO (RESERVA ROMANEIO SADA)'
           WHEN BASE.CODIGO_DEPOSITO = 110 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNF','BNR')  AND BASE.STPECAPRODUTO <> 0 AND SUBSTR(BASE.CODIGO, 18, 6) = '999999' THEN  '4 - ESTAMPADO'
           WHEN BASE.CODIGO_DEPOSITO = 111 AND BASE.PADRAO_QUALIDADE_SIN IN (1) AND  TRIM(BASE.IDMASCARATIPOINSUMO) IN ('BNT')  THEN                                                                              '4 - ACABADO TERCEIROS'
           WHEN BASE.PADRAO_QUALIDADE_SIN IN (2, 3) AND BASE.TIDOCUMENTOENTRADA <> 8 THEN                                                                                                                         '5 - SEGUNDA QUALIDADE (PRPRIO)'
           WHEN BASE.PADRAO_QUALIDADE_SIN IN (2, 3) AND BASE.TIDOCUMENTOENTRADA = 8  THEN                                                                                                                         '5 - SEGUNDA QUALIDADE (FACO)'
           WHEN BASE.CODIGO_DEPOSITO = 30 THEN                                                                                                                                                                    '6 - REPROCESSO'
           WHEN BASE.STPECAPRODUTO = 0 THEN                                                                                                                                                                       '7 - STATUS NORMAL'
           WHEN BASE.STPECAPRODUTO = 16 THEN                                                                                                                                                                      '8 - ALOCADA INVENTRIO'
           ELSE ''
        END
 ORDER BY ANALISE, BASE.CODIGO_DEPOSITO
