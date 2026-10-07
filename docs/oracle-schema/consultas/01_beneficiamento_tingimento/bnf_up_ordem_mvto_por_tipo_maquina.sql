/* =============================================================================
OBJETIVO: Unidades de Programação (UP) e movimentações por tipo de máquina
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: 01_beneficiamento_tingimento/bnf_liga_numero_up_na_ob.sql (Query #5b)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.TIPOSMAQUINAS, SGTPRD.UNIDADE_PROGR_PROD, SGTPRD.UP_ORDEM_MVTO
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual. 100% nativa sem views.
============================================================================= */

SELECT UP.NUMEROUP,
       UP.NUMEROORDEMREAL,
       UP.SEQUENCIAORDEMREAL,
       UND.TIPO_MAQUINA,
       TP.DESCRICAO AS DESCR_TIPO_MAQUINA,
       UND.DATA_HORA_INICIO,
       UND.DATA_HORA_FINAL
  FROM SGTPRD.UP_ORDEM_MVTO UP
  JOIN SGTPRD.UNIDADE_PROGR_PROD UND 
    ON UND.NUMEROUP = UP.NUMEROUP
  LEFT JOIN SGTPRD.TIPOSMAQUINAS TP 
    ON TP.IDTIPOSMAQUINA = UND.TIPO_MAQUINA
 ORDER BY UND.DATA_FIM DESC
 FETCH FIRST 100 ROWS ONLY;
