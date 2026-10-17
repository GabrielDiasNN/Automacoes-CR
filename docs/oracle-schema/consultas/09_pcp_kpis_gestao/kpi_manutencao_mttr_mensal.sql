/* =============================================================================
OBJETIVO: KPI mensal de manutenção: OMs solicitadas, concluídas e MTTR (horas) por família (12 meses + mês aberto).
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: SELECT (Painel/KPI)
FONTE: SGTPRD.ORDEMMANUTENCAO (uma linha por OM).
FATOS CONFIRMADOS NO ORACLE (16/10/2026):
  - SITUACAO = 1 é a OM concluída: 1.804 OMs nos últimos 12 meses (17/10/2026; a janela é móvel, 1.808 em 16/10), todas com
    DTINICIO_REAL, DTTERMINO_REAL e DTCONFIRMACAO preenchidos.
  - SITUACAO = 0 é OM ainda não executada (184 OMs, sem datas reais). Não entra no MTTR.
  - SITUACAO = 4 tem confirmação e nenhuma data real (250 OMs); o significado ainda
    não está confirmado, então NÃO entra no MTTR nem em concluídas.
  - TIPO_MANUTENCAO começa com 'NT-' seguido da família (FIACAO, TINTURARIA, MALHARIA).
LIMITE: o tempo de execução da OM é o intervalo entre o início e o término reais
  registrados na própria OM. NÃO é tempo de parada da máquina: PARADAS_MAQUINA não
  tem vínculo com a OM (ver REGRAS_NEGOCIO.md, seção de manutenção).
  PADRÃO DE 168 H (verificado em 17/10/2026, OMs concluídas nos últimos 12 meses): FIACAO tem
  350 de 789 (44%) com duração de pelo menos 167 h e em múltiplo de 168 h (tolerância de 1 h).
  TINTURARIA e MALHARIA têm 0 nesse padrão. Tinturaria tem 201 OMs abaixo de 1 h (mediana de 1 h).
  Esse padrão de FIACAO indica tempo de calendário com a OM aberta, não esforço de reparo.
  A coluna EXEC_MULT_168H mostra a contagem por mês e família. A engenharia de manutenção deve
  confirmar a regra antes de usar o MTTR da FIACAO como indicador de reparo.
PARÂMETROS / BINDS: nenhum (janela automática).
============================================================================= */
WITH JANELA AS (
    SELECT ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12) AS DT_INICIO,
           TRUNC(SYSDATE, 'MM')                  AS DT_MES_ABERTO,
           TRUNC(SYSDATE) + 1                    AS DT_FIM
      FROM DUAL
),
OM_BASE AS (
    SELECT TRUNC(OM.DTSOLICITACAO, 'MM')                                  AS DT_MES,
           REGEXP_SUBSTR(OM.TIPO_MANUTENCAO, '^NT-[^ ]+')                 AS TIPO_NT,
           OM.SITUACAO,
           CASE WHEN OM.SITUACAO = 1
                 AND OM.DTTERMINO_REAL >= OM.DTINICIO_REAL
                THEN (OM.DTTERMINO_REAL - OM.DTINICIO_REAL) * 24 END       AS HORAS_EXEC
      FROM SGTPRD.ORDEMMANUTENCAO OM
     CROSS JOIN JANELA JAN
     WHERE OM.DTSOLICITACAO >= JAN.DT_INICIO
       AND OM.DTSOLICITACAO <  JAN.DT_FIM
       AND OM.TIPO_MANUTENCAO LIKE 'NT-%'
)
SELECT TO_CHAR(OB.DT_MES, 'YYYY-MM')                                       AS COMPETENCIA,
       CASE WHEN OB.DT_MES >= JAN.DT_MES_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END AS STATUS_MES,
       REPLACE(OB.TIPO_NT, 'NT-', '')                                       AS FAMILIA,
       COUNT(*)                                                             AS OM_SOLICITADAS,
       SUM(CASE WHEN OB.SITUACAO = 1 THEN 1 ELSE 0 END)                     AS OM_CONCLUIDAS,
       SUM(CASE WHEN OB.SITUACAO = 0 THEN 1 ELSE 0 END)                     AS OM_NAO_EXECUTADAS,
       SUM(CASE WHEN OB.SITUACAO = 4 THEN 1 ELSE 0 END)                     AS OM_SITUACAO_4,
       SUM(CASE WHEN OB.HORAS_EXEC IS NOT NULL
                 AND OB.HORAS_EXEC >= 167
                 AND (ABS(MOD(OB.HORAS_EXEC, 168)) < 1 OR ABS(MOD(OB.HORAS_EXEC, 168) - 168) < 1)
                THEN 1 ELSE 0 END)                                              AS EXEC_MULT_168H,
       ROUND(AVG(OB.HORAS_EXEC), 2)                                         AS MTTR_MEDIO_H,
       ROUND(MEDIAN(OB.HORAS_EXEC), 2)                                      AS MTTR_MEDIANO_H,
       ROUND(MAX(OB.HORAS_EXEC), 2)                                         AS MTTR_MAX_H
  FROM OM_BASE OB
 CROSS JOIN JANELA JAN
 GROUP BY OB.DT_MES, CASE WHEN OB.DT_MES >= JAN.DT_MES_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END,
          REPLACE(OB.TIPO_NT, 'NT-', '')
 ORDER BY OB.DT_MES, FAMILIA
