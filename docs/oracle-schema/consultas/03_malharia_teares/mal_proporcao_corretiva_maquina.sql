/* =============================================================================
OBJETIVO: Proporção de manutenção corretiva por tear interno, com minutos médios por
          parada corretiva e intervalo entre falhas (MTBF proxy), 12 meses
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: MAQUINA (uma linha por tear interno com parada do setor 4 na janela)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
TABELAS PRINCIPAIS: SGTPRD.PARADAS_MAQUINA, SGTPRD.MAQUINA, SGTPRD.GRUPO_MAQUINAS,
  SGTPRD.UNIDADE_FABRIL
COLUNAS:
  EVT_CORRETIVA      paradas MLC04 (manutenção corretiva).
  EVT_PREVENTIVA     paradas MLC02 (manutenção preventiva).
  EVT_ELETRICA       paradas MLC23 (defeito elétrico).
  PCT_CORRETIVA      EVT_CORRETIVA / (EVT_CORRETIVA + EVT_PREVENTIVA) * 100.
  MIN_CORRETIVA      minutos de corretiva (só eventos com duração calculável).
  EVT_CORRETIVA_COM_DUR  eventos de corretiva com duração calculável (HORA_INICIO e HORA_TERMINO
                     preenchidos). É a base de MIN_MEDIO_PARADA_CORRETIVA.
  MIN_MEDIO_PARADA_CORRETIVA  MIN_CORRETIVA / EVT_CORRETIVA_COM_DUR: média de minutos por evento
                     de corretiva com duração (registrada, não tempo de reparo).
  MTBF_DIAS          dias da janela / (EVT_CORRETIVA + EVT_ELETRICA). Proxy de intervalo
                     entre falhas; não é MTBF oficial (não há tempo de operação).
  RANK_MIN_CORRETIVA posição da máquina por minutos de corretiva (1 = mais minutos; máquina sem minutos vai para o fim).
CUIDADOS OPERACIONAIS:
  - Não há ordem de manutenção vinculada às paradas: PARADAS_MAQUINA.NUMEROORDEMMANUTENCA
    está zerado em todas as paradas da malharia, e ORDEMMANUTENCAO.NUMERO_PARADA_MAQUIN não
    está preenchido nas ordens do setor 4. MIN_MEDIO_PARADA_CORRETIVA é duração registrada,
    não tempo de reparo medido (REGRAS_NEGOCIO.md, 5.4 e 5.7).
  - Preventiva e corretiva dependem do operador registrar o código certo.
  - EVT_CORRETIVA e EVT_PREVENTIVA contam o evento mesmo sem duração (PCT_CORRETIVA e MTBF são
    contagem de evento). A média de minutos usa só os eventos com duração calculável, o mesmo
    universo dos minutos. Corrigido em 09/10/2026: antes a média dividia os minutos dos eventos
    com duração pelo total de corretivas, e saía para baixo quando havia corretiva sem HORA.
  - Máquina sem MIN_CORRETIVA (só corretivas sem HORA) fica por último no ranking (NULLS LAST).
    Medido em 09/10/2026, janela 01/10/2025 a 30/09/2026: 0 de 87 máquinas sem MIN_CORRETIVA e
    0 corretivas sem HORA (de 2.074 corretivas).
  - Escopo: teares internos (TIPO_MAQUINA 145/146 em unidade com EH_FACCAO = 'N').
  - Paradas só do setor 4 (REGRAS_NEGOCIO.md, 5.1). Teares internos sem nenhuma parada do
    setor 4 na janela não aparecem: ausência de registro não é zero corretiva. Hoje são os 3
    do setor 7 (tipo 146), com decisão de escopo pendente (REGRAS_NEGOCIO.md, 5.1 e 5.11).
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM,
           TRUNC(SYSDATE, 'MM') - ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)          AS DIAS_JANELA
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
    SELECT PM.NUMERO_MAQUINA,
           PM.CODIGO_PARADA,
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
RESUMO AS (
    SELECT NUMERO_MAQUINA,
           SUM(CASE WHEN CODIGO_PARADA = 'MLC04' THEN 1 ELSE 0 END)           AS EVT_CORRETIVA,
           SUM(CASE WHEN CODIGO_PARADA = 'MLC02' THEN 1 ELSE 0 END)           AS EVT_PREVENTIVA,
           SUM(CASE WHEN CODIGO_PARADA = 'MLC23' THEN 1 ELSE 0 END)           AS EVT_ELETRICA,
           ROUND(SUM(CASE WHEN CODIGO_PARADA = 'MLC04' THEN MIN_PARADA ELSE 0 END), 0) AS MIN_CORRETIVA,
           SUM(CASE WHEN CODIGO_PARADA = 'MLC04' AND MIN_PARADA IS NOT NULL THEN 1 ELSE 0 END) AS EVT_CORRETIVA_COM_DUR
      FROM PARADAS_DUR
     GROUP BY NUMERO_MAQUINA
)
SELECT LTRIM(R.NUMERO_MAQUINA, '0')                                          AS MAQUINA,
       TRIM(M.GRUPO)                                                         AS GRUPO,
       TRIM(M.MODELO)                                                        AS MODELO,
       R.EVT_CORRETIVA,
       R.EVT_PREVENTIVA,
       R.EVT_ELETRICA,
       ROUND(100 * R.EVT_CORRETIVA / NULLIF(R.EVT_CORRETIVA + R.EVT_PREVENTIVA, 0), 1) AS PCT_CORRETIVA,
       R.MIN_CORRETIVA,
       R.EVT_CORRETIVA_COM_DUR,
       ROUND(R.MIN_CORRETIVA / NULLIF(R.EVT_CORRETIVA_COM_DUR, 0), 0)        AS MIN_MEDIO_PARADA_CORRETIVA,
       ROUND(P.DIAS_JANELA / NULLIF(R.EVT_CORRETIVA + R.EVT_ELETRICA, 0), 1) AS MTBF_DIAS,
       RANK() OVER (ORDER BY R.MIN_CORRETIVA DESC NULLS LAST)                AS RANK_MIN_CORRETIVA
  FROM RESUMO R
  CROSS JOIN PARAM P
  JOIN SGTPRD.MAQUINA M
    ON M.NUMERO_MAQUINA = R.NUMERO_MAQUINA
 ORDER BY RANK_MIN_CORRETIVA, MAQUINA;
