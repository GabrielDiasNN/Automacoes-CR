/* =============================================================================
OBJETIVO: Vínculo detalhado entre Unidade de Programação (UP) e Ordem de Movimento
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: 01_beneficiamento_tingimento/bnf_liga_numero_up_na_ob.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UNIDADE_PROGR_PROD, SGTPRD.UP_ORDEM_MVTO, SGTPRD.UP_PRODUTO
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

select upr.*
  from sgtprd.up_ordem_mvto       up,
       sgtprd.up_produto          upp,
       sgtprd.unidade_progr_prod  upr,
       sgtprd.unidade_programacao udp
 where upp.numeroup = up.numeroup
   and upr.numeroup = up.numeroup
   and udp.numeroup = up.numeroup
   and up.numeroordemreal = 60477;
