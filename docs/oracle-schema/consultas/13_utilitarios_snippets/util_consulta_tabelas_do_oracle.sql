/* =============================================================================
OBJETIVO: Consulta Tabelas do Oracle
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta Tabelas do Oracle.sql
TIPO: Snippet / Utilitário SQL
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.XX2_TABLES
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT
    T.ID,
    T.GUID,
    T.NAME,
    T.NICKNAME,
    T.FILENAME,
    T.IDMODULE,
    T.DOSFILE,
    T.DOSREG,
    T.INMEMORY,
    T.SYSTEMMODULE,
    T.DESCRIPTION,
    T.ISCLIENT,
    T.DOSNUMBER,
    T.ISVIRTUAL,
    T.ISSYSTEM,
    T.ISTEMPORARY,
    T.FORMATMASK,
    T.IDMODULEWEB,
    T.GUIDDESCRIPTION
FROM sgtprd.xx2_tables T
ORDER BY T.DESCRIPTION
