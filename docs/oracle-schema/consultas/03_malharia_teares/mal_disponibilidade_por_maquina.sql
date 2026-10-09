/* =============================================================================
OBJETIVO: Proxy de tempo parado por tear interno do setor 4 = 1 - paradas / horas de
          calendário (dias da janela x 24 h), 12 meses. NÃO é uptime nem OEE: parada
          registrada não distingue máquina parada de máquina sem pedido
          (REGRAS_NEGOCIO.md 5.7). Com sensibilidade sem o lote de início de turno.
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: MAQUINA (uma linha por tear interno do setor 4)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
  HORAS_DIA (CTE PARAM) = horas programadas por dia. Padrão 24. Trocar pela jornada
  real de cada grupo quando a engenharia informar (ver CUIDADOS).
TABELAS PRINCIPAIS: SGTPRD.PARADAS_MAQUINA, SGTPRD.MAQUINA, SGTPRD.GRUPO_MAQUINAS,
  SGTPRD.UNIDADE_FABRIL
COLUNAS:
  HORAS_PROGRAMADAS   dias da janela * HORAS_DIA (calendário, não programação da engenharia).
  HORAS_PARADAS       minutos de parada / 60 (todos os motivos com hora informada; ver CUIDADOS).
  DISPONIBILIDADE_PCT (nome histórico; é proxy de tempo parado) (1 - HORAS_PARADAS / HORAS_PROGRAMADAS) * 100.
  HORAS_PARADAS_SEM_INICIO_TURNO  horas paradas excluindo MLC07 (lote de início de turno).
  DISPONIBILIDADE_SEM_INICIO_PCT  mesma conta sem MLC07. Sensibilidade ao lançamento em lote.
  RANK_DISPONIBILIDADE  posição (1 = mais disponível).
CUIDADOS OPERACIONAIS:
  - Jornada confirmada: TABELA_PRD_TURNOS define 3 turnos (05:00, 13:30 e 22:00): T1 e T2 de 8 h 29 min
    e T3 de 6 h 59 min. Jornada de 24 h por dia nas duas filiais, com transições de 1 min arredondadas.
    Ver REGRAS_NEGOCIO.md, seção 5.1.
  - Paradas de mais de um dia com pesagem defasada não mudam a conta (usa só o
    registro de parada).
  - INÍCIO DE TURNO (MLC07) é lançado em lote; por isso a coluna sem MLC07.
  - Parada sem CODIGO_PARADA (NULL) não é MLC07: entra na coluna sem início de turno.
  - Parada sem HORA_INICIO ou HORA_TERMINO (colunas anuláveis) tem MIN_PARADA NULL: o SUM a ignora,
    e ela não entra em HORAS_PARADAS nem em DISPONIBILIDADE_PCT. Medido em 09/10/2026, janela
    01/10/2025 a 30/09/2026, setor 4 e teares internos: 0 de 12.456 paradas sem hora (0 de 87
    teares). Faixa de minutos ignorados: 0 a 0 min. Paradas sem DATA_TERMINO (fora do WHERE): 0.
    Contagem fixa na data da medição; não é atualizada sozinha.
  - Escopo: teares internos 145/146 (EH_FACCAO = 'N') e SETOR = 4, onde as paradas são
    medidas (REGRAS_NEGOCIO.md 5.1 e 5.4). Os 3 teares tipo 146 do setor 7 ficam fora: nenhuma
    parada registrada na janela em nenhum setor (conferido em 09/10/2026), então sairiam com
    100% falso. Decisão de escopo ainda pendente (REGRAS_NEGOCIO.md 5.1 e 5.11).
  - Não usar DISPONIBILIDADE_PCT como uptime nem como fator de OEE (REGRAS_NEGOCIO.md 5.7).
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM,
           TRUNC(SYSDATE, 'MM') - ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)          AS DIAS_JANELA,
           24                                                                    AS HORAS_DIA
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
       AND MQI.SETOR = 4                 -- paradas só no setor 4 (REGRAS 5.1 e 5.4)
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
           SUM(MIN_PARADA) / 60                                                    AS HORAS_PARADAS,
           SUM(CASE WHEN CODIGO_PARADA IS NULL OR CODIGO_PARADA <> 'MLC07'
                    THEN MIN_PARADA ELSE 0 END) / 60 AS HORAS_SEM_INICIO
      FROM PARADAS_DUR
     GROUP BY NUMERO_MAQUINA
)
SELECT LTRIM(M.NUMERO_MAQUINA, '0')                                          AS MAQUINA,
       TRIM(M.GRUPO)                                                         AS GRUPO,
       TRIM(M.MODELO)                                                        AS MODELO,
       ROUND(P.DIAS_JANELA * P.HORAS_DIA, 0)                                 AS HORAS_PROGRAMADAS,
       ROUND(NVL(R.HORAS_PARADAS, 0), 1)                                     AS HORAS_PARADAS,
       ROUND(100 * (1 - NVL(R.HORAS_PARADAS, 0) / NULLIF(P.DIAS_JANELA * P.HORAS_DIA, 0)), 1)
                                                                             AS DISPONIBILIDADE_PCT,
       ROUND(NVL(R.HORAS_SEM_INICIO, 0), 1)                                  AS HORAS_PARADAS_SEM_INICIO_TURNO,
       ROUND(100 * (1 - NVL(R.HORAS_SEM_INICIO, 0) / NULLIF(P.DIAS_JANELA * P.HORAS_DIA, 0)), 1)
                                                                             AS DISPONIBILIDADE_SEM_INICIO_PCT,
       RANK() OVER (ORDER BY NVL(R.HORAS_PARADAS, 0) ASC)                    AS RANK_DISPONIBILIDADE
  FROM SGTPRD.MAQUINA M
  JOIN INTERNAS INTE
    ON INTE.NUMERO_MAQUINA = M.NUMERO_MAQUINA
  CROSS JOIN PARAM P
  LEFT JOIN RESUMO R
    ON R.NUMERO_MAQUINA = M.NUMERO_MAQUINA
 ORDER BY RANK_DISPONIBILIDADE, MAQUINA;
