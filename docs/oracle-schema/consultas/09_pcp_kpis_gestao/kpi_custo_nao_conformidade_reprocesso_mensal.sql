/* =============================================================================
OBJETIVO: KPI mensal de custo de não conformidade (NC) e reprocesso por setor produtivo (12 meses + mês aberto).
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: SELECT (Painel/KPI)
FONTE: SGTPRD.CUSTO_PRODUCAO_QUANT (quantidade e tempo, uma linha por dia/item/setor/tipo)
       + SGTPRD.CUSTO_PRODUCAO_VALOR (valores, mesma chave ID_CUSTO_PRODUCAO_QT).
FATOS CONFIRMADOS NO ORACLE (16/10/2026, desde 01/09/2025):
  - A junção Q -> V é 1 para 1: 5.709 de 5.710 linhas do TIPO_REG 2 têm valor.
  - Quantidade de NC (QTD_NC) só aparece no TIPO_REG 2 do SETOR_PRODUTIVO 9
    (124.601 kg). Os demais setores e o TIPO_REG 0 têm QTD_NC = 0.
  - Custo de NC (CUSTO_NC_*) também só existe no caso acima: a soma é 1,96 milhão.
  - A data é numérica no formato AAAAMMDD (campo DATA).
LIMITES:
  - Inconsistência conhecida: em 2025-10 há custo de NC (29 mil) com QTD_NC = 0. Nos
    demais meses, custo de NC e kg de NC aparecem juntos. Conferir a origem antes de
    usar o custo de NC desse mês.
  - O significado do código SETOR_PRODUTIVO não está documentado no acervo. Por isso o
    KPI agrupa pelo código, sem dar nome ao setor. Confirmar com o PCP antes de rotular.
  - O significado do TIPO_REG não está documentado; o KPI o mantém como coluna.
  - A unidade monetária segue o cadastro de custo (não confirmada no acervo).
PARÂMETROS / BINDS: nenhum (janela automática).
============================================================================= */
WITH JANELA AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS DT_INICIO_NUM,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS DT_MES_ABERTO_NUM,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE) + 1, 'YYYYMMDD'))                    AS DT_FIM_NUM
      FROM DUAL
),
BASE AS (
    SELECT /*+ MATERIALIZE */
           TRUNC(TO_DATE(Q.DATA, 'YYYYMMDD'), 'MM')         AS DT_MES,
           Q.SETOR_PRODUTIVO,
           Q.TIPO_REG,
           SUM(Q.QTPRODUZIDA)                              AS KG_PRODUZIDO,
           SUM(Q.QTD_NC)                                   AS KG_NC,
           SUM(Q.QTD_REPROCESSO)                           AS KG_REPROC,
           SUM(V.CUSTO_NC_MP + V.CUSTO_NC_GGF + V.CUSTO_NC_QUIMICO
             + V.CUSTO_NC_EMB + V.CUSTO_NC_FACCAO)         AS CUSTO_NC,
           SUM(V.CUSTO_MP_REPROC + V.CUSTO_GGF_REPROC + V.CUSTO_QUIM_REPROC
             + V.CUSTO_EMB_REPROC + V.CUSTO_FAC_REPROC)    AS CUSTO_REPROC,
           SUM(V.CUSTO_MP + V.CUSTO_GGF + V.CUSTO_QUIMICO
             + V.CUSTO_EMBALAGEM + V.CUSTO_FACCAO)         AS CUSTO_PRODUCAO
      FROM SGTPRD.CUSTO_PRODUCAO_QUANT Q
      LEFT JOIN SGTPRD.CUSTO_PRODUCAO_VALOR V
             ON V.ID_CUSTO_PRODUCAO_QT = Q.ID_CUSTO_PRODUCAO_QT
     CROSS JOIN JANELA JAN
     WHERE Q.DATA >= JAN.DT_INICIO_NUM
       AND Q.DATA <  JAN.DT_FIM_NUM
     GROUP BY TRUNC(TO_DATE(Q.DATA, 'YYYYMMDD'), 'MM'), Q.SETOR_PRODUTIVO, Q.TIPO_REG
)
SELECT TO_CHAR(B.DT_MES, 'YYYY-MM')                                        AS COMPETENCIA,
       CASE WHEN TO_NUMBER(TO_CHAR(B.DT_MES, 'YYYYMMDD')) >= JAN.DT_MES_ABERTO_NUM
            THEN 'EM ABERTO' ELSE 'FECHADO' END                             AS STATUS_MES,
       B.SETOR_PRODUTIVO,
       B.TIPO_REG,
       ROUND(B.KG_PRODUZIDO, 0)                                             AS KG_PRODUZIDO,
       ROUND(B.KG_NC, 0)                                                    AS KG_NC,
       ROUND(100 * B.KG_NC / NULLIF(B.KG_PRODUZIDO, 0), 2)                  AS PERC_NC,
       ROUND(B.KG_REPROC, 0)                                                AS KG_REPROCESSO,
       ROUND(100 * B.KG_REPROC / NULLIF(B.KG_PRODUZIDO, 0), 2)              AS PERC_REPROCESSO,
       ROUND(B.CUSTO_NC, 2)                                                 AS CUSTO_NC,
       ROUND(B.CUSTO_REPROC, 2)                                             AS CUSTO_REPROCESSO,
       ROUND(100 * B.CUSTO_NC / NULLIF(B.CUSTO_PRODUCAO, 0), 2)             AS PERC_CUSTO_NC
  FROM BASE B
 CROSS JOIN JANELA JAN
 ORDER BY B.DT_MES, B.SETOR_PRODUTIVO, B.TIPO_REG
