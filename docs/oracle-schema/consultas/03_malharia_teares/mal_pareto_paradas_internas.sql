/* =============================================================================
OBJETIVO: Pareto das paradas de teares internos por código, com participação
          acumulada e separação entre paradas curtas e longas (12 meses)
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: CODIGO_PARADA (uma linha por código de parada)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
  Limite de parada curta na CTE PARAM (CURTA_MAX_MIN = 15).
TABELAS PRINCIPAIS: SGTPRD.PARADAS_MAQUINA, SGTPRD.MOTIVOS_PARADAS,
  SGTPRD.MAQUINA, SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
COLUNAS:
  ORDEM_PARETO      posição por minutos (1 = maior perda; código sem minutos vai para o fim).
  EVENTOS           número de paradas do código.
  MINUTOS           minutos totais do código.
  PCT_MINUTOS       participação do código no total de minutos.
  PCT_ACUMULADO     participação acumulada (regra 80/20: onde cruza 80%, estão os
                    códigos que concentram a maior parte da perda). Códigos empatados
                    em MINUTOS compartilham o mesmo acumulado (RANGE, não ROWS).
  EVT_CURTAS        paradas de até CURTA_MAX_MIN minutos. Paradas curtas e frequentes
                    somam muito tempo no acumulado (ver estudos citados na pesquisa).
  MIN_CURTAS        minutos somados das paradas curtas do código.
  CALCULA_EFICIENCIA flag de MOTIVOS_PARADAS. '0' = não entra no cálculo de perda.
CUIDADOS OPERACIONAIS:
  - INÍCIO DE TURNO (MLC07) é lançado em lote (em 2025, 44 dias; REGRAS_NEGOCIO.md, 5.4) e
    lidera o Pareto por minutos com margem pequena: 20,1% contra 19,8% (MLC04) e 18,3% (MLC02),
    medido em 09/10/2026 (janela 01/10/2025 a 30/09/2026). A consulta não o separa: entra em
    MINUTOS e no RANK como os demais códigos. Ver mal_paradas_categoria_mes.sql e
    mal_qualidade_registro_paradas.sql.
  - Escopo: teares internos (TIPO_MAQUINA 145/146 em unidade com EH_FACCAO = 'N').
  - Código sem minutos (MINUTOS NULL: todas as paradas do código sem HORA_INICIO ou HORA_TERMINO)
    fica por último no ranking (NULLS LAST na RANK e na janela de PCT_ACUMULADO). Medido em
    09/10/2026, janela 01/10/2025 a 30/09/2026: 0 de 23 códigos com MINUTOS NULL.
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM,
           15                                                                    AS CURTA_MAX_MIN
      FROM DUAL
),
INTERNAS AS (
    SELECT DISTINCT MQI.NUMERO_MAQUINA
      FROM SGTPRD.MAQUINA MQI
      JOIN SGTPRD.GRUPO_MAQUINAS GMQ
        ON GMQ.GRUPO = MQI.GRUPO
       AND GMQ.SETOR = MQI.SETOR
      JOIN SGTPRD.UNIDADE_FABRIL UFM
        ON UFM.CODIGO_UNIDADE_FABRI = GMQ.UNIDADE_FABRIL
     WHERE MQI.TIPO_MAQUINA IN (145, 146)
       AND UFM.EH_FACCAO = 'N'
),
PARADAS_DUR AS (
    SELECT PM.CODIGO_PARADA,
           GREATEST(0,
               ((TO_DATE(TO_CHAR(PM.DATA_TERMINO), 'YYYYMMDD') + PM.HORA_TERMINO / 1440)
              - (TO_DATE(TO_CHAR(PM.DATA_INICIO),  'YYYYMMDD') + PM.HORA_INICIO  / 1440)) * 1440
           ) AS MIN_PARADA
      FROM PARAM
      JOIN SGTPRD.PARADAS_MAQUINA PM
        ON PM.SETOR = 4
       AND PM.DATA_INICIO >= PARAM.D_INI
       AND PM.DATA_INICIO <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = PM.NUMERO_MAQUINA
     WHERE PM.DATA_TERMINO IS NOT NULL
),
POR_CODIGO AS (
    SELECT PD.CODIGO_PARADA,
           COUNT(*)                                                        AS EVENTOS,
           ROUND(SUM(PD.MIN_PARADA), 0)                                    AS MINUTOS,
           SUM(CASE WHEN PD.MIN_PARADA <= PARAM.CURTA_MAX_MIN THEN 1 ELSE 0 END) AS EVT_CURTAS,
           ROUND(SUM(CASE WHEN PD.MIN_PARADA <= PARAM.CURTA_MAX_MIN THEN PD.MIN_PARADA ELSE 0 END), 0)
                                                                           AS MIN_CURTAS
      FROM PARADAS_DUR PD
      CROSS JOIN PARAM
     GROUP BY PD.CODIGO_PARADA
),
TOTAL AS (
    SELECT SUM(MINUTOS) AS MIN_TOTAL FROM POR_CODIGO
)
SELECT RANK() OVER (ORDER BY PC.MINUTOS DESC NULLS LAST)                     AS ORDEM_PARETO,
       PC.CODIGO_PARADA,
       TRIM(MP.DESCRICAO)                                                    AS DESCRICAO,
       MP.CALCULA_EFICIENCIA,
       PC.EVENTOS,
       PC.MINUTOS,
       ROUND(100 * PC.MINUTOS / NULLIF(T.MIN_TOTAL, 0), 1)                   AS PCT_MINUTOS,
       ROUND(100 * SUM(PC.MINUTOS) OVER (ORDER BY PC.MINUTOS DESC NULLS LAST
                                         RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / NULLIF(T.MIN_TOTAL, 0), 1)                                    AS PCT_ACUMULADO,
       PC.EVT_CURTAS,
       PC.MIN_CURTAS
  FROM POR_CODIGO PC
  CROSS JOIN TOTAL T
  LEFT JOIN SGTPRD.MOTIVOS_PARADAS MP
    ON MP.CODIGO_PARADA = PC.CODIGO_PARADA
   AND MP.SETOR = 4
 ORDER BY ORDEM_PARETO, PC.CODIGO_PARADA;
