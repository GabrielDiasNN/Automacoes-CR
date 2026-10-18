/* =============================================================================
OBJETIVO: KPI mensal de reprocesso na montagem de lote (fase 10), 12 meses + mês aberto: fases e kg reprocessados sobre o total.
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Painel/KPI
GRANULARIDADE: uma linha por mês
FONTE: SGTPRD.OB_FASES (fase 10, data pelo TEMPO_FINAL_CONFIRMA) com marcação de SGTPRD.BD_BNF_REPROC_UNICO
       (chave NUMERO_OB + SEQUENCIA; a tabela não tem data).
FATOS CONFIRMADOS NO ORACLE (17/10/2026):
  - A tabela de reprocesso tem 12.444 linhas, uma por sequência de OB (sem repetição).
  - Quase todas estão na fase 10 (montagem). O destino tem TIPO_DESTINO = 1 (reprocesso) na
    mesma definição usada em bnf_monitora_tingimento_e_reprocesso.
  - TEMPO_FINAL_CONFIRMA de OB_FASES é minutos desde 01/01/1996 (REGRAS_NEGOCIO.md).
LIMITES:
  - A marcação não tem data: o reprocesso é atribuído ao mês em que a fase foi confirmada.
  - Só a fase 10 entra no KPI. Reprocessos de outras fases não são contados aqui.
  - Escolha da fase 10: é a fase com quase todo o volume marcado (ver FATOS).
PARÂMETROS / BINDS: nenhum (janela automática).
============================================================================= */
WITH JAN AS (
    SELECT ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12) AS DT_INI,
           TRUNC(SYSDATE, 'MM')                  AS DT_ABERTO,
           TRUNC(SYSDATE) + 1                    AS DT_FIM
      FROM DUAL
),
FASE10 AS (
    SELECT TRUNC(DATE '1996-01-01' + F.TEMPO_FINAL_CONFIRMA / 1440, 'MM') AS DT_MES,
           F.KILOS_PRODUZIDOS                                             AS KG,
           CASE WHEN R.NUMERO_OB IS NOT NULL THEN 1 ELSE 0 END           AS REPROC
      FROM SGTPRD.OB_FASES F
      LEFT JOIN SGTPRD.BD_BNF_REPROC_UNICO R
             ON R.NUMERO_OB = F.NUMERO_OB
            AND R.SEQUENCIA = F.SEQUENCIA
     CROSS JOIN JAN
     WHERE F.CODIGO_FASE = 10
       AND F.TEMPO_FINAL_CONFIRMA >= (JAN.DT_INI - DATE '1996-01-01') * 1440
       AND F.TEMPO_FINAL_CONFIRMA <  (JAN.DT_FIM - DATE '1996-01-01') * 1440
)
SELECT TO_CHAR(F.DT_MES, 'YYYY-MM')                                       AS COMPETENCIA,
       CASE WHEN F.DT_MES >= JAN.DT_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END AS STATUS_MES,
       COUNT(*)                                                           AS FASES_MONTAGEM,
       SUM(F.REPROC)                                                      AS FASES_REPROCESSO,
       ROUND(100 * SUM(F.REPROC) / NULLIF(COUNT(*), 0), 2)                AS PERC_FASES_REPROC,
       ROUND(SUM(F.KG), 0)                                                AS KG_MONTAGEM,
       ROUND(SUM(F.REPROC * F.KG), 0)                                     AS KG_REPROCESSO,
       ROUND(100 * SUM(F.REPROC * F.KG) / NULLIF(SUM(F.KG), 0), 2)        AS PERC_KG_REPROC
  FROM FASE10 F
 CROSS JOIN JAN
 GROUP BY F.DT_MES, CASE WHEN F.DT_MES >= JAN.DT_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END
 ORDER BY F.DT_MES
