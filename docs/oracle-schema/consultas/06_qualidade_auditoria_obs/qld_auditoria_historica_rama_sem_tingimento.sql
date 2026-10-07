/* =============================================================================
OBJETIVO: Validação histórica sintética do KPI de Rama sem tingimento (totais de OBs, kg, datas e meses)
DOMÍNIO: 06_qualidade_auditoria_obs
TIPO: Auditoria/Sentinela
GRÃO: Nenhum (agregado sintético)
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.OB, SGTPRD.GERAPECAORIGEMOB, SGTPRD.GERAPECADESTINOOB, SGTPRD.GERAPECAORIGEM
CUIDADOS OPERACIONAIS: Consulta de homologação e conferência matemática. Baseline histórico verificado: 2.102 OBs, 1.698.172,165979 kg, 89 competências mensais (2018-11-07 a 2026-09-29).
============================================================================= */

WITH
-- 1. Candidatas Rama (fluxos válidos, status 0, tipo destino 0)
CandidatasRama AS (
    SELECT /*+ MATERIALIZE */ DISTINCT VPF.NUMERO_OB
    FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
    JOIN SGTPRD.OB OBE ON OBE.NUMERO_OB = VPF.NUMERO_OB
    WHERE VPF.TIPO_MAQUINA = 6 
      AND VPF.STATUS = 0 
      AND VPF.TIPO_DESTINO = 0
      AND OBE.CODIGO_FLUXO IN (204, 302, 304, 305, 409, 412)
),
-- 2. Cadeia Ancestral de Ordens (expansão recursiva com CYCLE)
CadeiaAncestralOrdens (NUMERO_OB, NIVEL_GERACAO) AS (
    SELECT NUMERO_OB, 0 AS NIVEL_GERACAO
    FROM CandidatasRama
    UNION ALL
    SELECT 
        GEN.OB_MAE,
        C.NIVEL_GERACAO + 1
    FROM CadeiaAncestralOrdens C
    JOIN (
        -- Continuidade:
        SELECT 
            O.NUMERO_OB  AS OB_FILHO, 
            DO.NUMERO_OB AS OB_MAE
        FROM SGTPRD.GERAPECAORIGEMOB O
        JOIN SGTPRD.GERAPECADESTINOOB DO 
          ON DO.IDPECASPRODUTO = O.IDPECASPRODUTO 
         AND DO.NUMERO_OB <> O.NUMERO_OB
        UNION
        -- Transformação:
        SELECT 
            O.NUMERO_OB  AS OB_FILHO, 
            DO.NUMERO_OB AS OB_MAE
        FROM SGTPRD.GERAPECAORIGEMOB O
        JOIN SGTPRD.GERAPECAORIGEM GO ON GO.IDPECASPRODUTO = O.IDPECASPRODUTO
        JOIN SGTPRD.GERAPECADESTINOOB DO 
          ON DO.IDPECASPRODUTO = GO.IDPECASPRODUTOORIGEM 
         AND DO.NUMERO_OB <> O.NUMERO_OB
    ) GEN ON GEN.OB_FILHO = C.NUMERO_OB
)
CYCLE NUMERO_OB SET IS_CYCLE TO 1 DEFAULT 0,
-- 3. Universo compacto de ordens
UniversoOrdens AS (
    SELECT /*+ MATERIALIZE */ DISTINCT NUMERO_OB
    FROM CadeiaAncestralOrdens
    WHERE IS_CYCLE = 0
),
-- 4. Arestas Físicas de Peça com Nested Loops (USE_NL)
ArestasFisicasPeca AS (
    SELECT /*+ MATERIALIZE LEADING(UO O DO) USE_NL(O) USE_NL(DO) */
        DO.NUMERO_OB        AS OB_ORIGEM,
        DO.IDPECASPRODUTO   AS PECA_ORIGEM,
        O.NUMERO_OB         AS OB_DESTINO,
        O.IDPECASPRODUTO    AS PECA_DESTINO,
        'CONTINUIDADE'      AS TIPO_LIGACAO
    FROM UniversoOrdens UO
    JOIN SGTPRD.GERAPECAORIGEMOB O ON O.NUMERO_OB = UO.NUMERO_OB
    JOIN SGTPRD.GERAPECADESTINOOB DO 
      ON DO.IDPECASPRODUTO = O.IDPECASPRODUTO 
     AND DO.NUMERO_OB <> O.NUMERO_OB
    UNION ALL
    SELECT /*+ MATERIALIZE LEADING(UO O GO DO) USE_NL(O) USE_NL(GO) USE_NL(DO) */
        DO.NUMERO_OB        AS OB_ORIGEM,
        DO.IDPECASPRODUTO   AS PECA_ORIGEM,
        O.NUMERO_OB         AS OB_DESTINO,
        GO.IDPECASPRODUTO   AS PECA_DESTINO,
        'TRANSFORMACAO'     AS TIPO_LIGACAO
    FROM UniversoOrdens UO
    JOIN SGTPRD.GERAPECAORIGEMOB O ON O.NUMERO_OB = UO.NUMERO_OB
    JOIN SGTPRD.GERAPECAORIGEM GO ON GO.IDPECASPRODUTO = O.IDPECASPRODUTO
    JOIN SGTPRD.GERAPECADESTINOOB DO ON DO.IDPECASPRODUTO = GO.IDPECASPRODUTOORIGEM 
     AND DO.NUMERO_OB <> O.NUMERO_OB
),
-- 5. Genealogia completa CONNECT BY
GenealogiaCompleta AS (
    SELECT 
        CONNECT_BY_ROOT AF.OB_DESTINO   AS OB_FINAL,
        CONNECT_BY_ROOT AF.PECA_DESTINO AS PECA_FINAL,
        AF.OB_ORIGEM                    AS OB_ANCESTRAL,
        AF.PECA_ORIGEM                  AS PECA_ANCESTRAL,
        LEVEL                           AS NIVEL,
        AF.TIPO_LIGACAO
    FROM ArestasFisicasPeca AF
    START WITH AF.OB_DESTINO IN (SELECT NUMERO_OB FROM CandidatasRama)
    CONNECT BY NOCYCLE PRIOR AF.OB_ORIGEM = AF.OB_DESTINO 
                   AND PRIOR AF.PECA_ORIGEM = AF.PECA_DESTINO
),
-- 6. Exclusões ancestrais por tingimento ou rama
ExclusoesAncestrais AS (
    SELECT DISTINCT GC.OB_FINAL AS NUMERO_OB
    FROM GenealogiaCompleta GC
    JOIN SGTPRD.BD_BNF_PRODUCAO_FASE TIN 
      ON TIN.NUMERO_OB = GC.OB_ANCESTRAL AND TIN.STATUS = 0
    WHERE TIN.CODIGO_FASE IN (40, 45, 210) 
       OR TIN.PI_REC IN (401, 451, 2101, 5001, 5002, 5003, 5004, 5005, 5006)
    UNION
    SELECT DISTINCT GC.OB_FINAL AS NUMERO_OB
    FROM GenealogiaCompleta GC
    JOIN SGTPRD.BD_BNF_PRODUCAO_FASE RM 
      ON RM.NUMERO_OB = GC.OB_ANCESTRAL AND RM.STATUS = 0 AND RM.TIPO_MAQUINA = 6 AND RM.TIPO_DESTINO = 0
),
-- 7. Primeira passagem válida
PrimeiraPassagemRama AS (
    SELECT 
        VPF.NUMERO_OB,
        VPF.DATA_FIM,
        VPF.KILOS,
        ROW_NUMBER() OVER (
            PARTITION BY VPF.NUMERO_OB 
            ORDER BY VPF.DATA_HORA_FIM, VPF.SEQUENCIA, VPF.NUMERO_MAQUINA
        ) AS RN
    FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
    JOIN SGTPRD.OB OBE ON OBE.NUMERO_OB = VPF.NUMERO_OB
    WHERE VPF.TIPO_MAQUINA = 6 
      AND VPF.STATUS = 0 
      AND VPF.TIPO_DESTINO = 0
      AND OBE.CODIGO_FLUXO IN (204, 302, 304, 305, 409, 412)
      AND NOT EXISTS (
          SELECT 1 
          FROM SGTPRD.BD_BNF_PRODUCAO_FASE TING
          WHERE TING.NUMERO_OB = VPF.NUMERO_OB 
            AND TING.STATUS = 0
            AND TING.SEQUENCIA < VPF.SEQUENCIA
            AND (TING.CODIGO_FASE IN (40, 45, 210) OR TING.PI_REC IN (401, 451, 2101, 5001, 5002, 5003, 5004, 5005, 5006))
      )
      AND NOT EXISTS (
          SELECT 1 FROM ExclusoesAncestrais EA WHERE EA.NUMERO_OB = VPF.NUMERO_OB
      )
),
ResultadoFinal AS (
    SELECT 
        NUMERO_OB,
        DATA_FIM,
        KILOS
    FROM PrimeiraPassagemRama
    WHERE RN = 1
)
-- 8. Projeção sintética de auditoria
SELECT 
    COUNT(DISTINCT NUMERO_OB)                            AS TOTAL_OBS,
    SUM(KILOS)                                           AS TOTAL_KG,
    MIN(DATA_FIM)                                        AS MIN_DATA,
    MAX(DATA_FIM)                                        AS MAX_DATA,
    COUNT(DISTINCT TRUNC(DATA_FIM, 'MM'))                AS QTD_MESES,
    MIN(LAST_DAY(TRUNC(DATA_FIM, 'MM')))                 AS MIN_DATA_REFERENCIA,
    MAX(LAST_DAY(TRUNC(DATA_FIM, 'MM')))                 AS MAX_DATA_REFERENCIA
FROM ResultadoFinal;
