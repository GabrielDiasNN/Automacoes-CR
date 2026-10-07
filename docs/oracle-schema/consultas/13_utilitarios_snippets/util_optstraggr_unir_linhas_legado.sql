/* =============================================================================
OBJETIVO: Unir filiais distintas em uma única coluna com LISTAGG nativo
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: 13_utilitarios_snippets/util_funcao_unir_mais_de_um_resultado_na_mesma_linha.sql (Query #2)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.PESSOASFJ_FILIAIS
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT P.IDPESSOAFJ,
       LISTAGG(P.FILIAL, ',' ON OVERFLOW TRUNCATE)
           WITHIN GROUP (ORDER BY P.FILIAL) FILIAIS
FROM   (
    SELECT DISTINCT
           PF.IDPESSOAFJ,
           TRIM(LTRIM(PF.FILIAL, '0')) FILIAL
    FROM SGTPRD.PESSOASFJ_FILIAIS PF
    WHERE PF.IDPESSOAFJ = 1
) P
GROUP BY P.IDPESSOAFJ;
