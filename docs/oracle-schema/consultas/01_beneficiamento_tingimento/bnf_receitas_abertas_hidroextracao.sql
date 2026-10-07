/* =============================================================================
OBJETIVO: Consulta Receitas em Aberto no Hidro
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta Receitas em Aberto no Hidro.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BD_BAS_MASCPRODACAB, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO
CUIDADOS OPERACIONAIS: Consulta 100% nativa sem views, filtrada por hidroextração (fase 50).
============================================================================= */

SELECT OFP.NUMERO_OB,
       O.CODPRO_REDUZIDO,
       OFP.CODIGO_COR_DESENHO
  FROM SGTPRD.OB_PRODUTO              O
  JOIN SGTPRD.OB                      OB  ON OB.NUMERO_OB = O.NUMERO_OB
  JOIN SGTPRD.OB_FASES                OFP ON OFP.NUMERO_OB = O.NUMERO_OB
  JOIN SGTPRD.BD_BAS_MASCPRODACAB     V   ON V.CODIGO_REDUZIDO = O.CODPRO_REDUZIDO
 WHERE OB.STATUS <> 0
   AND O.IDPESSOAFJ = 3111
   AND OFP.CODIGO_FASE = 50
   AND TRIM(V.COR) = '10325'
   AND TRIM(OFP.CODIGO_COR_DESENHO) <> 'HID16'
 ORDER BY OFP.NUMERO_OB;