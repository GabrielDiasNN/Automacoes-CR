/* =============================================================================
OBJETIVO: RELAÇÃO DE BANHO
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\RELAÇÃO DE BANHO.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ESPECIFICACAO_PRODUT, SGTPRD.RELACAO_BANHO_EP
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT R.NUMERO_MAQUINA,
       R.RELACAO_BANHO,
       R.ESPECIFICACAO_PRODUT,
       EP.DESCRICAO
  FROM SGTPRD.RELACAO_BANHO_EP R, SGTPRD.ESPECIFICACAO_PRODUT EP
 WHERE R.PROCESSO_INDUSTRIAL = 401
   AND TRIM(R.NUMERO_MAQUINA) NOT IN
       ('000000KM01', '000000MQ99', '000000MQ00')
   AND EP.ESPECIFICACAOPRODUTO = R.ESPECIFICACAO_PRODUT
   AND R.ESPECIFICACAO_PRODUT = 54
 GROUP BY R.NUMERO_MAQUINA,
          R.RELACAO_BANHO,
          R.ESPECIFICACAO_PRODUT,
          EP.DESCRICAO
 ORDER BY 1, 2;
