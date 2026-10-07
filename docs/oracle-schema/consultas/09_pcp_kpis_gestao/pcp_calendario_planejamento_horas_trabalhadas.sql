/* =============================================================================
OBJETIVO: Calendario Planejamento (horas trabalhadas)
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\Calendario Planejamento (horas trabalhadas).sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (horizonte dinâmico a partir de SYSDATE)
TABELAS PRINCIPAIS: SGTPRD.CALENDARIO_UNIFABRIL
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
REVISÃO / AUDITORIA:
  - Serie temporal continua: feriados e folgas sem linhas no SGT sao preservados (sem gaps).
  - Filtro nativo da coluna FOLGA = '0' e blindagem contra anomalias de hora extra negativa.
  - Resolucao de virada de meia-noite (Turno 3) e ajuste pontual dos minutos 29/59.
  - Acesso direto indexado via PK CALUNIFA_PKCALENDARIOUNIFABRIL.
============================================================================= */

WITH parametros AS (
    SELECT
        '00010' AS CDUNIDADEFABRIL,
        TRUNC(SYSDATE) AS DATA_INICIAL,
        (
            SELECT DATE '1899-12-30' + MAX(clx.DATA)
            FROM sgtprd.calendario_unifabril clx
            WHERE clx.CDUNIDADEFABRIL = '00010'
        ) AS DATA_FINAL,
        DATE '1899-12-30' AS MARCO_ZERO_DELPHI
    FROM DUAL
),

/* Gera o calendario continuo de datas para evitar gaps em feriados e paradas fabris */
calendario_dias AS (
    SELECT
        p.CDUNIDADEFABRIL,
        p.DATA_INICIAL + (LEVEL - 1) AS DATA
    FROM parametros p
    CONNECT BY LEVEL <= (p.DATA_FINAL - p.DATA_INICIAL + 1)
),

base_turnos AS (
    SELECT
        cl.CDUNIDADEFABRIL,
        p.MARCO_ZERO_DELPHI + cl.DATA AS DATA_BASE,
        cl.INICIO AS INICIO_NUM,
        cl.FIM AS FIM_NUM,
        p.MARCO_ZERO_DELPHI + cl.DATA + MOD(cl.INICIO, 1) AS INICIO_REAL,
        p.MARCO_ZERO_DELPHI + cl.DATA + (TRUNC(cl.FIM) - TRUNC(cl.INICIO)) + MOD(cl.FIM, 1) AS FIM_REAL,
        NVL(cl.HORAEXTRA, 0) AS HORAEXTRA
    FROM sgtprd.calendario_unifabril cl
    JOIN parametros p
        ON p.CDUNIDADEFABRIL = cl.CDUNIDADEFABRIL
    WHERE cl.DATA >= (p.DATA_INICIAL - p.MARCO_ZERO_DELPHI - 1)
      AND cl.DATA <= (p.DATA_FINAL - p.MARCO_ZERO_DELPHI)
      AND NVL(cl.FOLGA, '0') = '0'
      AND cl.FIM > cl.INICIO

      /* Remove linhas artificiais que geravam falso 24:00 */
      AND NOT (
            MOD(cl.INICIO, 1) = 0
        AND MOD(cl.FIM, 1) = 0
        AND NVL(cl.HORAEXTRA, 0) < 0
      )
),

/* Particiona turnos que viram a meia-noite em duas fracoes por data civil */
intervalos_diarios AS (
    SELECT
        CDUNIDADEFABRIL,
        TRUNC(INICIO_REAL) AS DATA,
        INICIO_REAL AS INICIO,
        LEAST(FIM_REAL, TRUNC(INICIO_REAL) + 1) AS FIM
    FROM base_turnos

    UNION ALL

    SELECT
        CDUNIDADEFABRIL,
        TRUNC(FIM_REAL) AS DATA,
        TRUNC(FIM_REAL) AS INICIO,
        FIM_REAL AS FIM
    FROM base_turnos
    WHERE TRUNC(FIM_REAL) > TRUNC(INICIO_REAL)
),

resumo_minutos AS (
    SELECT
        CDUNIDADEFABRIL,
        DATA,
        LEAST(
            SUM(
                ROUND((FIM - INICIO) * 1440, 0)
                +
                CASE
                    WHEN TO_CHAR(FIM, 'MI') IN ('29', '59')
                    THEN 1
                    ELSE 0
                END
            ),
            1440
        ) AS MINUTOS_TRABALHADOS
    FROM intervalos_diarios
    WHERE FIM > INICIO
      AND DATA >= TRUNC(SYSDATE)
    GROUP BY
        CDUNIDADEFABRIL,
        DATA
),

resultado AS (
    SELECT
        c.CDUNIDADEFABRIL,
        c.DATA,
        NVL(r.MINUTOS_TRABALHADOS, 0) AS MINUTOS_TRABALHADOS
    FROM calendario_dias c
    LEFT JOIN resumo_minutos r
        ON r.CDUNIDADEFABRIL = c.CDUNIDADEFABRIL
       AND r.DATA = c.DATA
)

SELECT
    CDUNIDADEFABRIL,

    DATA,

    MINUTOS_TRABALHADOS,

    TRUNC(MINUTOS_TRABALHADOS / 60) AS HORAS,

    MOD(MINUTOS_TRABALHADOS, 60) AS MINUTOS,

    LPAD(TRUNC(MINUTOS_TRABALHADOS / 60), 2, '0')
        || ':' ||
    LPAD(MOD(MINUTOS_TRABALHADOS, 60), 2, '0') AS TEMPO_TRABALHADO,

    CASE
        WHEN MINUTOS_TRABALHADOS > 0
        THEN 'SIM'
        ELSE 'NAO'
    END AS TRABALHA_NO_DIA

FROM resultado
WHERE DATA >= TRUNC(SYSDATE)
ORDER BY
    DATA
