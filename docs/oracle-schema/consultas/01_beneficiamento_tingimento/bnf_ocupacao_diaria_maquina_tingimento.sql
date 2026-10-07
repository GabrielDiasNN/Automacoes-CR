/* =============================================================================
OBJETIVO: Ocupação diária das máquinas de tingimento nos últimos 30 dias: minutos em produção, limpeza, manutenção, ajuste de planejamento, outras paradas e ocioso
DOMÍNIO: 01_beneficiamento_tingimento
TIPO: Painel/KPI
GRÃO: DIA + MQ (uma linha por dia e máquina de tingimento com UP na janela)
PARÂMETROS / BINDS: Nenhum (janela: hoje e os 30 dias anteriores)
TABELAS PRINCIPAIS: SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.PARADAS_MAQUINA
CUIDADOS OPERACIONAIS: Somente leitura. É um proxy de ocupação, NÃO é OEE (não mede velocidade
  nem qualidade; ver Produção Beneficimento/docs/arquitetura.md).
  MIN_PRODUCAO = tempo das UPs de tingimento (SETOR = 5, CODIGOFASE = 40, TIPOUP = 0,
  EXCLUIDA = 0) com início confirmado (TEMPOINICONFIRMADO > 0), recortado nos limites do
  dia. UP iniciada e ainda sem fim confirmado (em execução) conta até SYSDATE.
  Paradas vêm de PARADAS_MAQUINA (SETOR = 5; DATA_* em YYYYMMDD, HORA_* em minutos do dia),
  classificadas por CODIGO_PARADA (MOTIVOS_PARADAS.DESCRICAO):
    BNF13 = LIMPEZA DE MAQUINA (MIN_LIMPEZA);
    BNF20/BNF21 = MANUT. PREVENTIVA e sua continuação (MIN_MANUTENCAO);
    BNF25 = AJUSTE DE PLANEJAMENTO (MIN_AJUSTE_PLANEJAMENTO): reserva de agenda do PCP, não é
      quebra; é o motivo de maior volume no setor;
    demais códigos, como BNF27 = INSPECIONAR MAQUINA, em MIN_OUTRAS_PARADAS.
  Paradas ainda abertas (DATA_TERMINO = 0) não entram; hoje não há nenhuma aberta.
  MIN_CALENDARIO = 1440, ou os minutos já decorridos no dia corrente. MIN_OCIOSO é o que
  sobra do calendário depois de produção e paradas (mínimo 0); produção e parada podem se
  sobrepor no apontamento, então a soma das colunas pode passar de MIN_CALENDARIO.
  PERC_OCUPACAO_PRODUCAO = MIN_PRODUCAO / MIN_CALENDARIO.
============================================================================= */

