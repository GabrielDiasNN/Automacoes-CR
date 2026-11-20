/* =============================================================================
OBJETIVO: Vínculo detalhado entre Unidade de Programação (UP) e Ordem de Movimento
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: 01_beneficiamento_tingimento/bnf_liga_numero_up_na_ob.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UNIDADE_PROGR_PROD, SGTPRD.UP_ORDEM_MVTO, SGTPRD.UP_PRODUTO
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT upr.NUMEROUP,
       upr.TIPO_MAQUINA,
       upr.CDFILIAL,
       upr.DATA_HORA_INICIO,
       upr.DATA_HORA_FINAL,
       upr.DATA_INI,
       upr.TURNO_INI,
       upr.DATA_FIM,
       upr.TURNO_FIM
  FROM sgtprd.up_ordem_mvto up
  JOIN sgtprd.up_produto upp ON upp.numeroup = up.numeroup
  JOIN sgtprd.unidade_progr_prod upr ON upr.numeroup = up.numeroup
  JOIN sgtprd.unidade_programacao udp ON udp.numeroup = up.numeroup
 WHERE up.numeroordemreal = 60477;
