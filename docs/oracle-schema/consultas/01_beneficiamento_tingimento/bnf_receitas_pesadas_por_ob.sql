/* =============================================================================
OBJETIVO: OB_s com receitas pesadas
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s com receitas pesadas.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: :MI, :SS
TABELAS PRINCIPAIS: SGTPRD.ENGEITEMESTOARTCRU, SGTPRD.FASES_FLUXO, SGTPRD.ITENS_ESTOQUE, SGTPRD.MOVTO_RECEITA, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.OPERADOR, SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO
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
           MAX(LTRIM(OBZ.NUMERO_MAQUINA, 0)) AS MQ_TING
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
SELECT OBF.CODIGO_GRUPO                                                           GRUPO,
       OBF.NUMERO_OB                                                              NUMERO_OB,
       CASE WHEN NVL(SUM(M.QUANTIDADEPESADA), 0) = 0 THEN 'NO' ELSE 'SIM' END    PESADA,
       MAX(MTG.MQ_TING)                                                           MQ_TING,
       MAX(UPT.INICIO_TING)                                                       INICIO_TING,
       MAX(UPT.FINAL_TING)                                                        FINAL_TING,
       MAX(ART.CDARTIGOCRU)                                                       ARTIGO,
       OBP.CODPRO_REDUZIDO                                                        REDUZIDO,
       MAX(TRIM(ITE.DESCRICAO))                                                   DESCRICAO,
       FAS.DESCR_FASE                                                             FASE_ATUAL,
       CASE FAS.STATUS_FASE
            WHEN 0 THEN 'PROGRAMADA'
            WHEN 1 THEN 'EMITIDA'
            WHEN 2 THEN 'PESADA'
            WHEN 3 THEN 'EM EXECUCAO'
            ELSE TO_CHAR(FAS.STATUS_FASE)
       END                                                                        STATUS_FASE,
       MAX(TRIM(OPE.NOME))                                                        USUARIO,       
       MAX(M.DT_PESAGEM)                                                          HORARIO_PESADO,
       ROUND((SYSDATE)-MAX(M.DT_PESAGEM),2)                                       DIAS_PESADO,
       SUM(M.QUANTIDADEPESADA)                                                    QUANT_PESADA
   FROM SGTPRD.OB_FASES           OBF
   JOIN FASE_ATUAL                FAS ON FAS.NUMERO_OB = OBF.NUMERO_OB
   JOIN SGTPRD.OB_PRODUTO         OBP ON OBP.NUMERO_OB = OBF.NUMERO_OB
   JOIN SGTPRD.MOVTO_RECEITA      M   ON M.NUMEROORDEM = OBF.NUMEROORDEMMOVIMENTO
                                     AND M.SEQUENCIAFASEOB = OBF.SEQUENCIAORDEMMOVIME
   LEFT JOIN SGTPRD.OPERADOR      OPE ON OPE.IDOPERADOR = M.IDOPE_PESAGEM
   LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ART ON ART.CDREDUZIDO = OBP.CODPRO_REDUZIDO
   LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = OBP.CODPRO_REDUZIDO
   LEFT JOIN MAQ_TING             MTG ON MTG.NUMERO_OB = OBF.NUMERO_OB
   LEFT JOIN UP_TINGIMENTO        UPT ON UPT.NUMERO_OB = OBF.NUMERO_OB
  WHERE OBF.CODIGO_FASE   = 40
    AND OBF.STATUS        IN (1, 2)
  GROUP BY OBF.NUMERO_OB,
           M.NUMEROORDEM,
           OBF.CODIGO_GRUPO,
           OBP.CODPRO_REDUZIDO,
           FAS.DESCR_FASE,
           FAS.STATUS_FASE
  ORDER BY INICIO_TING;
