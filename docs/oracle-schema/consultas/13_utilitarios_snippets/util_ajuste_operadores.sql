/* =============================================================================
OBJETIVO: Ajuste Operadores
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: Comandos SQL - CR\Ajuste Operadores.sql
TIPO: Segurança e Usuários
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.OPERADOR
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT O.CODIGO,
       O.NOME,
       O.TURNO,
       O.STATIVO,
       O.CODIGO_UNIDADE_FABRI,
       O.TISEPARADORROMANEIO,
       O.SETOR,
       O.GRUPO
  FROM SGTPRD.OPERADOR O
 WHERE O.SETOR = 5
      --AND O.CODIGO_UNIDADE_FABRI IN ('00010') 
      --AND O.TURNO = 4 
   AND O.STATIVO = 1
 ORDER BY O.NOME

