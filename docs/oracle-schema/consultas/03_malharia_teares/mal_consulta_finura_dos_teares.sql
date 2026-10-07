/* =============================================================================
OBJETIVO: Consulta Finura dos Teares
DOMÍNIO: 03_malharia_teares
ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta Finura dos Teares.sql
TIPO: Malharia e Teares
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.MALHATIVAFINURAMAQ
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

--APENAS ALTERAR A FINURA DESEJADA

SELECT
    M.IDMALHATIVAFINURAMAQ,
    M.NUMERO_MAQUINA,
    M.CDFINURA
  FROM SGTPRD.MALHATIVAFINURAMAQ M
 WHERE M.CDFINURA = 24
 AND SUBSTR (M.NUMERO_MAQUINA, 6,3) = 'TC0'
 ORDER BY M.NUMERO_MAQUINA
