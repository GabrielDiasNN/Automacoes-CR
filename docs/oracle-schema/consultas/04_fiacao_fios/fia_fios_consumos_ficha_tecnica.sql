/* =============================================================================
OBJETIVO: Fios consumos ficha técnica
DOMÍNIO: 04_fiacao_fios
ARQUIVO ORIGINAL: Comandos SQL - CR\Fios consumos ficha técnica.sql
TIPO: Fiação e Fios
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.FIOS_FICHA_MALHARIA_, SGTPRD.GRUPO_MAQUINAS, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT
    f.CODIGO_FIO,
    ite.DESCRICAO AS DESCR_FIO,
    f.CODIGO_PRODUTO,
    i.CODIGO_ALTERNATIVO AS ARTIGO,
    i.CODIGO,
    i.DESCRICAO,
    f.PERCENTUAL_PERDA,
    f.GRUPO_MAQUINA,
    g.DESCRICAO AS DESCRICAO_GRUPO,
    f.PERCPARTICIPACAO,
    f.INDIESTITITULO
FROM
    SGTPRD.FIOS_FICHA_MALHARIA_ f
INNER JOIN
    SGTPRD.ITENS_ESTOQUE i ON f.CODIGO_PRODUTO = i.CODIGO_REDUZIDO
INNER JOIN
    SGTPRD.GRUPO_MAQUINAS g ON f.GRUPO_MAQUINA = g.GRUPO
LEFT JOIN
    SGTPRD.ITENS_ESTOQUE ite ON ite.CODIGO_REDUZIDO = f.CODIGO_FIO -- Junção para obter a descrição do fio
WHERE
    SUBSTR(i.CODIGO, 1, 3) IN ('MCP', 'MCR');