/* =============================================================================
OBJETIVO: Fechamento da 1a quinzena (dias 01 a 15, inclusive) do mes de referencia: producao, produtos quimicos por categoria e cavaco (quantidades e valores).
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Painel/KPI
GRÃO: uma linha por categoria do relatório (CORANTE, AUXILIARES, ACABAMENTO, ETA/ETE, COMMODITIES, TOTAL QUIMICOS, CAVACO); contexto de produção repetido em todas as linhas
PARÂMETROS / BINDS: :MES_REF = 'YYYY-MM' (ex.: '2026-10'). Período calculado: dia 1 até dia 15.
TABELAS PRINCIPAIS: SGTPRD.FECHAMENTO_ESTOQUE_A, SGTPRD.FECHAMENTO_VALOR (abertura = fechamento do mês anterior),
          SGTPRD.GERAMOVIMENTOESTOQUE, SGTPRD.MOVIMENTACAO_VALOR (movimentos do período),
          SGTPRD.ITENS_ESTOQUE, SGTPRD.ENGEITEMESTOCLASSE (classificação),
          SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.MOVIMENTO_MAQUINA (produção e dias)
REGRAS CONFIRMADAS (validadas contra fechamentos de ago e set/2026):
  - Abertura = (SALDO_ATUAL - QUANTIDADE_BLOQUEADA) e VLFINAL (valor UNITARIO, por item) do fechamento do mes anterior.
    O saldo bloqueado do fechamento nao entra no estoque livre: ele some no fechamento seguinte sem movimento.
  - Movimento valido: STMOVIMENTO = 0, STGERAESTOBLOQ = 0, NRTIPOMOVIMENTO <> 999.
    STMOVIMENTO 1/2 sao pares de estorno que se anulam; 999 e o saldo de abertura ja fechado.
  - TIOPERACAO 1 = entrada (valor = QTMOVIMENTO x VLMOVIMENTO unitario de MOVIMENTACAO_VALOR);
    TIOPERACAO 2 = saida (nao tem valor gravado: e valorizada pelo custo medio do periodo).
  - Custo medio do periodo por item = (valor inicial + valor das entradas) / (qtd inicial + qtd entradas).
  - Estoque final = inicial + entradas - saidas (quantidade e valor a custo medio).
  - Consumo (R$) = saidas x custo medio. Consumo por kg = consumo (R$) / KG_RAMADO.
  - Producao: KG_RAMADO = KILOS da fase 150 (embaladeira/ramado, referencia de Ramado e Total Embalado);
    KG_TINGIMENTO = KILOS da fase 40. DIAS_PROD = uniao dos intervalos de operacao das maquinas da fase 150
    (MOVIMENTO_MAQUINA), para nao contar em dobro horas de maquinas paralelas (ver pendencias).
  - Categorias quimicas por subgrupo: 01 CORANTE, 02 AUXILIARES, 04 ACABAMENTO, 05 ETA/ETE,
    07 COMMODITIES (hipotese, nao confirmada). Cavaco = item CODIGO 'CAV0001'.
PENDENCIAS (ver relatorio): estoque final e consumo fisicos de cavaco e ETA/ETE nao existem
          no banco; DIAS_PROD nao reproduz o valor de referencia; saidas de ETA/ETE do periodo
          so aparecem no ERP com data posterior ao dia 15.
============================================================================= */

