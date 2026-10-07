/* =============================================================================
OBJETIVO: Meta Malharia
DOMÍNIO: 03_malharia_teares
ARQUIVO ORIGINAL: Comandos SQL - CR\Meta Malharia.sql
TIPO: Malharia e Teares
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.TB_ESP_PROD_TEOR_MAL
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
REVISÃO (21/09/2026): predicado de data convertido para faixa sargável,
  preservando exatamente o intervalo do dia anterior e evitando TRUNC na coluna.
EQUIVALÊNCIA ORACLE (21/09/2026): controle legado e candidata retornaram 89
  linhas e 12 colunas; comparar_equivalencia.py exit 0 com todas as colunas
  como chave. Evidência sanitizada em equivalencia-mal-meta-final.json.
============================================================================= */

SELECT
    T.DT_META,
    T.ST_OPM,
    T.DS_ST_OPM,
    T.NR_OPM,
    T.CD_REDUZIDO,
    T.NR_MAQUINA,
    T.GRUPO,
    T.KG_DIA_100,
    T.KG_DIA_EFIC,
    T.VL_INT,
    T.VL_EXT,
    T.CD_CELULA
  FROM sgtprd.tb_esp_prod_teor_mal T
 WHERE T.DT_META >= TRUNC(SYSDATE) - 1
   AND T.DT_META < TRUNC(SYSDATE)
