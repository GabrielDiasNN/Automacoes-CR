/* =============================================================================
OBJETIVO: Estoque total de malha crua
DOMÍNIO: 05_estoque_armazenagem
ARQUIVO ORIGINAL: Comandos SQL - CR\Estoque total de malha crua.sql
TIPO: Estoque e Depósitos
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ENGEITEMESTONIVELGE, SGTPRD.ENGEITEMESTONIVELGE9, SGTPRD.FASES_FLUXO, SGTPRD.GERAPECASPRODUTO, SGTPRD.GRUPO_FASES, SGTPRD.ITENS_ESTOQUE, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

WITH FASE_ATUAL AS (
                  SELECT NUMERO_OB, SETOR_SEQUENCIA, CODIGO_GRUPO AS GRUPO_FASE, STATUS
                    FROM (
                      SELECT OBF.NUMERO_OB,
                             NVL(GF.SETOR_SEQUENCIA, 0) SETOR_SEQUENCIA,
                             FF.CODIGO_GRUPO,
                             OBF.STATUS,
                             ROW_NUMBER() OVER (
                               PARTITION BY OBF.NUMERO_OB
                               ORDER BY CASE WHEN OBF.STATUS IN (1,2,3) THEN 1 WHEN OBF.STATUS = 0 THEN 2 ELSE 3 END,
                                        OBF.SEQUENCIA DESC
                             ) RN
                        FROM SGTPRD.OB O
                        JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = O.NUMERO_OB
                        JOIN SGTPRD.FASES_FLUXO FF ON FF.CODIGO_FASE = OBF.CODIGO_FASE
                        LEFT JOIN SGTPRD.GRUPO_FASES GF ON GF.CODIGO = FF.CODIGO_GRUPO
                       WHERE O.TIPO_ORDEM IN (0, 6)
                    )
                   WHERE RN = 1
), ESTOQUE AS (
                  SELECT
                      CASE WHEN TRIM(MAS.CDNIVELGENERICO) = 'T' THEN 'TUBULAR' ELSE 'RAMADO' END AS FLUXO,
                      SUM(E.QTLIQUIDA) AS QT
                  FROM
                      SGTPRD.GERAPECASPRODUTO E
                      INNER JOIN SGTPRD.ENGEITEMESTONIVELGE MAS ON E.CODIGO_REDUZIDO_PROD = MAS.CDREDUZIDO
                  WHERE
                      E.PADRAO_QUALIDADE_SIN = 1
                      AND E.TISITUACAOESTOQUE IN (0, 1)
                      AND E.STPECAPRODUTO IN (0, 16, 18)
                      AND E.CODIGO_DEPOSITO <> 30
                      AND TRIM(MAS.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR', 'MCT')
                  GROUP BY
                      CASE WHEN TRIM(MAS.CDNIVELGENERICO) = 'T' THEN 'TUBULAR' ELSE 'RAMADO' END
                 ), 
     MONTADO_REVISADO AS (
                  SELECT
                      CASE WHEN TRIM(EG.CDNIVELGENERICO) = 'T' THEN 'TUBULAR' ELSE 'RAMADO' END AS FLUXO,
                      SUM(CASE WHEN OBF.GRUPO_FASE = 1 THEN OBP.KILOS ELSE 0 END) AS MONTADO_QT,
                      SUM(CASE WHEN OBF.GRUPO_FASE = 2 AND OBF.STATUS <> 3
                               THEN OBP.KILOS ELSE 0 END) AS REVISADO_QT
                  FROM
                      FASE_ATUAL OBF
                      INNER JOIN SGTPRD.OB_PRODUTO OBP ON OBF.NUMERO_OB = OBP.NUMERO_OB
                      INNER JOIN SGTPRD.ITENS_ESTOQUE ITE ON OBP.CODPRO_REDUZIDO = ITE.CODIGO_REDUZIDO
                      INNER JOIN SGTPRD.ENGEITEMESTONIVELGE9 EG ON OBP.CODPRO_REDUZIDO = EG.CDREDUZIDO
                  WHERE
                      OBF.SETOR_SEQUENCIA IN (10, 20)
                      AND (OBF.GRUPO_FASE = 1
                           OR (OBF.GRUPO_FASE = 2 AND OBF.STATUS <> 3))
                  GROUP BY
                      CASE WHEN TRIM(EG.CDNIVELGENERICO) = 'T' THEN 'TUBULAR' ELSE 'RAMADO' END
                  )
SELECT
    ESTOQUE.FLUXO,
    ROUND(SUM(NVL(ESTOQUE.QT, 0) + NVL(MR.MONTADO_QT, 0) + NVL(MR.REVISADO_QT, 0)), 2) AS QUANTIDADE_KG,
    ROUND(SUM(NVL(ESTOQUE.QT, 0) + NVL(MR.MONTADO_QT, 0) + NVL(MR.REVISADO_QT, 0)) / (SUM(SUM(NVL(ESTOQUE.QT, 0) + NVL(MR.MONTADO_QT, 0) + NVL(MR.REVISADO_QT, 0))) OVER()) * 100, 2) || '%' AS PERC
FROM
    ESTOQUE
    LEFT JOIN MONTADO_REVISADO MR ON MR.FLUXO = ESTOQUE.FLUXO
GROUP BY
    ESTOQUE.FLUXO;

