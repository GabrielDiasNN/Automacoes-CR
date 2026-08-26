-- =============================================================================
-- ORB-07 — OBs emitidas, não montadas, destinadas a tingimento branco
--
-- A classificação da cor é autoritativa. O código de cor da fase é projetado
-- somente para auditoria: no Oracle, 00001 também aparece associado a classes
-- que não são BRANCO. Classes aceitas: 6 (BRANCO) e 9 (BRANCO 2 FIBRAS).
--
-- OB sem classificação resolvida permanece no retorno com código nulo para que
-- a camada de validação registre WARN e a descarte de forma observável.
-- =============================================================================
WITH
CLASSIFICACAO_OB AS (
    SELECT V.NR_OB,
           MAX(V.CD_CLASSIFICACAO_COR)
               KEEP (DENSE_RANK LAST ORDER BY V.CD_CLASSIFICACAO_COR)
               AS CD_CLASSIFICACAO_COR,
           MAX(TRIM(V.DS_CLASSIFICACAO_COR))
               KEEP (DENSE_RANK LAST ORDER BY V.CD_CLASSIFICACAO_COR)
               AS DS_CLASSIFICACAO_COR,
           COUNT(DISTINCT V.CD_CLASSIFICACAO_COR) AS QTD_CLASSIFICACOES_COR
      FROM SGTPRD.VW_EXC_OB_PROD_CLASS_COR V
     GROUP BY V.NR_OB
),
COR_TINGIMENTO AS (
    SELECT OBF.NUMERO_OB,
           MAX(TRIM(OBF.CODIGO_COR_DESENHO))
               KEEP (DENSE_RANK LAST ORDER BY OBF.SEQUENCIA)
               AS CODIGO_COR_TINGIMENTO
      FROM SGTPRD.OB_FASES OBF
     WHERE OBF.CODIGO_FASE = 40
     GROUP BY OBF.NUMERO_OB
)
SELECT OB.NUMERO_OB,
       OB.CODIGO_FLUXO,
       OB.CODIGO_REDUZIDO_CRU,
       OB.STATUS,
       OBP.TOTAL_PECAS,
       OBP.KILOS_PROGRAMADOS,
       PPOB.OBMONTADA,
       ART.CDARTIGOCRU AS CODIGO_ARTIGO_CRU,
       COR.CODIGO_COR_TINGIMENTO,
       CLS.CD_CLASSIFICACAO_COR,
       CLS.DS_CLASSIFICACAO_COR,
       NVL(CLS.QTD_CLASSIFICACOES_COR, 0) AS QTD_CLASSIFICACOES_COR,
       -- EXPEDIREM e' texto livre no Oracle: uma unica linha com valor vazio, com
       -- espacos ou fora de YYYYMMDD derrubaria o lote inteiro (ORA-01861/ORA-01847,
       -- exit 1 -> Exit-WithCode 3) por um campo que e' apenas informativo na mensagem
       -- e desempate de prioridade. DEFAULT NULL ON CONVERSION ERROR degrada a linha
       -- ruim para NULL, caminho ja suportado por coerce_ob_row e priorizar_obs.
       -- Disponivel desde Oracle 12.2; o servidor de producao e 12.2.0.1.0
       -- (ver docs/ai-native-context-monitor.md).
       TO_DATE(IPC.EXPEDIREM DEFAULT NULL ON CONVERSION ERROR, 'YYYYMMDD') AS DT_ENTREGA,
       PED.IDFILIALRESPONSAVEL AS ID_CLIENTE,
       TRIM(PES.NOMEFANTASIA) AS NOME_CLIENTE
  FROM SGTPRD.OB OB
 INNER JOIN SGTPRD.OB_PRODUTO OBP
    ON OBP.NUMERO_OB = OB.NUMERO_OB
 INNER JOIN SGTPRD.PEDPRODUCAOOB PPOB
    ON PPOB.NUMEROOB = OB.NUMERO_OB
  LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ART
    ON ART.CDREDUZIDO = OB.CODIGO_REDUZIDO_CRU
  LEFT JOIN CLASSIFICACAO_OB CLS
    ON CLS.NR_OB = OB.NUMERO_OB
  LEFT JOIN COR_TINGIMENTO COR
    ON COR.NUMERO_OB = OB.NUMERO_OB
  LEFT JOIN SGTPRD.OFORDENS OFO
    ON OFO.NUMEROPEDPRODUCAO = PPOB.NUMERO
   AND OFO.REDUZIDO = PPOB.REDUZIDO
  LEFT JOIN SGTPRD.OFPEDIDO OFP
    ON OFP.NUMEROOF = OFO.NUMEROOF
   AND OFP.NIVEL = OFO.NIVEL
   AND OFP.REDUZIDO = OFO.REDUZIDO
   AND OFP.QUANTIDADE_ATUAL <> 0
  LEFT JOIN SGTPRD.ITENSPEDIDOQTDES IPQ
    ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
  LEFT JOIN SGTPRD.ITENSPEDIDOGRADE IPG
    ON IPG.IDITENSPEDIDOGRADE = IPQ.IDITEMPEDGRADE
  LEFT JOIN SGTPRD.ITENSPEDIDOCOMERCIAL IPC
    ON IPC.PEDIDO = IPG.PEDIDO
   AND IPC.ITEMPEDIDO = IPG.ITEMPEDIDO
  LEFT JOIN SGTPRD.PEDIDOCOMERCIAL PED
    ON PED.PEDIDO = IPC.PEDIDO
  LEFT JOIN SGTPRD.PESSOASFJ PES
    ON PES.IDPESSOAFJ = PED.IDFILIALRESPONSAVEL
 WHERE OB.STATUS = 1
   AND PPOB.OBMONTADA = '0'
   AND (CLS.CD_CLASSIFICACAO_COR IN (6, 9) OR CLS.CD_CLASSIFICACAO_COR IS NULL)
   -- Exclusao R/S e por LINHA (pedido comercial), nao por OB: intencional. Uma OB
   -- ligada a mais de um pedido comercial permanece elegivel se ao menos um deles
   -- nao terminar em R/S, mesmo que outro pedido ligado a mesma OB termine.
   AND (
        PED.PEDIDOCLIENTE IS NULL
     OR (PED.PEDIDOCLIENTE NOT LIKE '%R' AND PED.PEDIDOCLIENTE NOT LIKE '%S')
   )
