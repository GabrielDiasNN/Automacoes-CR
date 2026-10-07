/* =============================================================================
OBJETIVO: Consulta - Geração de Resíduo (Fiação)
DOMÍNIO: 11_views_referencia_sgt
ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta - Geração de Resíduo (Fiação).sql
TIPO: DDL / Definição de View
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: Não identificadas explicitamente
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

CREATE OR REPLACE VIEW VW_ESP_MEDDIA_PROD_RES AS
WITH BASE_PRODUCAO AS (
    -- Calcula a produção diária de fios por resíduo
    SELECT 
        RESF.COD_REDUZIDO_RESIDUO,
        GME2.CDREDUZIDO           AS CD_REDUZIDO_FIO,
        GME2.DTDOCUMENTO          AS DT_PRODUCAO,
        SUM(GME2.QTMOVIMENTO)     AS QT_PROD_FIO
    FROM RESIDUO_FIO RESF
    LEFT JOIN GERAMOVIMENTOESTOQUE GME2 
        ON GME2.CDREDUZIDO = RESF.CODIGO_REDUZIDO
    WHERE GME2.CDFILIAL IN (1, 2)
      AND GME2.NRTIPOMOVIMENTO = 32
      AND GME2.STMOVIMENTO = 0
      AND GME2.STMOVCONFIRMADO = '1'
      AND GME2.DTDOCUMENTO BETWEEN data_inicial AND data_anterior
      AND RESF.COD_REDUZIDO_RESIDUO IN (5937, 5946, 5948, 5953, 5933, 5936, 14574)
    GROUP BY RESF.COD_REDUZIDO_RESIDUO, GME2.CDREDUZIDO, GME2.DTDOCUMENTO
),
DIAS_PRODUCAO AS (
    -- Conta dias únicos de produção por resíduo
    SELECT 
        COD_REDUZIDO_RESIDUO,
        COUNT(DISTINCT DT_PRODUCAO) AS TOTAL_DIAS
    FROM BASE_PRODUCAO
    GROUP BY COD_REDUZIDO_RESIDUO
)
SELECT 
    PRE.FILIAL                        AS CD_FILIAL,
    PRE.REDUZ                         AS CD_REDUZIDO,
    TRIM(PRE.CODIGO_ALTERNATIVO)      AS CD_ALTERNATIVO,
    PRE.DESCR_ITEM                    AS DS_PRODUTO,
    SUM(PRE.QUANT)                    AS QT_PRODUZIDA,
    DP.TOTAL_DIAS                     AS DIAS,
    ROUND(SUM(PRE.QUANT) / NULLIF(DP.TOTAL_DIAS, 0), 2) AS MEDIA_PRODUZIDA_DIA
FROM VW_PI_CBASR01_PRD PRE
LEFT JOIN DIAS_PRODUCAO DP 
    ON DP.COD_REDUZIDO_RESIDUO = PRE.REDUZ
WHERE PRE.DATA_PRODUCAO BETWEEN data_inicial AND data_anterior
  AND PRE.REDUZ IN (5937, 5946, 5948, 5953, 5933, 5936, 14574)
GROUP BY 
    PRE.FILIAL,
    PRE.REDUZ,
    TRIM(PRE.CODIGO_ALTERNATIVO),
    PRE.DESCR_ITEM,
    DP.TOTAL_DIAS
ORDER BY CD_FILIAL, CD_REDUZIDO;
