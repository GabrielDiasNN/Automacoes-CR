/* =============================================================================
OBJETIVO: Diagnóstico Diário de Ritmo Líquido, Tempos de Setup e Gaps Ociosos nas Ramas
DOMÍNIO: 02_acabamento_preparacao
TIPO: Painel/KPI
GRÃO: DATA_PROD + RAMA (uma linha por dia de produção e rama)
PARÂMETROS / BINDS: Nenhum (janela dinâmica de 30 dias até hoje)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.MAQUINA
CUIDADOS OPERACIONAIS: Somente leitura. Utiliza janela analítica LAG para apuração de intervalos inter-lote.
  Só entra apontamento concluído (STATUS = 0): STATUS 1 (em execução) e 3 (na fila, sem início) são
  programação, não produção, e inflavam kg e horas do dia corrente. As ramas vêm de MAQUINA (GRUPO RM001,
  SETOR 5), como nas demais consultas de rama. O LAG é calculado antes do filtro MIN_REAL > 1, para que um
  apontamento sem duração entre dois lotes não infle o intervalo. O filtro MIN_REAL > 1 descarta apontamentos
  sem duração mensurável (cerca de 6% dos kg da janela): eles não servem para ritmo, mas ficam de fora de
  KG_TOTAL. Intervalos de até 30 min são setup/troca; de 30 min a 24 h são gap de desabastecimento; acima de
  24 h são parada prolongada (fim de semana, manutenção ou parada planejada) e saem numa coluna própria, sem
  contaminar o ritmo efetivo nem o gap operacional.
============================================================================= */

WITH APONTAMENTOS AS (
    SELECT /*+ MATERIALIZE */
        PR.NUMERO_MAQUINA,
        PR.DATA_FIM,
        PR.NUMERO_OB,
        PR.KILOS,
        PR.METROS,
        PR.MIN_REAL,
        PR.VELOCIDADE,
        PR.DATA_HORA_INI,
        PR.DATA_HORA_FIM,
        LAG(PR.DATA_HORA_FIM) OVER (
            PARTITION BY PR.NUMERO_MAQUINA
            ORDER BY PR.DATA_HORA_INI, PR.DATA_HORA_FIM, PR.NUMERO_OB
        ) AS DTHR_FIM_ANTERIOR
    FROM SGTPRD.BD_BNF_PRODUCAO_FASE PR
    WHERE PR.NUMERO_MAQUINA IN (
              SELECT MAQ.NUMERO_MAQUINA
              FROM SGTPRD.MAQUINA MAQ
              WHERE MAQ.GRUPO = 'RM001'
                AND MAQ.SETOR = 5
          )
      AND PR.STATUS = 0
      AND PR.KILOS > 0
      AND PR.DATA_FIM >= TRUNC(SYSDATE) - 30
      AND PR.DATA_FIM <= TRUNC(SYSDATE)
),
COM_INTERVALOS AS (
    SELECT
        AP.*,
        GREATEST(0, ROUND((AP.DATA_HORA_INI - AP.DTHR_FIM_ANTERIOR) * 1440, 1)) AS GAP_MINUTOS
    FROM APONTAMENTOS AP
    WHERE AP.MIN_REAL > 1
)
SELECT
    TRUNC(DATA_FIM) AS DATA_PROD,
    LTRIM(NUMERO_MAQUINA, '0') AS RAMA,
    COUNT(DISTINCT NUMERO_OB) AS TOTAL_LOTES,
    ROUND(SUM(KILOS), 1) AS KG_TOTAL,
    ROUND(SUM(METROS), 1) AS METROS_TOTAL,
    -- Tempos segregados (em horas)
    ROUND(SUM(MIN_REAL) / 60, 2) AS HORAS_LIQUIDAS_PROCESSO,
    ROUND(SUM(CASE WHEN GAP_MINUTOS <= 30 THEN GAP_MINUTOS ELSE 0 END) / 60, 2) AS HORAS_SETUP_TROCA,
    ROUND(SUM(CASE WHEN GAP_MINUTOS > 30 AND GAP_MINUTOS <= 1440 THEN GAP_MINUTOS ELSE 0 END) / 60, 2) AS HORAS_GAPS_DESABASTECIMENTO,
    ROUND(SUM(CASE WHEN GAP_MINUTOS > 1440 THEN GAP_MINUTOS ELSE 0 END) / 60, 2) AS HORAS_PARADA_PROLONGADA,
    -- Ritmos reais
    ROUND(SUM(KILOS) / NULLIF(SUM(MIN_REAL) / 60, 0), 1) AS KG_HORA_LIQUIDA,
    ROUND(SUM(KILOS) / NULLIF((SUM(MIN_REAL) + SUM(CASE WHEN GAP_MINUTOS <= 30 THEN GAP_MINUTOS ELSE 0 END)) / 60, 0), 1) AS KG_HORA_EFETIVA,
    ROUND(SUM(VELOCIDADE * MIN_REAL) / NULLIF(SUM(MIN_REAL), 0), 1) AS VELOCIDADE_MEDIA_M_MIN
FROM COM_INTERVALOS
GROUP BY TRUNC(DATA_FIM), NUMERO_MAQUINA
ORDER BY DATA_PROD DESC, RAMA;
