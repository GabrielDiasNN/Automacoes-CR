/* =============================================================================
OBJETIVO: Conferência de SKU TOTVS por reduzido agrupador
DOMÍNIO: 06_qualidade_auditoria_obs
ARQUIVO ORIGINAL: 06_qualidade_auditoria_obs/qld_conferencia_sku_totvs.sql (Query #2)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.ENGEITEMESTONIVELGE9, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT ITE.CODIGO_REDUZIDO                                              COD_REDUZIDO,
       TRIM(ITE.CODIGO_ALTERNATIVO)                                     COD_ALTERNATIVO,
       TRIM(ITE.DESCRICAO)                                              DESCRICAO,
       DECODE(TRIM(ENG.CDNIVELGENERICO), 'T', 'TUBULAR', 'R', 'RAMADO') TIPO_PRODUTO,
       ITE.CODCLASFISCAL                                                NCM
  FROM SGTPRD.ITENS_ESTOQUE ITE, SGTPRD.ENGEITEMESTONIVELGE9 ENG
 WHERE ENG.CDREDUZIDO = ITE.CODIGO_REDUZIDO
   AND ITE.CODIGO_REDUZIDO IN (17157);
