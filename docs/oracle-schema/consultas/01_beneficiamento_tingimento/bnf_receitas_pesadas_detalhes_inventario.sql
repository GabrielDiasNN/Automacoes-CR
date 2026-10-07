/* =============================================================================
OBJETIVO: OB_s com receitas pesadas (com detalhes produtos Júlio inventário)
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s com receitas pesadas (com detalhes produtos Júlio inventário).sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.FASES_FLUXO, SGTPRD.ITENS_ESTOQUE, SGTPRD.MOVTO_RECEITA, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO
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
)
SELECT OBF.CODIGO_GRUPO                                              GRUPO,
       OBF.NUMERO_OB                                                 NUMERO_OB,
       M.TIPO_PESAGEM                                                TP_PESAGEM,
       DECODE(M.TIPO_PESAGEM,0,'MANUAL',1,'AUTOMATICA')              DESC_TP_PESAGEM,
       CASE WHEN NVL(SUM(M.QUANTIDADEPESADA), 0) = 0 THEN 'NAO' ELSE 'SIM' END PESADA,
       M.QUANTIDADE                                                  QUANTIDADE,
       M.SEQUENCIA                                                   SEQUENCIA,
       M.CODINSREDUZIDO                                              REDUZIDO_INSUMO,
       (SELECT TRIM(ITE.DESCRICAO)
          FROM SGTPRD.ITENS_ESTOQUE ITE 
         WHERE ITE.CODIGO_REDUZIDO = M.CODINSREDUZIDO)               DESCRICAO_INSUMO,
           
       (SELECT SUBSTR(MAX(OBZ.NUMERO_MAQUINA),7,4) MQ 
          FROM SGTPRD.OB_FASES OBZ 
         WHERE OBZ.NUMERO_OB = OBF.NUMERO_OB 
           AND OBZ.CODIGO_FASE = 40 
         GROUP BY OBZ.NUMERO_OB)                                     MQ_TING,
       (SELECT MAX(UNP.DTTEMPOINICIAL)
          FROM SGTPRD.UP_ORDEM_MVTO UPO, 
               SGTPRD.UNIDADE_PROGRAMACAO UNP
         WHERE UPO.NUMEROUP = UNP.NUMEROUP
           AND UPO.NUMEROORDEMREAL = OBF.NUMERO_OB
           AND UNP.TIPO_MAQUINA = 19
           AND UNP.EXCLUIDA = 0
           AND UNP.TIPOUP = 0)                                       INICIO_TING,
           
       (SELECT MAX(UNP.DTTEMPOFINAL)
          FROM SGTPRD.UP_ORDEM_MVTO UPO, 
               SGTPRD.UNIDADE_PROGRAMACAO UNP
         WHERE UPO.NUMEROUP = UNP.NUMEROUP
           AND UPO.NUMEROORDEMREAL = OBF.NUMERO_OB
           AND UNP.TIPO_MAQUINA = 19
           AND UNP.EXCLUIDA = 0
           AND UNP.TIPOUP = 0)                                       FINAL_TING,
           
       OBP.CODPRO_REDUZIDO                                           REDUZIDO_PRODUTO,
       (SELECT TRIM(ITE.DESCRICAO) 
          FROM SGTPRD.ITENS_ESTOQUE ITE 
         WHERE ITE.CODIGO_REDUZIDO = OBP.CODPRO_REDUZIDO)            DESCRICAO_PRODUTO,
         
       FAS.DESCR_FASE                                                FASE_ATUAL,
         
       CASE FAS.STATUS_FASE
            WHEN 0 THEN 'PROGRAMADA'
            WHEN 1 THEN 'EMITIDA'
            WHEN 2 THEN 'PESADA'
            WHEN 3 THEN 'EM EXECUCAO'
            ELSE TO_CHAR(FAS.STATUS_FASE)
       END                                                           STATUS_FASE,
       MAX(M.USUARIO_PESO_RECEITA)                                   USUARIO_QUE_PESOU
  FROM SGTPRD.OB_FASES           OBF
  JOIN FASE_ATUAL                FAS ON FAS.NUMERO_OB = OBF.NUMERO_OB
  JOIN SGTPRD.OB_PRODUTO         OBP ON OBP.NUMERO_OB = OBF.NUMERO_OB
  JOIN SGTPRD.MOVTO_RECEITA      M   ON M.NUMEROORDEM = DECODE(OBF.CODIGO_GRUPO, 0, OBF.NUMERO_OB, OBF.CODIGO_GRUPO)
                                    AND M.SEQUENCIAFASEOB = DECODE(OBF.CODIGO_GRUPO, 0, OBF.SEQUENCIA, 0)
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
