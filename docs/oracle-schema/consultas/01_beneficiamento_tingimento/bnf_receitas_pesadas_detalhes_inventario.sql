/* =============================================================================
OBJETIVO: OB_s com receitas pesadas (com detalhes produtos Júlio inventário)
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s com receitas pesadas (com detalhes produtos Júlio inventário).sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.FASES_FLUXO, SGTPRD.ITENS_ESTOQUE, SGTPRD.MOVTO_RECEITA, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.OPERADOR, SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. 100% nativa sem views. Execução somente leitura salvo se DML restrito.
============================================================================= */

WITH FASE_ATUAL AS (
    SELECT /*+ MATERIALIZE */
           OBF.NUMERO_OB,
           MIN(FFL.DESCRICAO_FASE) KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS DESCR_FASE,
           MIN(OBF.STATUS)         KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS STATUS_FASE
      FROM SGTPRD.OB_FASES OBF
      JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
     WHERE OBF.STATUS <> 4
     GROUP BY OBF.NUMERO_OB
),
MAQ_TING AS (
    SELECT /*+ MATERIALIZE */
           OBZ.NUMERO_OB,
           SUBSTR(MAX(OBZ.NUMERO_MAQUINA), 7, 4) AS MQ_TING
      FROM SGTPRD.OB_FASES OBZ
     WHERE OBZ.CODIGO_FASE = 40
     GROUP BY OBZ.NUMERO_OB
),
UP_TINGIMENTO AS (
    SELECT /*+ MATERIALIZE */
           UPO.NUMEROORDEMREAL     AS NUMERO_OB,
           MAX(UNP.DTTEMPOINICIAL) AS INICIO_TING,
           MAX(UNP.DTTEMPOFINAL)   AS FINAL_TING
      FROM SGTPRD.UP_ORDEM_MVTO UPO
      JOIN SGTPRD.UNIDADE_PROGRAMACAO UNP ON UNP.NUMEROUP = UPO.NUMEROUP
     WHERE UNP.TIPO_MAQUINA = 19
       AND UNP.EXCLUIDA = 0
       AND UNP.TIPOUP = 0
     GROUP BY UPO.NUMEROORDEMREAL
)
SELECT OBF.CODIGO_GRUPO                                              GRUPO,
       OBF.NUMERO_OB                                                 NUMERO_OB,
       M.TIPO_PESAGEM                                                TP_PESAGEM,
       DECODE(M.TIPO_PESAGEM,0,'MANUAL',1,'AUTOMATICA')              DESC_TP_PESAGEM,
       CASE WHEN NVL(SUM(M.QUANTIDADEPESADA), 0) = 0 THEN 'NAO' ELSE 'SIM' END PESADA,
       M.QUANTIDADE                                                  QUANTIDADE,
       M.SEQUENCIA                                                   SEQUENCIA,
       M.CODINSREDUZIDO                                              REDUZIDO_INSUMO,
       MAX(TRIM(ITE_INS.DESCRICAO))                                  DESCRICAO_INSUMO,
       MAX(MTG.MQ_TING)                                              MQ_TING,
       MAX(UPT.INICIO_TING)                                          INICIO_TING,
       MAX(UPT.FINAL_TING)                                           FINAL_TING,
       OBP.CODPRO_REDUZIDO                                           REDUZIDO_PRODUTO,
       MAX(TRIM(ITE_PRD.DESCRICAO))                                  DESCRICAO_PRODUTO,
       FAS.DESCR_FASE                                                FASE_ATUAL,
       CASE FAS.STATUS_FASE
            WHEN 0 THEN 'PROGRAMADA'
            WHEN 1 THEN 'EMITIDA'
            WHEN 2 THEN 'PESADA'
            WHEN 3 THEN 'EM EXECUCAO'
            ELSE TO_CHAR(FAS.STATUS_FASE)
       END                                                           STATUS_FASE,
       MAX(TRIM(OPE.NOME))                                           USUARIO_QUE_PESOU
  FROM SGTPRD.OB_FASES           OBF
  JOIN FASE_ATUAL                FAS     ON FAS.NUMERO_OB = OBF.NUMERO_OB
  JOIN SGTPRD.OB_PRODUTO         OBP     ON OBP.NUMERO_OB = OBF.NUMERO_OB
  JOIN SGTPRD.MOVTO_RECEITA      M       ON M.NUMEROORDEM = DECODE(OBF.CODIGO_GRUPO, 0, OBF.NUMERO_OB, OBF.CODIGO_GRUPO)
                                        AND M.SEQUENCIAFASEOB = DECODE(OBF.CODIGO_GRUPO, 0, OBF.SEQUENCIA, 0)
  LEFT JOIN SGTPRD.OPERADOR      OPE     ON OPE.IDOPERADOR = M.IDOPE_PESAGEM
  LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE_INS ON ITE_INS.CODIGO_REDUZIDO = M.CODINSREDUZIDO
  LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE_PRD ON ITE_PRD.CODIGO_REDUZIDO = OBP.CODPRO_REDUZIDO
  LEFT JOIN MAQ_TING             MTG     ON MTG.NUMERO_OB = OBF.NUMERO_OB
  LEFT JOIN UP_TINGIMENTO        UPT     ON UPT.NUMERO_OB = OBF.NUMERO_OB
 WHERE OBF.CODIGO_FASE = 40
   AND OBF.STATUS IN (1, 2)
 GROUP BY OBF.NUMERO_OB,
          M.TIPO_PESAGEM,
          OBF.CODIGO_GRUPO,
          OBP.CODPRO_REDUZIDO,
          M.QUANTIDADE,
          M.CODINSREDUZIDO,
          M.SEQUENCIA,
          FAS.DESCR_FASE,
          FAS.STATUS_FASE
 ORDER BY INICIO_TING, M.SEQUENCIA;
