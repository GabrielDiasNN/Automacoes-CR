/* =============================================================================
OBJETIVO: Vínculo de Romaneio com Nota Fiscal de Saída (NFC -> NFI -> GRI -> ROM)
DOMÍNIO: 07_expedicao_pedidos_comercial
ARQUIVO ORIGINAL: Comandos SQL - CR/Liga Romaneio na Nota Fiscal.sql
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum (filtros opcionais por NFC.NRNOTA ou ROM.NUMERO_ROMANEIO)
TABELAS PRINCIPAIS: SGTPRD.NOTAFISCALCAPA, SGTPRD.NOTAFISCALITENS, SGTPRD.GERAREQUESTOITEMNOTA, SGTPRD.PRODUTO_ROMANEIO
CUIDADOS OPERACIONAIS: Relacionamento das chaves fiscais e de expedição do SGT.
REVISÃO (20/09/2026 - Onda 1): ROWNUM <= 100 substituído por FETCH FIRST 100 ROWS ONLY.
  ROWNUM é avaliado antes do ORDER BY (retorna 100 linhas arbitrárias, depois ordena).
  FETCH FIRST é avaliado após o ORDER BY (retorna as 100 mais recentes corretamente).
  guard_sql.py: exit 0.
============================================================================= */

SELECT
    NFC.ID                     AS ID_NOTA_CAPA,
    NFC.NRNOTA                 AS NR_NOTA_FISCAL,
    NFC.IDSERIE                AS SERIE_NOTA,
    NFC.DTEMISSAO              AS DT_EMISSAO,
    NFI.ID                     AS ID_NOTA_ITEM,
    NFI.CDREDUZIDO             AS REDUZ_ITEM,
    ROM.NUMERO_ROMANEIO        AS NR_ROMANEIO,
    ROM.IDPRODUTO_ROMANEIO     AS ID_PROD_ROMANEIO,
    ROM.QUANTIDADE_KILOS       AS QT_KILOS,
    ROM.QUANTIDADE_METROS      AS QT_METROS
FROM SGTPRD.NOTAFISCALCAPA       NFC
JOIN SGTPRD.NOTAFISCALITENS      NFI ON NFI.IDNOTAFISCALCAPA = NFC.ID
JOIN SGTPRD.GERAREQUESTOITEMNOTA GRI ON NFI.ID = GRI.IDNOTAFISCALITENS
JOIN SGTPRD.PRODUTO_ROMANEIO     ROM ON GRI.IDPRODUTO_ROMANEIO = ROM.IDPRODUTO_ROMANEIO
ORDER BY NFC.DTEMISSAO DESC, NFC.NRNOTA DESC
FETCH FIRST 100 ROWS ONLY;
