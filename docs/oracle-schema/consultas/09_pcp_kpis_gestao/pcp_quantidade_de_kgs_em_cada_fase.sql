/* =============================================================================
OBJETIVO: Quantidade de KGs em cada fase
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\Quantidade de KGs em cada fase.sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BD_BAS_MASCPRODACAB, SGTPRD.FLUXO, SGTPRD.FLUXOGRUPO, SGTPRD.GERAPECADESTINOOB, SGTPRD.GERAPECAORIGEMOB, SGTPRD.GERAPECASPRODUTO, SGTPRD.ITENSPEDIDOGRADE, SGTPRD.ITENSPEDIDOQTDES, SGTPRD.ITENS_ESTOQUE, SGTPRD.MAQUINA, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.OFORDENS, SGTPRD.OFPEDIDO, SGTPRD.PEDIDOCOMERCIAL, SGTPRD.PEDPRODUCAOOB, SGTPRD.UNIDADE_MEDIDA
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

-- ============================================================
-- AR_M019_POSICAO_PRD_FASE  —  v5 FINAL (100% TABELAS NATIVAS)
-- ============================================================
-- ✅ ZERO views: VW_PI_CBPAP01_PROCBENEF e vw_pi_cenga03_prodaca ELIMINADAS.
--
-- FONTES (todas validadas):
--   FASE atual       = OB_FASES (STATUS<>4, KEEP DENSE_RANK)   ✅
--   MONTADA          = PEDPRODUCAOOB.OBMONTADA                  ✅
--   KG/peças CRU     = GERAPECAORIGEMOB  + GERAPECASPRODUTO     ✅
--   KG/peças ACABADO = GERAPECADESTINOOB + GERAPECASPRODUTO     ✅
--   KG programado    = OB_PRODUTO.KILOS_PROGRAMADOS (só p/ OB não montada)  ✅
--
--   REGRA DE QUILOS (revisada):
--     • CRU     → montada: peso real das peças de origem | não montada: programado
--     • ACABADO → SOMENTE peças reais de destino (sem peça → 0)
--     • NUNCA usar OB_PRODUTO.KILOS_ACABADOS (campo programado falsearia o
--       desempate cru/acabado da agregação)
--   UM               = UNIDADE_MEDIDA.DSSIGLA  (via ITENS_ESTOQUE)     ✅ NOVO
--   ESTAMPADO        = BD_BAS_MASCPRODACAB.ESTAMPADO (via reduzido)    ✅ NOVO
--
-- A vw_pi_cenga03_prodaca trazia UM e ESTAMPADO embrulhados em ~50 subqueries
-- escalares + funções PL/SQL + 15 tabelas. Aqui restam só as 3 de cadastro:
--   ITENS_ESTOQUE → UNIDADE_MEDIDA (UM) + BD_BAS_MASCPRODACAB (ESTAMPADO)
--
-- ESTRATÉGIA DE CUSTO:
--   • OB_BASE materializada filtra o universo UMA vez e restringe tudo a jusante
--   • Agregações de peças restritas a OB_BASE → não varrem GERAPECASPRODUTO inteira
--   • ENG_PRODUTO restrita aos reduzidos de OB_BASE → hash table pequena
--   • Todas as dimensões materializadas e lidas em passada única
-- ============================================================

--CREATE OR REPLACE VIEW sgtprd.AR_M019_POSICAO_PRD_FASE AS

WITH
    -- ----------------------------------------------------------------
    -- 0. UNIVERSO BASE — filtra OB cedo, reduz tudo a jusante
    -- ----------------------------------------------------------------
    OB_BASE AS (
        SELECT /*+ MATERIALIZE */
            OB.NUMERO_OB,
            OB.CODIGO_REDUZIDO,
            OB.CODIGO_FLUXO,
            OB.STATUS,
            OB.TIPO_ORDEM
        FROM sgtprd.OB OB
        WHERE OB.STATUS     <> 0
          AND OB.TIPO_ORDEM IN (0, 6)
    ),

    -- ----------------------------------------------------------------
    -- 1. OBs com FASE 40 (tingimento) no roteiro — classifica FASE 26
    -- ----------------------------------------------------------------
    OB_COM_FASE40 AS (
        SELECT /*+ MATERIALIZE */
            DISTINCT NUMERO_OB
        FROM sgtprd.OB_FASES
        WHERE CODIGO_FASE = 40
    ),

    -- ----------------------------------------------------------------
    -- 2. Grupo do fluxo (ID_GRUPO) para os CASE WHENs
    -- ----------------------------------------------------------------
    GRUPO_FLUXO AS (
        SELECT /*+ MATERIALIZE */
            FLX.CODIGO_FLUXO,
            FLG.ID        AS ID_GRUPO,
            FLG.DESCRICAO AS DS_GRUPO
        FROM sgtprd.FLUXO      FLX
        JOIN sgtprd.FLUXOGRUPO FLG ON FLG.ID = FLX.IDFLUXOGRUPO
    ),

    -- ----------------------------------------------------------------
    -- 3. Fase atual ✅ = primeira fase não-concluída (STATUS <> 4)
    -- ----------------------------------------------------------------
    FASE_ATUAL AS (
        SELECT /*+ MATERIALIZE */
            NUMERO_OB,
            MIN(CODIGO_FASE)    KEEP (DENSE_RANK FIRST ORDER BY SEQUENCIA) AS CODIGO_FASE,
            MIN(STATUS)         KEEP (DENSE_RANK FIRST ORDER BY SEQUENCIA) AS STATUS_FASE,
            MIN(NUMERO_MAQUINA) KEEP (DENSE_RANK FIRST ORDER BY SEQUENCIA) AS NUMERO_MAQUINA
        FROM sgtprd.OB_FASES
        WHERE STATUS <> 4
        GROUP BY NUMERO_OB
    ),

    -- ----------------------------------------------------------------
    -- 4. UM e ESTAMPADO ✅ NATIVO (substitui vw_pi_cenga03_prodaca)
    --    UM        = UNIDADE_MEDIDA.DSSIGLA  (ITENS_ESTOQUE.IDUNIDADEMEDIDA)
    --    ESTAMPADO = BD_BAS_MASCPRODACAB.ESTAMPADO (por CODIGO_REDUZIDO)
    --    Restrito aos reduzidos de OB_BASE → hash table mínima
    -- ----------------------------------------------------------------
    ENG_PRODUTO AS (
        SELECT /*+ MATERIALIZE */
            ITE.CODIGO_REDUZIDO AS REDUZ,
            TRIM(UND.DSSIGLA)   AS UM,
            VMA.ESTAMPADO       AS ESTAMPADO
        FROM sgtprd.ITENS_ESTOQUE       ITE
        JOIN sgtprd.UNIDADE_MEDIDA      UND ON UND.IDUNIDADEMEDIDA = ITE.IDUNIDADEMEDIDA
        JOIN sgtprd.BD_BAS_MASCPRODACAB VMA ON VMA.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
        WHERE ITE.TIPO_ITEM = 10
          AND ITE.CODIGO_REDUZIDO IN (SELECT CODIGO_REDUZIDO FROM OB_BASE)
    ),

    -- ----------------------------------------------------------------
    -- 5. MONTADA ✅ = PEDPRODUCAOOB.OBMONTADA
    -- ----------------------------------------------------------------
    MONTADA_OB AS (
        SELECT /*+ MATERIALIZE */
            P.NUMEROOB       AS NUMERO_OB,
            MAX(P.OBMONTADA) AS OBMONTADA
        FROM sgtprd.PEDPRODUCAOOB P
        WHERE P.SETOR = 5
        GROUP BY P.NUMEROOB
    ),

    -- ----------------------------------------------------------------
    -- 6. Pedido comercial vinculado → detecta 'SEM PROGRAMAÇÃO'
    -- ----------------------------------------------------------------
    PEDIDO_OB AS (
        SELECT /*+ MATERIALIZE */
            P.NUMEROOB        AS NUMERO_OB,
            COUNT(PCO.PEDIDO) AS NRO_PEDIDOS
        FROM sgtprd.PEDPRODUCAOOB    P
        JOIN sgtprd.OFORDENS         OFO ON OFO.NUMEROPEDPRODUCAO  = P.NUMERO
        JOIN sgtprd.OFPEDIDO         OFP ON OFP.NUMEROOF           = OFO.NUMEROOF
        JOIN sgtprd.ITENSPEDIDOQTDES IPX ON IPX.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
        JOIN sgtprd.ITENSPEDIDOGRADE IPG ON IPG.IDITENSPEDIDOGRADE = IPX.IDITEMPEDGRADE
        JOIN sgtprd.PEDIDOCOMERCIAL  PCO ON PCO.PEDIDO             = IPG.PEDIDO
        WHERE P.SETOR = 5
        GROUP BY P.NUMEROOB
    ),

    -- ----------------------------------------------------------------
    -- 7. PESO/PEÇAS CRU REAL ✅ (peças de ORIGEM), restrito a OB_BASE
    -- ----------------------------------------------------------------
    QT_CRU_OB AS (
        SELECT /*+ MATERIALIZE */
            ORI.NUMERO_OB,
            COUNT(GPP.IDPECASPRODUTO) AS QT_PECAS_CRU,
            SUM(GPP.QTLIQUIDA)        AS QT_KILOS_CRU
        FROM sgtprd.GERAPECAORIGEMOB  ORI
        JOIN sgtprd.GERAPECASPRODUTO  GPP ON GPP.IDPECASPRODUTO = ORI.IDPECASPRODUTO
        JOIN OB_BASE                  OBB ON OBB.NUMERO_OB      = ORI.NUMERO_OB
        GROUP BY ORI.NUMERO_OB
    ),

    -- ----------------------------------------------------------------
    -- 8. PESO/PEÇAS ACABADO REAL ✅ (peças de DESTINO), restrito a OB_BASE
    -- ----------------------------------------------------------------
    QT_ACA_OB AS (
        SELECT /*+ MATERIALIZE */
            DES.NUMERO_OB,
            COUNT(GPP.IDPECASPRODUTO) AS QT_PECAS_ACA,
            SUM(GPP.QTLIQUIDA)        AS QT_KILOS_ACA
        FROM sgtprd.GERAPECADESTINOOB DES
        JOIN sgtprd.GERAPECASPRODUTO  GPP ON GPP.IDPECASPRODUTO = DES.IDPECASPRODUTO
        JOIN OB_BASE                  OBB ON OBB.NUMERO_OB      = DES.NUMERO_OB
        GROUP BY DES.NUMERO_OB
    ),

    -- ----------------------------------------------------------------
    -- 9. Classificação da OB na posição atual de produção
    -- ----------------------------------------------------------------
    Classificada AS (
        SELECT
            CASE
                -- ── FALTA MONTAR ─────────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE = 10  AND NVL(MON.OBMONTADA,0) = 0 AND OBE.STATUS = 3       AND FA.STATUS_FASE = 0                                                              THEN '10 - FALTA MONTAR -> (PROGRAMADA)'
                WHEN FA.CODIGO_FASE = 10  AND NVL(MON.OBMONTADA,0) = 0 AND OBE.STATUS IN (1,5)  AND FA.STATUS_FASE = 0                                                              THEN '11 - FALTA MONTAR -> (EMITADA)'
                -- ── SEM PROGRAMAÇÃO ──────────────────────────────────────────────────
                WHEN NVL(POB.NRO_PEDIDOS,0) = 0                                                                                                                                       THEN '12 - SEM PROGRAMAÇÃO'
                -- ── REPROCESSO ───────────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE = 10  AND NVL(MON.OBMONTADA,0) = 1 AND OBE.TIPO_ORDEM = 6  AND FA.STATUS_FASE = 0                                                               THEN '13 - REPROCESSO -> (FALTA AGRUPAR)'
                -- ── MONTADO ─────────────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE = 20  AND OBE.CODIGO_FLUXO <> 204 AND FA.STATUS_FASE = 0                                                                                          THEN '20 - MONTADO -> (REVISAR P/TINGIMENTO)'
                WHEN FA.CODIGO_FASE = 20  AND OBE.CODIGO_FLUXO  = 204                                                                                                                 THEN '21 - MONTADO -> (REVISAR P/ABRIDOR)'
                -- ── REVISADO / TINGIMENTO ────────────────────────────────────────────
                WHEN (FA.CODIGO_FASE = 40 AND FA.STATUS_FASE <> 3) OR (FA.CODIGO_FASE = 26 AND F40.NUMERO_OB IS NOT NULL)                                                             THEN '22 - REVISADO'
                WHEN FA.CODIGO_FASE = 40  AND FA.STATUS_FASE = 3                                                                                                                       THEN '25 - TINGINDO AGORA'
                -- ── HIDRO ────────────────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE IN (45,46,50) AND GF.ID_GRUPO IN (1,3,5,9,12)                                                                                                     THEN '30 - HIDRO UMIDO'
                WHEN FA.CODIGO_FASE IN (45,55)    AND GF.ID_GRUPO IN (1,3,5,9,12)                                                                                                     THEN '31 - HIDRO SECO'
                -- ── SECAGEM / ACABAMENTO ─────────────────────────────────────────────
                WHEN FA.CODIGO_FASE = 60                                                                                                                                               THEN '35 - SECADOR'
                WHEN MAQ.IDTIPOSMAQUINA = 29 AND GF.ID_GRUPO = 5                                                                                                                       THEN '36 - FELPADEIRA (TUBULAR)'
                WHEN MAQ.IDTIPOSMAQUINA = 29 AND GF.ID_GRUPO = 12                                                                                                                      THEN '37 - FELPADEIRA (RAMADO -> FELPADO TUBULAR)'
                WHEN MAQ.IDTIPOSMAQUINA = 29 AND GF.ID_GRUPO = 6                                                                                                                       THEN '38 - FELPADEIRA (RAMADO -> FELPADO ABERTO)'
                WHEN FA.CODIGO_FASE = 70                                                                                                                                               THEN '40 - CALANDRA DE BRILHO'
                WHEN FA.CODIGO_FASE = 165                                                                                                                                              THEN '44 - CONFERÊNCIA DE FELPA'
                WHEN FA.CODIGO_FASE = 80                                                                                                                                               THEN '45 - CALANDRA COMPACTA'
                -- ── ABR/RAS/RAMA ─────────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE IN (45,90,100,110) AND ENG.ESTAMPADO = 0 AND GF.ID_GRUPO = 2                                                                                      THEN '50 - ABR/RAS/RAU'
                WHEN MAQ.IDTIPOSMAQUINA IN (6,23)      AND ENG.ESTAMPADO = 1 AND GF.ID_GRUPO IN (4,7,11) AND NOT (FA.CODIGO_FASE = 100 AND GF.ID_GRUPO IN (4,7))                     THEN '51 - ABR/RAS/RAU -> (ENVIAR P/ ESTAMPARIA)'
                WHEN MAQ.IDTIPOSMAQUINA IN (6,23)      AND ENG.ESTAMPADO = 0 AND GF.ID_GRUPO IN (8,10)                                                                                THEN '52 - ABR/RAS/RAU (DIRETO RAMA)'
                WHEN FA.CODIGO_FASE = 100 AND ENG.ESTAMPADO = 1 AND GF.ID_GRUPO = 4                                                                                                   THEN '53 - RAMAR UMIDO -> (FINALIZAR ESTAMPADO)'
                WHEN FA.CODIGO_FASE = 110 AND ENG.ESTAMPADO = 0 AND GF.ID_GRUPO IN (6,12)                                                                                             THEN '54 - RAMAR SECO -> (FINALIZAR FELPADO)'
                -- ── CQ / EXPEDIÇÃO ───────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE IN (150,160) AND ENG.ESTAMPADO = 0                                                                                                                THEN '60 - CQ/EXP -> (FALTA EMBALAR)'
                WHEN FA.CODIGO_FASE IN (150,160) AND OBE.CODIGO_FLUXO IN (107,109)                                                                                                    THEN '61 - CQ/EXP -> (FALTA ENSACAR MANNRICH)'
                WHEN FA.CODIGO_FASE IN (150,160) AND OBE.CODIGO_FLUXO IN (110,111)                                                                                                    THEN '62 - CQ/EXP -> (FALTA ENSACAR ZIMERMANN)'
                WHEN FA.CODIGO_FASE IN (150,160) AND OBE.CODIGO_FLUXO IN (112,113)                                                                                                    THEN '63 - CQ/EXP -> (FALTA ENSACAR CORES & TONS)'
                -- ── RETORNO FACÇÃO ───────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE = 120 AND FA.STATUS_FASE = 3                                                                                                                       THEN '70 - RETORNAR DA MANNRICH'
                WHEN FA.CODIGO_FASE = 125 AND FA.STATUS_FASE = 3                                                                                                                       THEN '71 - RETORNAR DA ZIMERMANN'
                WHEN FA.CODIGO_FASE = 130 AND FA.STATUS_FASE = 3                                                                                                                       THEN '72 - RETORNAR DA CORES & TONS'
                WHEN FA.CODIGO_FASE = 135 AND FA.STATUS_FASE = 3                                                                                                                       THEN '73 - RETORNAR DA PRIMER COLOR'
                WHEN FA.CODIGO_FASE = 140 AND FA.STATUS_FASE = 3                                                                                                                       THEN '74 - RETORNAR DA ODORIZZI'
                WHEN FA.CODIGO_FASE = 145 AND FA.STATUS_FASE = 3                                                                                                                       THEN '75 - RETORNAR DA SSG (CIRRÊ)'
                -- ── ENVIO FACÇÃO ─────────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE = 25  AND OBE.CODIGO_FLUXO IN (301,303)                                                                                                           THEN '80 - ENVIAR P/ ODORIZZI'
                WHEN FA.CODIGO_FASE = 25  AND OBE.CODIGO_FLUXO IN (302,306)                                                                                                           THEN '81 - ENVIAR P/ CORES & TONS'
                WHEN FA.CODIGO_FASE = 25  AND OBE.CODIGO_FLUXO IN (305,308)                                                                                                           THEN '82 - ENVIAR P/ PRIME COLOR'
                WHEN FA.CODIGO_FASE = 25  AND OBE.CODIGO_FLUXO  = 304                                                                                                                 THEN '83 - ENVIAR P/ 3A DIGITAL'
                WHEN FA.CODIGO_FASE = 120 AND OBE.CODIGO_FLUXO IN (107,109)                                                                                                           THEN '84 - ENVIAR ENSACADO P/ MANNRICH'
                WHEN FA.CODIGO_FASE = 125 AND OBE.CODIGO_FLUXO IN (110,111)                                                                                                           THEN '85 - ENVIAR ENSACADO P/ ZIMERMANN'
                WHEN FA.CODIGO_FASE = 130 AND OBE.CODIGO_FLUXO IN (112,113)                                                                                                           THEN '86 - ENVIAR ENSACADO P/ CORES & TONS'
                -- ── URBANO ───────────────────────────────────────────────────────────
                WHEN FA.CODIGO_FASE = 190 AND OBE.CODIGO_FLUXO  = 207                                                                                                                 THEN '95 - ENTREGAR P/ URBANO'
                ELSE                                                                                                                                                                    '999 - OUTROS'
            END                                                                AS FASES,

            -- ── QUANTIDADE CRU / LINHA ───────────────────────────────────────
            -- Princípio: peso real vem das PEÇAS (QTLIQUIDA), não de campo programado.
            --   montada=1    → peso real das peças de ORIGEM (QT_KILOS_CRU)
            --   montada=0    → ainda não há peça física → KG PROGRAMADO (única exceção
            --                  legítima ao uso de campo de OB_PRODUTO)
            -- Sem fallback para OBP.KILOS: se a OB está montada ela TEM peças reais;
            -- usar campo programado aqui mascararia inconsistência de dados.
            DECODE(NVL(MON.OBMONTADA,0),
                   1, NVL(QC.QT_KILOS_CRU, 0),
                      OBP.KILOS_PROGRAMADOS)                                  AS QUANT_CRU_LINHA,

            -- ── QUANTIDADE ACABADA ───────────────────────────────────────────
            -- SOMENTE peças reais de DESTINO. Sem peça de destino → acabado = 0.
            -- ⚠️ NÃO usar OB_PRODUTO.KILOS_ACABADOS: além de violar o princípio de
            -- peso real, um valor programado residual faria SUM(QUANT_ACA) <> 0 e
            -- dispararia indevidamente o ramo "acabado" do DECODE da agregação,
            -- exibindo estimativa no lugar do cru real em fases intermediárias.
            NVL(QA.QT_KILOS_ACA, 0)                                          AS QUANT_ACA,

            -- ── PEÇAS ────────────────────────────────────────────────────────
            -- Espelha a regra do peso: peças reais de origem (montada) ou de destino.
            -- montada=0 → sem peça física → peças programadas (TOTAL_PECAS_CONFIRM).
            CASE
                WHEN NVL(MON.OBMONTADA,0) = 1
                    THEN COALESCE(QC.QT_PECAS_CRU, QA.QT_PECAS_ACA, 0)
                ELSE NVL(OBP.TOTAL_PECAS_CONFIRM, 0)
            END                                                              AS PECAS_LINHA,

            ENG.UM,
            OBE.NUMERO_OB

        FROM OB_BASE                      OBE

        JOIN FASE_ATUAL                   FA  ON FA.NUMERO_OB        = OBE.NUMERO_OB
        JOIN ENG_PRODUTO                  ENG ON ENG.REDUZ           = OBE.CODIGO_REDUZIDO
        JOIN sgtprd.OB_PRODUTO            OBP ON OBP.NUMERO_OB       = OBE.NUMERO_OB
        JOIN GRUPO_FLUXO                  GF  ON GF.CODIGO_FLUXO     = OBE.CODIGO_FLUXO

        LEFT JOIN sgtprd.MAQUINA          MAQ ON MAQ.NUMERO_MAQUINA  = FA.NUMERO_MAQUINA
                                             AND MAQ.SETOR            = 5
        LEFT JOIN OB_COM_FASE40           F40 ON F40.NUMERO_OB       = OBE.NUMERO_OB
        LEFT JOIN MONTADA_OB              MON ON MON.NUMERO_OB       = OBE.NUMERO_OB
        LEFT JOIN PEDIDO_OB               POB ON POB.NUMERO_OB       = OBE.NUMERO_OB
        LEFT JOIN QT_CRU_OB               QC  ON QC.NUMERO_OB        = OBE.NUMERO_OB
        LEFT JOIN QT_ACA_OB               QA  ON QA.NUMERO_OB        = OBE.NUMERO_OB
    ),

    Agregada AS (
        SELECT
            FASES,
            -- Desempate por fase: se há QUALQUER acabado real na fase, mostra o
            -- acabado; senão, mostra o cru. Como QUANT_ACA agora é 0 quando não há
            -- peça de destino, SUM = 0 só nas fases sem nenhuma produção acabada.
            -- OBS.: em fase com MIX (parte acabada, parte não), prevalece a soma do
            -- acabado real — as OBs ainda não acabadas entram como 0 nesse total.
            DECODE(SUM(QUANT_ACA), 0, SUM(QUANT_CRU_LINHA), SUM(QUANT_ACA)) AS QUANTIDADE_REGRA,
            SUM(QUANT_CRU_LINHA)                                              AS QUANTIDADE_CRU,
            SUM(PECAS_LINHA)                                                  AS QT_PECAS,
            UM,
            COUNT(NUMERO_OB)                                                  AS QT_OB
        FROM Classificada
        GROUP BY FASES, UM
    )

