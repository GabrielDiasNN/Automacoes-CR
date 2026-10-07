/* =============================================================================
OBJETIVO: Padrão moderno com LISTAGG no Oracle
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: 13_utilitarios_snippets/util_funcao_unir_mais_de_um_resultado_na_mesma_linha.sql (Query #3)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.PESSOASFJ_FILIAIS
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT P.IDPESSOAFJ, LISTAGG(P.FILIAL, ',') WITHIN GROUP (ORDER BY P.FILIAL) FILIAIS
FROM   SGTPRD.PESSOASFJ_FILIAIS P
WHERE  P.IDPESSOAFJ=1
GROUP BY P.IDPESSOAFJ;
