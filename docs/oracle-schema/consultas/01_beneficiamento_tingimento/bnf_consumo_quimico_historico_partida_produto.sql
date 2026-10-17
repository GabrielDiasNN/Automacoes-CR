/* =============================================================================
OBJETIVO: Historico de consumo de quimicos por partida de tingimento e produto (rastreio/auditoria): consumo real pesado x quantidade emitida na receita, com desvio.
DOMÍNIO: 01_beneficiamento_tingimento
TIPO: Auditoria/Sentinela
GRÃO: 1 linha por PARTIDA x PRODUTO QUIMICO. Partida = NUMEROORDEM + SEQUENCIAFASEOB de MOVTO_RECEITA = NUMEROORDEMMOVIMENTO + SEQUENCIAORDEMMOVIME de OB_FASES.
PARÂMETROS / BINDS: DATA_INI, DATA_FIM e CD_REDUZIDO no CTE PARAMETROS (valores literais de exemplo; ajustar antes de executar).
TABELAS PRINCIPAIS: SGTPRD.MOVTO_RECEITA, SGTPRD.OB_FASES, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Somente leitura. Regras em REGRAS_NEGOCIO.md (secao Quimicos). Consumo real = QUANTIDADEPESADA com MOVCONFIRMADO=1 e STATUSPESAGEMRECEITA=3. Previsto = QUANTIDADE do mesmo lancamento, nao e teorico validado. Desvio so quando previsto > 0.
============================================================================= */
WITH PARAMETROS AS (
    SELECT DATE '2026-01-01' AS DATA_INI,
           DATE '2026-10-18' AS DATA_FIM,
           CAST(NULL AS NUMBER) AS CD_REDUZIDO
      FROM DUAL
),
PARTIDA_KG AS (
    -- Uma linha por partida: peso de tecido e identificacao (OB de referencia, maquina, cor).
    SELECT OBF.NUMEROORDEMMOVIMENTO                 AS NR_PARTIDA,
           OBF.SEQUENCIAORDEMMOVIME                 AS SEQ_PARTIDA,
           SUM(NVL(OBF.KILOS_PRODUZIDOS, 0))        AS KG_TECIDO,
           MIN(OBF.NUMERO_OB)                       AS OB_REFERENCIA,
           MIN(SUBSTR(OBF.NUMERO_MAQUINA, 7, 4))    AS MAQUINA,
           MIN(TRIM(OBF.CODIGO_COR_DESENHO))        AS COR,
           MAX(OBF.TEMPO_FINAL_CONFIRMA)            AS TEMPO_FINAL_CONFIRMA
      FROM SGTPRD.OB_FASES OBF
     WHERE OBF.CODIGO_FASE = 40
       AND OBF.NUMEROORDEMMOVIMENTO IS NOT NULL
     GROUP BY OBF.NUMEROORDEMMOVIMENTO, OBF.SEQUENCIAORDEMMOVIME
),
LANCAMENTO AS (
    -- Uma linha por partida x produto. Confirmados e pesados (consumo real) e a quantidade emitida.
    SELECT R.NUMEROORDEM                             AS NR_PARTIDA,
           R.SEQUENCIAFASEOB                         AS SEQ_PARTIDA,
           R.CODINSREDUZIDO                          AS CD_REDUZIDO,
           SUM(CASE WHEN R.MOVCONFIRMADO = 1 AND R.STATUSPESAGEMRECEITA = 3
                    THEN NVL(R.QUANTIDADEPESADA, 0) ELSE 0 END) AS CONSUMO_REAL_KG,
           SUM(CASE WHEN R.MOVCONFIRMADO = 1 AND R.STATUSPESAGEMRECEITA = 3
                    THEN NVL(R.QUANTIDADE, 0) ELSE 0 END)       AS PREVISTO_RECEITA_KG,
           MAX(R.DT_CONFIRMACAO)                     AS DT_CONFIRMACAO
      FROM SGTPRD.MOVTO_RECEITA R
      CROSS JOIN PARAMETROS P
     WHERE R.DT_CONFIRMACAO >= P.DATA_INI
       AND R.DT_CONFIRMACAO <  P.DATA_FIM
       AND (P.CD_REDUZIDO IS NULL OR R.CODINSREDUZIDO = P.CD_REDUZIDO)
     GROUP BY R.NUMEROORDEM, R.SEQUENCIAFASEOB, R.CODINSREDUZIDO
),
DETALHE AS (
    SELECT L.CD_REDUZIDO,
           L.NR_PARTIDA,
           L.SEQ_PARTIDA,
           PK.OB_REFERENCIA,
           PK.MAQUINA,
           PK.COR,
           TRUNC(L.DT_CONFIRMACAO)                    AS DT_CONSUMO,
           PK.KG_TECIDO,
           L.CONSUMO_REAL_KG,
           L.PREVISTO_RECEITA_KG,
           L.CONSUMO_REAL_KG - L.PREVISTO_RECEITA_KG  AS DESVIO_ABS_KG,
           CASE WHEN L.PREVISTO_RECEITA_KG > 0
                THEN ROUND((L.CONSUMO_REAL_KG - L.PREVISTO_RECEITA_KG) * 100 / L.PREVISTO_RECEITA_KG, 1)
           END                                        AS DESVIO_PCT,
           CASE WHEN L.PREVISTO_RECEITA_KG > 0 THEN 'SIM' ELSE 'NAO' END AS BASE_COMPARAVEL,
           ROUND(L.CONSUMO_REAL_KG * 1000 / NULLIF(PK.KG_TECIDO, 0), 2) AS G_REAL_POR_KG
      FROM LANCAMENTO L
      LEFT JOIN PARTIDA_KG PK ON PK.NR_PARTIDA = L.NR_PARTIDA
                             AND PK.SEQ_PARTIDA = L.SEQ_PARTIDA
)
SELECT D.DT_CONSUMO,
       D.CD_REDUZIDO,
       ITE.DESCRICAO,
       D.OB_REFERENCIA,
       D.NR_PARTIDA,
       D.SEQ_PARTIDA,
       D.MAQUINA,
       D.COR,
       D.KG_TECIDO,
       D.CONSUMO_REAL_KG,
       D.PREVISTO_RECEITA_KG,
       D.DESVIO_ABS_KG,
       D.DESVIO_PCT,
       D.BASE_COMPARAVEL,
       D.G_REAL_POR_KG
  FROM DETALHE D
  LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = D.CD_REDUZIDO
 ORDER BY D.DT_CONSUMO DESC, D.NR_PARTIDA, D.CD_REDUZIDO;