WITH PARAM AS (
    SELECT TRUNC(TO_DATE(:MES_REF, 'YYYY-MM'))                                   AS DT_INI,
           TRUNC(TO_DATE(:MES_REF, 'YYYY-MM')) + 15                              AS DT_FIM_EXCL,
           TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(TO_DATE(:MES_REF, 'YYYY-MM')), -1), 'YYYYMM')) AS AM_ANT
      FROM DUAL
),
CLASSIF AS (
    -- Uma linha por item de estoque, com a categoria do relatorio (dedupe por CODIGO_REDUZIDO)
    SELECT CD, CATEGORIA
      FROM (
            SELECT ITE.CODIGO_REDUZIDO AS CD,
                   CASE
                       WHEN TRIM(ITE.CODIGO) = 'CAV0001'                                    THEN 'CAVACO'
                       WHEN ITE.TIPO_ITEM = 5 AND SUBSTR(GSC.CDSUBGRUPO, 9, 2) = '01'      THEN 'CORANTE'
                       WHEN ITE.TIPO_ITEM = 5 AND SUBSTR(GSC.CDSUBGRUPO, 9, 2) = '02'      THEN 'AUXILIARES'
                       WHEN ITE.TIPO_ITEM = 5 AND SUBSTR(GSC.CDSUBGRUPO, 9, 2) = '04'      THEN 'ACABAMENTO'
                       WHEN ITE.TIPO_ITEM = 5 AND SUBSTR(GSC.CDSUBGRUPO, 9, 2) = '05'      THEN 'ETA/ETE'
                       WHEN ITE.TIPO_ITEM = 5 AND SUBSTR(GSC.CDSUBGRUPO, 9, 2) = '07'      THEN 'COMMODITIES'
                   END AS CATEGORIA,
                   ROW_NUMBER() OVER (PARTITION BY ITE.CODIGO_REDUZIDO ORDER BY GSC.CDSUBGRUPO) AS RN
              FROM SGTPRD.ITENS_ESTOQUE ITE
              LEFT JOIN SGTPRD.ENGEITEMESTOCLASSE GSC ON GSC.CDREDUZIDO = ITE.CODIGO_REDUZIDO
             WHERE ITE.TIPO_ITEM IN (5, 6)
           )
     WHERE RN = 1
       AND CATEGORIA IS NOT NULL
),
ABERTURA AS (
    -- Saldo do fechamento do mes anterior (estoque inicial), por item
    -- SALDO_ATUAL inclui a parcela bloqueada (QUANTIDADE_BLOQUEADA); o estoque livre e o que o ERP carrega
    SELECT F.CODIGO_REDUZIDO_INSU                                                  AS CD,
           SUM(F.SALDO_ATUAL - NVL(F.QUANTIDADE_BLOQUEADA, 0))                     AS QT_INI,
           SUM((F.SALDO_ATUAL - NVL(F.QUANTIDADE_BLOQUEADA, 0)) * NVL(V.VLFINAL, 0)) AS VL_INI
      FROM SGTPRD.FECHAMENTO_ESTOQUE_A F
      LEFT JOIN SGTPRD.FECHAMENTO_VALOR V
        ON V.CDFILIAL            = F.CDFILIAL
       AND V.ANO_MES_FECHAMENTO  = F.ANO_MES_FECHAMENTO
       AND V.CODIGO_REDUZIDO_INSU = F.CODIGO_REDUZIDO_INSU
       AND V.CONTA_CONTABIL      = F.CONTA_CONTABIL
       AND V.CDUNIDADENEGOCIO    = F.CDUNIDADENEGOCIO
       AND V.TIPO_VALORIZACAO    = 0
       AND V.OPCAO_MOEDA         = 0
     WHERE F.ANO_MES_FECHAMENTO = (SELECT AM_ANT FROM PARAM)
     GROUP BY F.CODIGO_REDUZIDO_INSU
),
MOVIMENTO AS (
    -- Entradas (com valor) e saidas do periodo, por item
    SELECT M.CDREDUZIDO                                                          AS CD,
           SUM(CASE WHEN M.TIOPERACAO = 1 THEN M.QTMOVIMENTO ELSE 0 END)         AS QT_ENT,
           SUM(CASE WHEN M.TIOPERACAO = 1 THEN M.QTMOVIMENTO * NVL(V.VLMOVIMENTO, 0) ELSE 0 END) AS VL_ENT,
           SUM(CASE WHEN M.TIOPERACAO = 2 THEN M.QTMOVIMENTO ELSE 0 END)         AS QT_SAI
      FROM SGTPRD.GERAMOVIMENTOESTOQUE M
      LEFT JOIN SGTPRD.MOVIMENTACAO_VALOR V
        ON V.NUMERO_MOVIMENTO = M.ID
       AND V.TIPO_VALORIZACAO = 0
       AND V.OPCAO_MOEDA      = 0
     WHERE M.DTDOCUMENTO >= (SELECT DT_INI     FROM PARAM)
       AND M.DTDOCUMENTO <  (SELECT DT_FIM_EXCL FROM PARAM)
       AND M.STMOVIMENTO = 0
       AND M.STGERAESTOBLOQ = 0
       AND M.NRTIPOMOVIMENTO <> 999
       AND M.TIOPERACAO IN (1, 2)
     GROUP BY M.CDREDUZIDO
),
ITEM AS (
    -- Estoque por item com custo medio do periodo (saidas e saldo final valorizados a custo medio)
    SELECT C.CATEGORIA,
           C.CD,
           NVL(A.QT_INI, 0)  AS QT_INI,
           NVL(A.VL_INI, 0)  AS VL_INI,
           NVL(MV.QT_ENT, 0) AS QT_ENT,
           NVL(MV.VL_ENT, 0) AS VL_ENT,
           NVL(MV.QT_SAI, 0) AS QT_SAI
      FROM CLASSIF C
      LEFT JOIN ABERTURA A  ON A.CD  = C.CD
      LEFT JOIN MOVIMENTO MV ON MV.CD = C.CD
     WHERE NVL(A.QT_INI, 0) <> 0 OR NVL(MV.QT_ENT, 0) <> 0 OR NVL(MV.QT_SAI, 0) <> 0
),
ITEM_VAL AS (
    SELECT I.CATEGORIA,
           I.QT_INI,
           I.VL_INI,
           I.QT_ENT,
           I.VL_ENT,
           I.QT_SAI,
           I.QT_INI + I.QT_ENT - I.QT_SAI                                         AS QT_FIM,
           (I.VL_INI + I.VL_ENT) / NULLIF(I.QT_INI + I.QT_ENT, 0)                 AS VL_UNIT_MEDIO
      FROM ITEM I
),
ITEM_FIM AS (
    SELECT IV.CATEGORIA,
           IV.QT_INI, IV.VL_INI,
           IV.QT_ENT, IV.VL_ENT,
           IV.QT_SAI,
           NVL(IV.QT_SAI * IV.VL_UNIT_MEDIO, 0)                                   AS VL_SAI,
           IV.QT_FIM,
           NVL(IV.QT_FIM * IV.VL_UNIT_MEDIO, 0)                                   AS VL_FIM
      FROM ITEM_VAL IV
),
CATEGORIA_BASE AS (
    SELECT CATEGORIA,
           COUNT(*)                 AS QT_ITENS,
           SUM(QT_INI)              AS QT_INI,
           SUM(VL_INI)              AS VL_INI,
           SUM(QT_ENT)              AS QT_ENT,
           SUM(VL_ENT)              AS VL_ENT,
           SUM(QT_SAI)              AS QT_SAI,
           SUM(VL_SAI)              AS VL_SAI,
           SUM(QT_FIM)              AS QT_FIM,
           SUM(VL_FIM)              AS VL_FIM
      FROM ITEM_FIM
     GROUP BY CATEGORIA
),
-- Total de produtos quimicos = soma das categorias quimicas (exclui cavaco); somatorio de valores e
-- quantidades, nunca de razoes (unitarios e consumo/kg sao recalculados depois)
CATEGORIA AS (
    SELECT CATEGORIA, QT_ITENS, QT_INI, VL_INI, QT_ENT, VL_ENT, QT_SAI, VL_SAI, QT_FIM, VL_FIM
      FROM CATEGORIA_BASE
    UNION ALL
    SELECT 'TOTAL QUIMICOS', SUM(QT_ITENS), SUM(QT_INI), SUM(VL_INI), SUM(QT_ENT), SUM(VL_ENT),
           SUM(QT_SAI), SUM(VL_SAI), SUM(QT_FIM), SUM(VL_FIM)
      FROM CATEGORIA_BASE
     WHERE CATEGORIA <> 'CAVACO'
),
ORDEM AS (
    SELECT 1 AS ORD, 'CORANTE'        AS CATEGORIA FROM DUAL UNION ALL
    SELECT 2,        'AUXILIARES'                  FROM DUAL UNION ALL
    SELECT 3,        'ACABAMENTO'                  FROM DUAL UNION ALL
    SELECT 4,        'ETA/ETE'                     FROM DUAL UNION ALL
    SELECT 5,        'COMMODITIES'                 FROM DUAL UNION ALL
    SELECT 6,        'TOTAL QUIMICOS'              FROM DUAL UNION ALL
    SELECT 7,        'CAVACO'                      FROM DUAL
),
MAQUINAS_PROD AS (
    -- Maquinas que produziram fase 150 no periodo (dado de producao, nao lista fixa)
    SELECT DISTINCT B.NUMERO_MAQUINA
      FROM SGTPRD.BD_BNF_PRODUCAO_FASE B, PARAM P
     WHERE B.CODIGO_FASE = 150
       AND B.DATA_FIM >= P.DT_INI
       AND B.DATA_FIM <  P.DT_FIM_EXCL
),
INTERVALO_MAQ AS (
    -- Intervalos de operacao das maquinas (TEMPO_* em minutos desde 01/01/1996), inicio dentro do periodo
    SELECT M.TEMPO_INICIAL AS S, M.TEMPO_FINAL AS E
      FROM SGTPRD.MOVIMENTO_MAQUINA M, PARAM P
     WHERE M.NUMERO_MAQUINA IN (SELECT NUMERO_MAQUINA FROM MAQUINAS_PROD)
       AND M.TEMPO_FINAL > M.TEMPO_INICIAL
       AND M.TEMPO_INICIAL >= (P.DT_INI - DATE '1996-01-01') * 1440
       AND M.TEMPO_INICIAL <  (P.DT_FIM_EXCL - DATE '1996-01-01') * 1440
),
INTERVALO_ACUM AS (
    SELECT S, E, MAX(E) OVER (ORDER BY S, E ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS PMAX
      FROM INTERVALO_MAQ
),
DIAS_UNIAO AS (
    -- Tempo com pelo menos uma maquina produzindo (uniao dos intervalos), em dias
    SELECT SUM(GREATEST(0, E - GREATEST(S, NVL(PMAX, S)))) / 1440 AS DIAS
      FROM INTERVALO_ACUM
),
PRODUCAO AS (
    SELECT SUM(CASE WHEN B.CODIGO_FASE = 150 THEN B.KILOS END)                    AS KG_RAMADO,
           SUM(CASE WHEN B.CODIGO_FASE = 40  THEN B.KILOS END)                    AS KG_TINGIMENTO,
           (SELECT DIAS FROM DIAS_UNIAO)                                          AS DIAS_PROD,
           SUM(CASE WHEN B.CODIGO_FASE = 150 THEN B.MIN_REAL END) / 1440          AS DIAS_SOMA_MIN_REAL,
           COUNT(DISTINCT CASE WHEN B.CODIGO_FASE = 150 THEN TRUNC(B.DATA_FIM) END) AS DIAS_CALENDARIO
      FROM SGTPRD.BD_BNF_PRODUCAO_FASE B, PARAM P
     WHERE B.CODIGO_FASE IN (40, 150)
       AND B.DATA_FIM >= P.DT_INI
       AND B.DATA_FIM <  P.DT_FIM_EXCL
)
SELECT O.ORD,
       O.CATEGORIA,
       CASE WHEN CT.CATEGORIA IS NULL THEN 'SEM ITENS' ELSE 'OK' END          AS SITUACAO,
       CT.QT_ITENS,
       CT.QT_INI,
       CT.VL_INI,
       CT.QT_ENT                                                              AS QT_COMPRAS,
       CT.VL_ENT                                                              AS VL_COMPRAS,
       CT.QT_SAI                                                              AS QT_CONSUMO,
       CT.VL_SAI                                                              AS VL_CONSUMO,
       CT.QT_FIM,
       CT.VL_FIM,
       CT.VL_INI / NULLIF(CT.QT_INI, 0)                                       AS VL_UNIT_INI,
       CT.VL_ENT / NULLIF(CT.QT_ENT, 0)                                       AS VL_UNIT_COMPRAS,
       CT.VL_FIM / NULLIF(CT.QT_FIM, 0)                                       AS VL_UNIT_FIM,
       CT.VL_SAI / NULLIF(PR.KG_RAMADO, 0)                                    AS VL_CONSUMO_POR_KG,
       CT.QT_SAI / NULLIF(PR.DIAS_PROD, 0)                                    AS QT_CONSUMO_POR_DIA,
       CT.QT_SAI / NULLIF(PR.KG_RAMADO / 1000, 0)                             AS QT_CONSUMO_POR_TON,
       PR.KG_TINGIMENTO,
       PR.KG_RAMADO,
       PR.KG_RAMADO                                                           AS KG_TOTAL_EMBALADO,
       PR.DIAS_PROD,
       PR.DIAS_CALENDARIO
  FROM ORDEM O
  LEFT JOIN CATEGORIA CT ON CT.CATEGORIA = O.CATEGORIA
 CROSS JOIN PRODUCAO PR
 ORDER BY O.ORD
