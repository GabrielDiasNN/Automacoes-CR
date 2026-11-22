/* =============================================================================
OBJETIVO: Fila programada por máquina de tingimento (UPs ainda não iniciadas): quantidade de partidas, kg, horas previstas à frente e atrasadas
DOMÍNIO: 01_beneficiamento_tingimento
TIPO: Monitoramento operacional
GRÃO: NUMERO_MAQUINA (uma linha por máquina de tingimento com fila)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.MAQUINA
CUIDADOS OPERACIONAIS: Somente leitura. Complementa bnf_monitoramento_maquinas_tingimento.sql, que
  mostra só o lote em execução agora.
  Universo: UPs de tingimento (SETOR = 5, CODIGOFASE = 40, TIPOUP = 0, EXCLUIDA = 0) sem início
  confirmado (TEMPOINICONFIRMADO = 0), cuja OB está aberta (OB.STATUS <> 0) e cuja fase de
  tingimento ainda não foi confirmada (OB_FASES.STATUS <> 4).
  UNIDADE_PROGRAMACAO.STATUS na fila: 2 = programada com horário (DTTEMPOINIPROGRAMADO válido);
  3 = na fila sem horário definido (a data vem zerada, 1899-12-30, e por isso fica fora de
  PRIMEIRA_PROG/ULTIMA_PROG e de QT_ATRASADAS).
  QT_ATRASADAS = UPs com horário programado já vencido (< SYSDATE) e ainda não iniciadas.
  Duração prevista em minutos, na mesma ordem de preferência de
  bnf_monitoramento_previsao_vs_realizado_tingimento.sql: DURACAO_PREVISTA (em dias) *
  1440; senão TEMPOFINALPROGRAMADO - TEMPOINIPROGRAMADO (dias) * 1440.
  KG_FILA = OB_PRODUTO.KILOS_PROGRAMADOS: carga nominal do lote, não peso real.
  HORAS_FILA é a soma das durações previstas, não o tempo até a fila esvaziar: ignora
  paralelismo, paradas e o lote que está rodando.
============================================================================= */

WITH FILA AS (
    SELECT /*+ MATERIALIZE */
           UPR.NUMERO_MAQUINA,
           UPR.STATUS AS STATUS_UP,
           UOM.NUMEROORDEMREAL AS NUMERO_OB,
           CASE WHEN UPR.STATUS = 2 THEN UPR.DTTEMPOINIPROGRAMADO END AS DT_PROGRAMADA,
           CASE
               WHEN UPR.DURACAO_PREVISTA <> 0 THEN UPR.DURACAO_PREVISTA * 1440
               WHEN UPR.TEMPOFINALPROGRAMADO <> 0
                   THEN (UPR.TEMPOFINALPROGRAMADO - UPR.TEMPOINIPROGRAMADO) * 1440
               ELSE 0
           END AS MIN_PREV
      FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
      JOIN SGTPRD.UP_ORDEM_MVTO UOM ON UOM.NUMEROUP = UPR.NUMEROUP
      JOIN SGTPRD.OB OB ON OB.NUMERO_OB = UOM.NUMEROORDEMREAL
      JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL
                              AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
     WHERE UPR.SETOR = 5
       AND UPR.CODIGOFASE = 40
       AND UPR.TIPOUP = 0
       AND UPR.EXCLUIDA = 0
       AND NVL(UPR.TEMPOINICONFIRMADO, 0) = 0
       AND OB.STATUS <> 0
       AND OBF.STATUS <> 4
)
SELECT LTRIM(FIL.NUMERO_MAQUINA, '0')                        AS MQ,
       TRIM(MAQ.NOME_MAQUINA)                                AS NOME_MAQUINA,
       COUNT(*)                                              AS QT_UPS_FILA,
       SUM(CASE WHEN FIL.STATUS_UP = 2 THEN 1 ELSE 0 END)    AS QT_COM_HORARIO,
       SUM(CASE WHEN FIL.STATUS_UP = 3 THEN 1 ELSE 0 END)    AS QT_SEM_HORARIO,
       SUM(CASE WHEN FIL.DT_PROGRAMADA < SYSDATE THEN 1 ELSE 0 END) AS QT_ATRASADAS,
       ROUND(SUM(NVL(OBP.KILOS_PROGRAMADOS, 0)), 0)          AS KG_FILA,
       ROUND(SUM(FIL.MIN_PREV) / 60, 1)                      AS HORAS_FILA,
       MIN(FIL.DT_PROGRAMADA)                                AS PRIMEIRA_PROG,
       MAX(FIL.DT_PROGRAMADA)                                AS ULTIMA_PROG
  FROM FILA FIL
  JOIN SGTPRD.MAQUINA MAQ ON MAQ.NUMERO_MAQUINA = FIL.NUMERO_MAQUINA
  LEFT JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = FIL.NUMERO_OB
 GROUP BY LTRIM(FIL.NUMERO_MAQUINA, '0'), TRIM(MAQ.NOME_MAQUINA)
 ORDER BY HORAS_FILA DESC
