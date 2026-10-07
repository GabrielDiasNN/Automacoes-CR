/* =============================================================================
OBJETIVO: Formatar números no SQL
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: Comandos SQL - CR\Formatar números no SQL.sql
TIPO: Snippet / Utilitário SQL
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.NOTAFISCALITENS
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT TO_CHAR(NFI.VLTOTALBRUTO,'999G999G990D00') VL FROM SGTPRD.NOTAFISCALITENS NFI