WITH PARAMETROS AS (
    SELECT TRUNC(SYSDATE) - 30 AS DT_INI,
           TRUNC(SYSDATE) + 1  AS DT_FIM
      FROM DUAL
),
DIAS AS (
    SELECT PAR.DT_INI + LEVEL - 1 AS DIA
      FROM PARAMETROS PAR
   CONNECT BY LEVEL <= PAR.DT_FIM - PAR.DT_INI
),
UP_TING AS (
    SELECT /*+ MATERIALIZE */
           UPR.NUMERO_MAQUINA,
           UPR.DTTEMPOINICONFIRMADO AS DT_INI_REAL,
           CASE WHEN UPR.TEMPOFINALCONFIRMADO > 0
                THEN UPR.DTTEMPOFINALCONFIRMA
                ELSE SYSDATE
           END AS DT_FIM_REAL
      FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
     CROSS JOIN PARAMETROS PAR
     WHERE UPR.SETOR = 5
       AND UPR.CODIGOFASE = 40
       AND UPR.TIPOUP = 0
       AND UPR.EXCLUIDA = 0
       AND UPR.TEMPOINICONFIRMADO > 0
       AND UPR.DTTEMPOINICONFIRMADO >= PAR.DT_INI - 2
       AND UPR.DTTEMPOINICONFIRMADO <  PAR.DT_FIM
),
MAQS AS (
    SELECT DISTINCT NUMERO_MAQUINA FROM UP_TING
),
PARADA AS (
    SELECT /*+ MATERIALIZE */
           PMA.NUMERO_MAQUINA,
           CASE
               WHEN PMA.CODIGO_PARADA = 'BNF13'                THEN 'LIMPEZA'
               WHEN PMA.CODIGO_PARADA IN ('BNF20', 'BNF21')    THEN 'MANUTENCAO'
               WHEN PMA.CODIGO_PARADA = 'BNF25'                THEN 'AJUSTE_PLANEJAMENTO'
               ELSE                                                 'OUTRAS'
           END AS CATEGORIA,
           TO_DATE(TO_CHAR(PMA.DATA_INICIO), 'YYYYMMDD')  + PMA.HORA_INICIO  / 1440 AS DT_INI_PAR,
           TO_DATE(TO_CHAR(PMA.DATA_TERMINO), 'YYYYMMDD') + PMA.HORA_TERMINO / 1440 AS DT_FIM_PAR
      FROM SGTPRD.PARADAS_MAQUINA PMA
     CROSS JOIN PARAMETROS PAR
     WHERE PMA.SETOR = 5
       AND PMA.DATA_INICIO >= TO_NUMBER(TO_CHAR(PAR.DT_INI - 2, 'YYYYMMDD'))
       AND PMA.DATA_TERMINO > 0
       AND PMA.NUMERO_MAQUINA IN (SELECT NUMERO_MAQUINA FROM MAQS)
),
PROD_DIA AS (
    SELECT DIA.DIA,
           UPT.NUMERO_MAQUINA,
           SUM(GREATEST(0, (LEAST(UPT.DT_FIM_REAL, DIA.DIA + 1)
                            - GREATEST(UPT.DT_INI_REAL, DIA.DIA)) * 1440)) AS MIN_PRODUCAO
      FROM DIAS DIA
      JOIN UP_TING UPT ON UPT.DT_INI_REAL < DIA.DIA + 1
                      AND UPT.DT_FIM_REAL > DIA.DIA
     GROUP BY DIA.DIA, UPT.NUMERO_MAQUINA
),
PARADA_DIA AS (
    SELECT DIA.DIA,
           PAR.NUMERO_MAQUINA,
           SUM(CASE WHEN PAR.CATEGORIA = 'LIMPEZA' THEN
                    GREATEST(0, (LEAST(PAR.DT_FIM_PAR, DIA.DIA + 1)
                                 - GREATEST(PAR.DT_INI_PAR, DIA.DIA)) * 1440) END)  AS MIN_LIMPEZA,
           SUM(CASE WHEN PAR.CATEGORIA = 'MANUTENCAO' THEN
                    GREATEST(0, (LEAST(PAR.DT_FIM_PAR, DIA.DIA + 1)
                                 - GREATEST(PAR.DT_INI_PAR, DIA.DIA)) * 1440) END)  AS MIN_MANUTENCAO,
           SUM(CASE WHEN PAR.CATEGORIA = 'AJUSTE_PLANEJAMENTO' THEN
                    GREATEST(0, (LEAST(PAR.DT_FIM_PAR, DIA.DIA + 1)
                                 - GREATEST(PAR.DT_INI_PAR, DIA.DIA)) * 1440) END)  AS MIN_AJUSTE,
           SUM(CASE WHEN PAR.CATEGORIA = 'OUTRAS' THEN
                    GREATEST(0, (LEAST(PAR.DT_FIM_PAR, DIA.DIA + 1)
                                 - GREATEST(PAR.DT_INI_PAR, DIA.DIA)) * 1440) END)  AS MIN_OUTRAS
      FROM DIAS DIA
      JOIN PARADA PAR ON PAR.DT_INI_PAR < DIA.DIA + 1
                     AND PAR.DT_FIM_PAR > DIA.DIA
     GROUP BY DIA.DIA, PAR.NUMERO_MAQUINA
),
GRADE AS (
    SELECT DIA.DIA,
           MQ.NUMERO_MAQUINA,
           LEAST(1440, (SYSDATE - DIA.DIA) * 1440) AS MIN_CALENDARIO
      FROM DIAS DIA
     CROSS JOIN MAQS MQ
)
SELECT TRUNC(GRD.DIA)                                        AS DIA,
       LTRIM(GRD.NUMERO_MAQUINA, '0')                        AS MQ,
       ROUND(GRD.MIN_CALENDARIO)                             AS MIN_CALENDARIO,
       ROUND(NVL(PRD.MIN_PRODUCAO, 0))                       AS MIN_PRODUCAO,
       ROUND(NVL(PAD.MIN_LIMPEZA, 0))                        AS MIN_LIMPEZA,
       ROUND(NVL(PAD.MIN_MANUTENCAO, 0))                     AS MIN_MANUTENCAO,
       ROUND(NVL(PAD.MIN_AJUSTE, 0))                         AS MIN_AJUSTE_PLANEJAMENTO,
       ROUND(NVL(PAD.MIN_OUTRAS, 0))                         AS MIN_OUTRAS_PARADAS,
       ROUND(GREATEST(0, GRD.MIN_CALENDARIO
                         - NVL(PRD.MIN_PRODUCAO, 0)
                         - NVL(PAD.MIN_LIMPEZA, 0)
                         - NVL(PAD.MIN_MANUTENCAO, 0)
                         - NVL(PAD.MIN_AJUSTE, 0)
                         - NVL(PAD.MIN_OUTRAS, 0)))          AS MIN_OCIOSO,
       ROUND(NVL(PRD.MIN_PRODUCAO, 0) / NULLIF(GRD.MIN_CALENDARIO, 0) * 100, 1) AS PERC_OCUPACAO_PRODUCAO
  FROM GRADE GRD
  LEFT JOIN PROD_DIA PRD ON PRD.DIA = GRD.DIA
                        AND PRD.NUMERO_MAQUINA = GRD.NUMERO_MAQUINA
  LEFT JOIN PARADA_DIA PAD ON PAD.DIA = GRD.DIA
                          AND PAD.NUMERO_MAQUINA = GRD.NUMERO_MAQUINA
 WHERE GRD.MIN_CALENDARIO > 0
 ORDER BY TRUNC(GRD.DIA) DESC, MQ
