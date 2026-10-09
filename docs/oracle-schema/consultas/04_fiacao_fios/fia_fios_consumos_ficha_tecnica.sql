/* =============================================================================
OBJETIVO: Fios consumos ficha técnica
DOMÍNIO: 04_fiacao_fios
ARQUIVO ORIGINAL: Comandos SQL - CR\Fios consumos ficha técnica.sql
TIPO: Fiação e Fios
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.FIOS_FICHA_MALHARIA_, SGTPRD.GRUPO_MAQUINAS, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
REVISÃO (08/10/2026): o join com GRUPO_MAQUINAS era só por GRUPO, mas a chave é (SETOR, GRUPO). Os grupos
  0G020 e 0G021 existem nos setores 4 e 7 e duplicavam cada fio (597 linhas contra 554 corretas; excesso de 43).
  Agora a subconsulta traz uma linha por GRUPO, com as descrições dos setores unidas por ' | ' (ordem de SETOR).
  A ficha de fio (FIOS_FICHA_MALHARIA_) não tem SETOR, então para 0G020 e 0G021 DESCRICAO_GRUPO traz as duas
  descrições. Decisão de negócio em aberto: qual setor vale para esses grupos.
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
    (
        SELECT GP.GRUPO,
               LISTAGG(GP.DESCRICAO, ' | ') WITHIN GROUP (ORDER BY GP.SETOR) AS DESCRICAO
          FROM SGTPRD.GRUPO_MAQUINAS GP
         GROUP BY GP.GRUPO
    ) g ON f.GRUPO_MAQUINA = g.GRUPO
LEFT JOIN
    SGTPRD.ITENS_ESTOQUE ite ON ite.CODIGO_REDUZIDO = f.CODIGO_FIO -- Junção para obter a descrição do fio
WHERE
    SUBSTR(i.CODIGO, 1, 3) IN ('MCP', 'MCR');