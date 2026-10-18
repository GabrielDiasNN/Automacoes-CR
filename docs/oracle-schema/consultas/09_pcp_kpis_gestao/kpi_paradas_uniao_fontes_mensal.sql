/* =============================================================================
OBJETIVO: Paradas de máquina por mês e setor, unindo as duas fontes oficiais sem contar o mesmo evento duas vezes (12 meses + mês aberto).
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Painel/KPI
GRANULARIDADE: uma linha por mês, setor e origem (EVENTO_NA_BD = registro da BD_PRD_PARADAS_MAQ; SO_PARADAS_MAQUINA = registro da PARADAS_MAQUINA sem par na BD)
FONTES: SGTPRD.BD_PRD_PARADAS_MAQ (registro de evento, DATE) e SGTPRD.PARADAS_MAQUINA (registro de evento, data em AAAAMMDD numérico e hora em minutos do dia).
REGRA DE IDENTIDADE: dois registros são o mesmo evento quando têm a mesma máquina e os intervalos se sobrepõem em pelo menos 50% do menor dos dois.
  Todo registro da BD entra. Um registro da PARADAS_MAQUINA só entra se não tiver par na BD.
FATOS CONFIRMADOS NO ORACLE (17/10/2026, janela de out/2025 a out/2026, medido com esta consulta):
  - EVENTO_NA_BD: 28.095 eventos (todos os eventos da BD com fim válido).
  - SO_PARADAS_MAQUINA: 27 eventos da PARADAS_MAQUINA sem par na BD. Total de eventos únicos: 28.122.
  - Setor 5 (tingimento): 1.668 eventos, todos da BD. A PARADAS_MAQUINA não acrescenta nenhum.
  - Janela inteira de 13 meses: não há divisão por mês, então eventos que atravessam a virada do mês casam com o par certo.
LIMITES:
  - Dez/2025 setor 2 tem a PARADAS_MAQUINA com volume baixo (852 contra 1.000 a 1.300 nos outros meses). Pode ser carga incompleta. Confirmar com a TI.
  - Setor 217 só existe na BD (6 eventos). Significado não confirmado.
  - Códigos fora de MOTIVOS_PARADAS (cadastro): 59 registros da PARADAS_MAQUINA e 91 da BD. Entram na contagem, sem descrição.
  - A identidade é por sobreposição, não por horário exato. Com horário exato, o total casado seria menor.
PARÂMETROS / BINDS: nenhum (janela automática).
============================================================================= */
WITH JAN AS (
    SELECT ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12) AS DT_INI,
           TRUNC(SYSDATE, 'MM')                  AS DT_ABERTO,
           TRUNC(SYSDATE) + 1                    AS DT_FIM
      FROM DUAL
),
BD AS (
    SELECT B.ID AS ID_BD, B.SETOR, B.NUMERO_MAQUINA AS MAQ,
           B.DATA_HORA_INI AS INI, B.DATA_HORA_FIM AS FIM
      FROM SGTPRD.BD_PRD_PARADAS_MAQ B
     CROSS JOIN JAN
     WHERE B.DATA_HORA_INI >= JAN.DT_INI
       AND B.DATA_HORA_INI <  JAN.DT_FIM
       AND B.DATA_HORA_FIM >  B.DATA_HORA_INI
),
PM AS (
    SELECT P.NUMERO_PARADA AS ID_PM, P.SETOR, P.NUMERO_MAQUINA AS MAQ,
           TO_DATE(TO_CHAR(P.DATA_INICIO), 'YYYYMMDD') + NVL(P.HORA_INICIO, 0) / 1440  AS INI,
           TO_DATE(TO_CHAR(P.DATA_TERMINO), 'YYYYMMDD') + NVL(P.HORA_TERMINO, 0) / 1440 AS FIM
      FROM SGTPRD.PARADAS_MAQUINA P
     CROSS JOIN JAN
     WHERE P.DATA_INICIO >= TO_NUMBER(TO_CHAR(JAN.DT_INI, 'YYYYMMDD'))
       AND P.DATA_INICIO <  TO_NUMBER(TO_CHAR(JAN.DT_FIM, 'YYYYMMDD'))
       AND P.DATA_TERMINO >= P.DATA_INICIO
),
PM_SEM_PAR AS (
    SELECT P.*
      FROM PM P
     WHERE NOT EXISTS (
            SELECT 1 FROM BD B
             WHERE B.MAQ = P.MAQ
               AND B.INI < P.FIM
               AND P.INI < B.FIM
               AND (LEAST(B.FIM, P.FIM) - GREATEST(B.INI, P.INI)) * 1440
                   >= 0.5 * LEAST((B.FIM - B.INI), (P.FIM - P.INI)) * 1440)
),
EVENTOS AS (
    SELECT 'EVENTO_NA_BD' AS ORIGEM, B.SETOR, B.INI, (B.FIM - B.INI) * 1440 AS MINUTOS
      FROM BD B
    UNION ALL
    SELECT 'SO_PARADAS_MAQUINA', P.SETOR, P.INI, (P.FIM - P.INI) * 1440
      FROM PM_SEM_PAR P
)
SELECT TO_CHAR(TRUNC(E.INI, 'MM'), 'YYYY-MM')                                   AS COMPETENCIA,
       CASE WHEN TRUNC(E.INI, 'MM') >= JAN.DT_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END AS STATUS_MES,
       E.SETOR,
       E.ORIGEM,
       COUNT(*)                                                                 AS EVENTOS,
       ROUND(SUM(E.MINUTOS), 0)                                                 AS MINUTOS
  FROM EVENTOS E
 CROSS JOIN JAN
 GROUP BY TRUNC(E.INI, 'MM'),
          CASE WHEN TRUNC(E.INI, 'MM') >= JAN.DT_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END,
          E.SETOR,
          E.ORIGEM
 ORDER BY 1, 3, 4
