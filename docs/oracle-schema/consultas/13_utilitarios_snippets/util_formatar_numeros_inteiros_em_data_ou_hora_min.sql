/* =============================================================================
OBJETIVO: Formatar números inteiros em data ou hora-min
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: Comandos SQL - CR\Formatar números inteiros em data ou hora-min.sql
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.GERAPECACOMPLPECA, SGTPRD.GERAPECASPRODUTO
CUIDADOS OPERACIONAIS: Snippet didático — demonstra conversão de inteiros SGT para data/hora.
                       Para usar com outra função auxiliar: SELECT PKGUTIL0001.FNC_CNVDATA(campo_data_num, NULL) FROM DUAL.
============================================================================= */

SELECT
    GPP.IDPECASPRODUTO,
    TO_DATE(GPP.DATA_DA_ENTRADA_PECA, 'YYYYMMDD')                            AS DT_ENTRADA,
    TO_CHAR(
        TO_DATE(DECODE(GPP.DATA_DA_ENTRADA_PECA, 0, 18991231, GPP.DATA_DA_ENTRADA_PECA), 'YYYYMMDD')
        + (GPP.HORA_DA_ENTRADA_PECA / 1440),
        'hh24:mi'
    )                                                                         AS HORA_ENTRADA
FROM SGTPRD.GERAPECASPRODUTO GPP
JOIN SGTPRD.GERAPECACOMPLPECA GPC ON GPC.IDPECASPRODUTO = GPP.IDPECASPRODUTO
FETCH FIRST 100 ROWS ONLY