SELECT
    AGR.FASES     AS CD_DS_FASE,
    AGR.QT_PECAS,
    ROUND(
        CASE
            WHEN AGR.FASES = '999 - EM EXECUÇÃO NAS FASES DA PRODUÇÃO' THEN AGR.QUANTIDADE_CRU
            ELSE AGR.QUANTIDADE_REGRA
        END
    , 2)          AS QT_CRU,
    AGR.UM,
    AGR.QT_OB     AS QT_ORDENS
FROM Agregada AGR
WHERE AGR.FASES <> '999 - OUTROS'
ORDER BY AGR.FASES


-- ============================================================
-- NOTAS
-- ============================================================
--
-- NOTA 1 — BD_BAS_MASCPRODACAB cardinalidade (UM/ESTAMPADO)
--   ENG_PRODUTO assume 1 linha por CODIGO_REDUZIDO. Valide:
--     SELECT CODIGO_REDUZIDO, COUNT(*) FROM sgtprd.BD_BAS_MASCPRODACAB
--     GROUP BY CODIGO_REDUZIDO HAVING COUNT(*) > 1;
--   Se houver duplicidade, o JOIN ENG multiplica OBs. Nesse caso troque por:
--     JOIN (SELECT CODIGO_REDUZIDO, MAX(ESTAMPADO) ESTAMPADO
--           FROM sgtprd.BD_BAS_MASCPRODACAB GROUP BY CODIGO_REDUZIDO) VMA ...
--
-- NOTA 2 — OB_PRODUTO cardinalidade (1:1 com OB)
--   Se houver várias linhas por OB, KG programado e fallback de peças duplicam:
--     SELECT NUMERO_OB, COUNT(*) FROM sgtprd.OB_PRODUTO
--     GROUP BY NUMERO_OB HAVING COUNT(*) > 1;
--   Se retornar linhas, agregue OB_PRODUTO numa CTE antes do JOIN.
--
-- NOTA 3 — TIPO_ITEM = 10 em ENG_PRODUTO
--   Mantido conforme a view original (produto acabado). Se algum reduzido de OB
--   não for tipo 10, ele sumiria (INNER JOIN). Confirme que todo reduzido de
--   beneficiamento é TIPO_ITEM = 10; se não, remova o filtro.
--
-- NOTA 4 — Índices que sustentam o baixo custo
--   OB_FASES(NUMERO_OB, SEQUENCIA) | OB_FASES(CODIGO_FASE)
--   GERAPECAORIGEMOB(NUMERO_OB) | GERAPECADESTINOOB(NUMERO_OB)
--   GERAPECASPRODUTO(IDPECASPRODUTO) PK
--   PEDPRODUCAOOB(NUMEROOB, SETOR)
--   ITENS_ESTOQUE(CODIGO_REDUZIDO) PK | BD_BAS_MASCPRODACAB(CODIGO_REDUZIDO)
--   Rode EXPLAIN PLAN e confirme HASH JOIN nas tabelas de peças.
-- ============================================================
