/* =============================================================================
OBJETIVO: Produção mensal de malha crua na Rama (sem tingimento prévio na própria OB ou em ancestrais)
DOMÍNIO: 02_acabamento_preparacao
TIPO: Painel/KPI
GRÃO: DATA_REFERENCIA
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.OB, SGTPRD.GERAPECAORIGEMOB, SGTPRD.GERAPECADESTINOOB, SGTPRD.GERAPECAORIGEM
CUIDADOS OPERACIONAIS: Consulta homologada com execução em sub-3s. Utiliza arquitetura de duas fases (expansão recursiva de ordens com CYCLE + arestas físicas restritas por Nested Loops) para evitar estouro de PGA/Temp e ORA-00028 no Oracle 12c.
============================================================================= */

WITH
-- -----------------------------------------------------------------------------
-- 1. Candidatas da Rama: Eventos físicos de acabamento cru (Tipo Máquina 6, RM01/RM02)
-- Filtradas por fluxos têxteis válidos de cru no acabamento (204, 302, 304, 305, 409, 412).
-- Não aplicar TIPO_ORDEM <> 6 pois elimina ordens legítimas de preparação de cru.
-- -----------------------------------------------------------------------------
CandidatasRama AS (
    SELECT /*+ MATERIALIZE */ DISTINCT VPF.NUMERO_OB
    FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
    JOIN SGTPRD.OB OBE ON OBE.NUMERO_OB = VPF.NUMERO_OB
    WHERE VPF.TIPO_MAQUINA = 6 
      AND VPF.STATUS = 0 
      AND VPF.TIPO_DESTINO = 0
      AND OBE.CODIGO_FLUXO IN (204, 302, 304, 305, 409, 412)
),

