/* =============================================================================
OBJETIVO: Aging das OBs montadas em aberto por fase atual, em faixas de dias parados, com quantidade fora do SLA
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Painel/KPI
GRÃO: CODIGO_FASE + FAIXA_AGING (uma linha por fase atual e faixa de dias parados)
PARÂMETROS / BINDS: Nenhum. O SLA é a constante SLA_DIAS da CTE PARAMETROS (premissa a confirmar).
TABELAS PRINCIPAIS: SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.PEDPRODUCAOOB, SGTPRD.FASES_FLUXO, SGTPRD.GERAPECAORIGEMOB, SGTPRD.GERAPECASPRODUTO
CUIDADOS OPERACIONAIS: Somente leitura. Mesma definição de "OB em aberto" e de "fase atual" de
  bnf_posicao_atual_obs_em_aberto.sql (OB.STATUS <> 0, PEDPRODUCAOOB.SETOR = 5 e OBMONTADA = 1;
  fase atual = menor sequência com OB_FASES.STATUS em 1/2/3, ou a última se todas estiverem
  fora desse conjunto).
  DIAS_PARADO = SYSDATE - última confirmação de fase (TEMPO_FINAL_CONFIRMA, minutos desde
  1996-01-01). OB sem nenhuma confirmação vai para a faixa "99. SEM CONFIRMACAO".
  Diferente da consulta-base, NÃO exige cadastro de cor/artigo/complemento (JOINs internos
  em ENGEITEMESTOCOR/ENGEITEMESTOARTCRU/ITENS_COMPLEMENTO), que fazem OBs sumirem do total.
  KG_REAL = peso líquido das peças de origem já montadas (GERAPECASPRODUTO); OB sem peça
  montada conta com 0 kg.
  SLA_DIAS = 3 é uma premissa única, não um SLA validado por fase: ajuste antes de usar
  a coluna QT_FORA_SLA como indicador oficial.
============================================================================= */

WITH PARAMETROS AS (
    SELECT 3 AS SLA_DIAS FROM DUAL
),
OB_ATIVA AS (
    SELECT /*+ MATERIALIZE */
           OB.NUMERO_OB,
           OB.TIPO_ORDEM,
           COALESCE(
               MIN(CASE WHEN OBF.STATUS IN (1, 2, 3) THEN OBF.SEQUENCIA END),
               MAX(OBF.SEQUENCIA)
           ) AS SEQ_ATUAL,
           SYSDATE - (
               DATE '1996-01-01' + MAX(NULLIF(OBF.TEMPO_FINAL_CONFIRMA, 0)) / 1440
           ) AS DIAS_PARADO
      FROM SGTPRD.OB OB
      JOIN SGTPRD.PEDPRODUCAOOB PPO ON PPO.NUMEROOB = OB.NUMERO_OB
                                   AND PPO.SETOR = 5
                                   AND PPO.OBMONTADA = 1
      LEFT JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OB.NUMERO_OB
     WHERE OB.STATUS <> 0
     GROUP BY OB.NUMERO_OB, OB.TIPO_ORDEM
),
QT_OB AS (
    SELECT GPO.NUMERO_OB,
           COUNT(GPP.IDPECASPRODUTO) AS QT_PECAS,
           SUM(GPP.QTLIQUIDA)        AS QT_KILOS_REAL
      FROM SGTPRD.GERAPECAORIGEMOB GPO
      JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.IDPECASPRODUTO = GPO.IDPECASPRODUTO
      JOIN OB_ATIVA OBA ON OBA.NUMERO_OB = GPO.NUMERO_OB
     GROUP BY GPO.NUMERO_OB
),
POSICAO AS (
    SELECT OBA.NUMERO_OB,
           OBF.CODIGO_FASE,
           TRIM(FFL.DESCRICAO_FASE)  AS FASE_ATUAL,
           OBA.DIAS_PARADO,
           NVL(QT.QT_PECAS, 0)       AS QT_PECAS,
           NVL(QT.QT_KILOS_REAL, 0)  AS QT_KILOS_REAL
      FROM OB_ATIVA OBA
      JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OBA.NUMERO_OB
                              AND OBF.SEQUENCIA = OBA.SEQ_ATUAL
      JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
      LEFT JOIN QT_OB QT ON QT.NUMERO_OB = OBA.NUMERO_OB
     WHERE (OBA.TIPO_ORDEM = 0 OR OBF.CODIGO_FASE <> 10)
)
SELECT POS.CODIGO_FASE,
       POS.FASE_ATUAL,
       CASE
           WHEN POS.DIAS_PARADO IS NULL THEN '99. SEM CONFIRMACAO'
           WHEN POS.DIAS_PARADO <= 2    THEN '1. ATE 2 DIAS'
           WHEN POS.DIAS_PARADO <= 5    THEN '2. 3 A 5 DIAS'
           WHEN POS.DIAS_PARADO <= 10   THEN '3. 6 A 10 DIAS'
           ELSE                              '4. MAIS DE 10 DIAS'
       END                                            AS FAIXA_AGING,
       COUNT(*)                                       AS QT_OBS,
       SUM(POS.QT_PECAS)                              AS QT_PECAS,
       ROUND(SUM(POS.QT_KILOS_REAL), 1)               AS KG_REAL,
       SUM(CASE WHEN POS.DIAS_PARADO > PAR.SLA_DIAS THEN 1 ELSE 0 END) AS QT_FORA_SLA,
       ROUND(MAX(POS.DIAS_PARADO), 1)                 AS MAX_DIAS_PARADO
  FROM POSICAO POS
 CROSS JOIN PARAMETROS PAR
 GROUP BY POS.CODIGO_FASE,
          POS.FASE_ATUAL,
          CASE
              WHEN POS.DIAS_PARADO IS NULL THEN '99. SEM CONFIRMACAO'
              WHEN POS.DIAS_PARADO <= 2    THEN '1. ATE 2 DIAS'
              WHEN POS.DIAS_PARADO <= 5    THEN '2. 3 A 5 DIAS'
              WHEN POS.DIAS_PARADO <= 10   THEN '3. 6 A 10 DIAS'
              ELSE                              '4. MAIS DE 10 DIAS'
          END
 ORDER BY POS.CODIGO_FASE, FAIXA_AGING
