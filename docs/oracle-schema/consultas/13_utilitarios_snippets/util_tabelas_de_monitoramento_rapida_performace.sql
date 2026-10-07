/* =============================================================================
OBJETIVO: Tabelas de monitoramento (rápida performace)
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: Comandos SQL - CR\Tabelas de monitoramento (rápida performace).sql
TIPO: Snippet / Utilitário SQL
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BD_PAR_ATUALIZACAO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT
    B.ID,
    B.TABELA,
    B.ATIVO,
    B.DIAS_ATUALIZAR,
    B.ATUALIZAR_AGORA,
    B.DESCRICAO
FROM SGTPRD.BD_PAR_ATUALIZACAO B
ORDER BY B.ID DESC