-- -----------------------------------------------------------------------------
-- 2. Cadeia Ancestral de Ordens: Expansão recursiva dinâmica sem limite fixo de gerações.
-- Semântica física comprovada no SGT:
--   GERAPECADESTINOOB: Contém a OB Mãe/Geradora onde a peça foi gerada.
--   GERAPECAORIGEMOB:   Contém a OB Filha/Consumidora onde a peça entrou como insumo.
-- Usa cláusula CYCLE para proteção determinística contra referências circulares.
-- -----------------------------------------------------------------------------
CadeiaAncestralOrdens (NUMERO_OB, NIVEL_GERACAO) AS (
    SELECT NUMERO_OB, 0 AS NIVEL_GERACAO
    FROM CandidatasRama
    UNION ALL
    SELECT 
        GEN.OB_MAE,
        C.NIVEL_GERACAO + 1
    FROM CadeiaAncestralOrdens C
    JOIN (
        -- Continuidade: mesmo identificador de peça IDPECASPRODUTO
        SELECT 
            O.NUMERO_OB  AS OB_FILHO, 
            DO.NUMERO_OB AS OB_MAE
        FROM SGTPRD.GERAPECAORIGEMOB O
        JOIN SGTPRD.GERAPECADESTINOOB DO 
          ON DO.IDPECASPRODUTO = O.IDPECASPRODUTO 
         AND DO.NUMERO_OB <> O.NUMERO_OB
        UNION
        -- Transformação / Desdobro: via GERAPECAORIGEM (IDPECASPRODUTOORIGEM -> IDPECASPRODUTO)
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

-- -----------------------------------------------------------------------------
-- 3. Universo de Ordens: Materializa o conjunto fechado de OBs da linhagem.
-- Isola as buscas subsequentes e impede Hash Joins globais sobre tabelas de milhões de linhas.
-- -----------------------------------------------------------------------------
UniversoOrdens AS (
    SELECT /*+ MATERIALIZE */ DISTINCT NUMERO_OB
    FROM CadeiaAncestralOrdens
    WHERE IS_CYCLE = 0
),

-- -----------------------------------------------------------------------------
-- 4. Arestas Físicas de Peça: Conecta cada peça física entre as ordens do universo.
-- Hints LEADING e USE_NL forçam junção indexada (Nested Loops), impedindo estouro de PGA/Temp.
-- -----------------------------------------------------------------------------
ArestasFisicasPeca AS (
    -- Continuidade: DO = Pai/Origem, O = Filho/Destino
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
    -- Transformação: DO = Pai/Origem, O = Filho/Destino via GERAPECAORIGEM
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

-- -----------------------------------------------------------------------------
-- 5. Genealogia Completa: Travessia hierárquica peça a peça a partir das candidatas.
-- -----------------------------------------------------------------------------
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

-- -----------------------------------------------------------------------------
-- 6. Exclusões Ancestrais:
-- Trava 2: Tingimento em qualquer nível ancestral (definido por fase/processo, não tipo máquina).
-- Trava 3: Rama em qualquer nível ancestral (elimina dupla contagem de material pré-ramado).
-- -----------------------------------------------------------------------------
ExclusoesAncestrais AS (
    -- Trava 2: Tingimento ancestral
    SELECT DISTINCT GC.OB_FINAL AS NUMERO_OB
    FROM GenealogiaCompleta GC
    JOIN SGTPRD.BD_BNF_PRODUCAO_FASE TIN 
      ON TIN.NUMERO_OB = GC.OB_ANCESTRAL AND TIN.STATUS = 0
    WHERE TIN.CODIGO_FASE IN (40, 45, 210) 
       OR TIN.PI_REC IN (401, 451, 2101, 5001, 5002, 5003, 5004, 5005, 5006)
    UNION
    -- Trava 3: Rama ancestral
    SELECT DISTINCT GC.OB_FINAL AS NUMERO_OB
    FROM GenealogiaCompleta GC
    JOIN SGTPRD.BD_BNF_PRODUCAO_FASE RM 
      ON RM.NUMERO_OB = GC.OB_ANCESTRAL AND RM.STATUS = 0 AND RM.TIPO_MAQUINA = 6 AND RM.TIPO_DESTINO = 0
),

-- -----------------------------------------------------------------------------
-- 7. Primeira Passagem Válida na Rama:
-- Ordena eventos cronologicamente por DATA_HORA_FIM (imprescindível pois DATA_FIM é truncada).
-- Aplica Trava 1 (sem tingimento na própria OB antes da Rama) e Travas 2/3 (sem contaminação ancestral).
-- -----------------------------------------------------------------------------
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
      -- Trava 1: Sem tingimento prévio na própria OB antes da Rama
      AND NOT EXISTS (
          SELECT 1 
          FROM SGTPRD.BD_BNF_PRODUCAO_FASE TING
          WHERE TING.NUMERO_OB = VPF.NUMERO_OB 
            AND TING.STATUS = 0
            AND TING.SEQUENCIA < VPF.SEQUENCIA
            AND (TING.CODIGO_FASE IN (40, 45, 210) OR TING.PI_REC IN (401, 451, 2101, 5001, 5002, 5003, 5004, 5005, 5006))
      )
      -- Travas 2 e 3: Sem tingimento e sem Rama em qualquer OB ancestral
      AND NOT EXISTS (
          SELECT 1 FROM ExclusoesAncestrais EA WHERE EA.NUMERO_OB = VPF.NUMERO_OB
      )
),

-- -----------------------------------------------------------------------------
-- 8. Resultado Final: Mantém apenas o 1º evento válido por OB
-- -----------------------------------------------------------------------------
ResultadoFinal AS (
    SELECT 
        NUMERO_OB,
        DATA_FIM,
        KILOS
    FROM PrimeiraPassagemRama
    WHERE RN = 1
),

-- -----------------------------------------------------------------------------
-- 9. Agregação Mensal
-- -----------------------------------------------------------------------------
ResultadoMensal AS (
    SELECT
        LAST_DAY(TRUNC(DATA_FIM, 'MM')) AS DATA_REFERENCIA,
        SUM(KILOS)                      AS QTD_PRODUZIDA
    FROM ResultadoFinal
    GROUP BY TRUNC(DATA_FIM, 'MM')
)

-- -----------------------------------------------------------------------------
-- 10. Projeção Operacional Formatada
-- -----------------------------------------------------------------------------
SELECT
    ROW_NUMBER() OVER (
        ORDER BY QTD_PRODUZIDA DESC, DATA_REFERENCIA DESC
    ) AS RANKING,

    INITCAP(
        TO_CHAR(
            DATA_REFERENCIA,
            'fmMonth',
            'NLS_DATE_LANGUAGE=PORTUGUESE'
        )
    )
    || ' de ' ||
    TO_CHAR(DATA_REFERENCIA, 'YYYY') AS DESCR_ANO_MES,

    QTD_PRODUZIDA,

    EXTRACT(MONTH FROM DATA_REFERENCIA) AS MES,

    EXTRACT(YEAR FROM DATA_REFERENCIA) AS ANO,

    DATA_REFERENCIA

FROM ResultadoMensal
ORDER BY RANKING;
