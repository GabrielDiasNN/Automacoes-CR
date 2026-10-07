/* =============================================================================
OBJETIVO: POSICAO-ATUAL-OBS-EM-ABERTO
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: SQL Reference\POSICAO-ATUAL-OBS-EM-ABERTO.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ENGEITEMESTOARTCRU, SGTPRD.ENGEITEMESTOCOR, SGTPRD.FASES_FLUXO, SGTPRD.GERAPECAORIGEMOB, SGTPRD.GERAPECASPRODUTO, SGTPRD.ITENS_COMPLEMENTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.PEDPRODUCAOOB
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

-- ============================================================
-- POSIÇÃO ATUAL DAS OBs MONTADAS EM ABERTO
-- Schema: SGTPRD
-- A sequência atual e a última confirmação são derivadas diretamente de OB_FASES.
-- ============================================================
-- Retorna todas as OBs abertas (STATUS <> 0) que foram montadas
-- (PEDPRODUCAOOB.OBMONTADA = 1, SETOR = 5), com:
--   DIAS_PARADO  = SYSDATE - última confirmação da OB (via função do pacote)
--   SEQ_ATUAL    = sequência atual na fase (via função do pacote)
--   FASE_ATUAL   = descrição da fase atual (FASES_FLUXO.DESCRICAO_FASE)
--   STATUS_FASE  = status textual da fase (VW_ENU_STATUS_OB_FASES)
--   QT_PECAS     = contagem física de peças montadas
--   QT_KILOS_REAL= peso líquido real (GERAPECASPRODUTO)
-- Ordenação: DIAS_PARADO DESC NULLS LAST (mais críticas primeiro)
-- ============================================================

WITH

    -- 1. OBs MONTADAS ativas + sequência atual + dias parado.
    -- A menor fase ainda ativa representa a posição corrente; a última
    -- confirmação usa o valor serial persistido em TEMPO_FINAL_CONFIRMA.
    OB_ATIVA AS (
        SELECT /*+ MATERIALIZE */
            OB.NUMERO_OB,
            OB.CODIGO_REDUZIDO,
            OB.TIPO_ORDEM,
            COALESCE(
                MIN(CASE WHEN OBF.STATUS IN (1, 2, 3) THEN OBF.SEQUENCIA END),
                MAX(OBF.SEQUENCIA)
            ) AS SEQ_ATUAL,
            SYSDATE - (
                DATE '1996-01-01' + MAX(NULLIF(OBF.TEMPO_FINAL_CONFIRMA, 0)) / 1440
            ) AS DIAS_PARADO
        FROM SGTPRD.OB           OB
        JOIN SGTPRD.PEDPRODUCAOOB PPO ON PPO.NUMEROOB  = OB.NUMERO_OB
                                     AND PPO.SETOR     = 5
                                     AND PPO.OBMONTADA = 1
        LEFT JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OB.NUMERO_OB
        WHERE OB.STATUS <> 0
        GROUP BY OB.NUMERO_OB, OB.CODIGO_REDUZIDO, OB.TIPO_ORDEM
    ),

    -- 2. Dados do produto acabado
    --    GROUP BY: protege contra múltiplas linhas de ENGEITEMESTOCOR por reduzido
    --    (sem ele, cada cor extra no cadastro duplicaria a OB no resultado final)
    ITEM_OB AS (
        SELECT
            OBA.NUMERO_OB,
            OBA.CODIGO_REDUZIDO                AS REDUZ_ACABADO,
            TRIM(MAX(ITE.CODIGO_ALTERNATIVO))  AS ALTERNATIVO,
            TRIM(MAX(ITE.DESCRICAO))           AS DS_ITEM,
            TRIM(MAX(ART.CDARTIGOCRU))         AS CD_ARTIGO,
            MIN(EIC.CDCOR)                     AS CD_COR_ITEM,  -- MIN = 1 valor fixo como fallback
            MAX(ITC.LARGURA)                   AS LARGURA,
            MAX(ITC.GRAMATURA)                 AS GRAMATURA
        FROM OB_ATIVA                  OBA
        JOIN SGTPRD.ITENS_ESTOQUE      ITE ON ITE.CODIGO_REDUZIDO = OBA.CODIGO_REDUZIDO
        JOIN SGTPRD.ENGEITEMESTOARTCRU ART ON ART.CDREDUZIDO      = ITE.CODIGO_REDUZIDO
        JOIN SGTPRD.ENGEITEMESTOCOR    EIC ON EIC.CDREDUZIDO      = ITE.CODIGO_REDUZIDO
        JOIN SGTPRD.ITENS_COMPLEMENTO  ITC ON ITC.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
        GROUP BY OBA.NUMERO_OB, OBA.CODIGO_REDUZIDO
    ),

    -- 3. Placa Kanban + Cor tingimento: único scan em OB_FASES
    --    Antes eram 2 CTEs separadas (PLACA_OB e COR_TINGIMENTO) = 2 passagens
    --    KEEP DENSE_RANK LAST: garante a cor da sequência mais recente da fase 40
    --    NULLS FIRST no ORDER BY: empurra fases != 40 para o fundo do rank,
    --    assegurando que LAST sempre aponte para fase 40 quando existir
    INFO_FASES AS (
        SELECT
            OBF.NUMERO_OB,
            TRIM(MAX(OBF.CODIGO_PLACA))                                   AS PLACA_KANBAN,
            MAX(CASE WHEN OBF.CODIGO_FASE = 40 THEN OBF.CODIGO_COR_DESENHO END)
                KEEP (DENSE_RANK LAST ORDER BY
                      CASE WHEN OBF.CODIGO_FASE = 40 THEN OBF.SEQUENCIA ELSE NULL END
                      NULLS FIRST)                                        AS CD_COR_TINGIMENTO
        FROM SGTPRD.OB_FASES OBF
        JOIN OB_ATIVA         OBA ON OBA.NUMERO_OB = OBF.NUMERO_OB
        GROUP BY OBF.NUMERO_OB
    ),

    -- 4. Peso REAL da malha montada + contagem de peças físicas
    QT_OB AS (
        SELECT
            GPO.NUMERO_OB,
            COUNT(GPP.IDPECASPRODUTO) AS QT_PECAS,
            SUM(GPP.QTLIQUIDA)        AS QT_KILOS_REAL
        FROM SGTPRD.GERAPECAORIGEMOB GPO
        JOIN SGTPRD.GERAPECASPRODUTO  GPP ON GPP.IDPECASPRODUTO = GPO.IDPECASPRODUTO
        JOIN OB_ATIVA                 OBA ON OBA.NUMERO_OB      = GPO.NUMERO_OB
        GROUP BY GPO.NUMERO_OB
    )

SELECT
    OBA.NUMERO_OB,
    NVL(INF.PLACA_KANBAN, 'SEM KANBAN')              AS PLACA_KANBAN,
    -- Dados do produto
    ITM.ALTERNATIVO,
    ITM.CD_ARTIGO,
    NVL(INF.CD_COR_TINGIMENTO, ITM.CD_COR_ITEM)      AS CD_COR,
    ITM.REDUZ_ACABADO,
    ITM.DS_ITEM,
    ITM.LARGURA,
    ITM.GRAMATURA,
    -- Fase e status
    TRIM(FFL.DESCRICAO_FASE)                          AS FASE_ATUAL,
    CASE OBF.STATUS
        WHEN 0 THEN 'PROGRAMADA'
        WHEN 1 THEN 'EMITIDA'
        WHEN 2 THEN 'PESADA'
        WHEN 3 THEN 'EM PROCESSO'
        WHEN 4 THEN 'CONCLUIDO'
        WHEN 5 THEN 'CANCELADA'
        ELSE TO_CHAR(OBF.STATUS)
    END                                               AS STATUS_FASE_ATUAL,
    TRUNC(OBA.DIAS_PARADO, 1)                         AS DIAS_PARADO,
    -- Quantidades reais
    QT.QT_PECAS,
    QT.QT_KILOS_REAL
FROM       OB_ATIVA                    OBA
JOIN SGTPRD.OB_FASES                   OBF ON OBF.NUMERO_OB  = OBA.NUMERO_OB
                                          AND OBF.SEQUENCIA   = OBA.SEQ_ATUAL
JOIN SGTPRD.FASES_FLUXO                FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
LEFT JOIN INFO_FASES                   INF ON INF.NUMERO_OB   = OBA.NUMERO_OB
JOIN ITEM_OB                           ITM ON ITM.NUMERO_OB   = OBA.NUMERO_OB
JOIN QT_OB                             QT  ON QT.NUMERO_OB    = OBA.NUMERO_OB
WHERE (OBA.TIPO_ORDEM = 0 OR OBF.CODIGO_FASE <> 10)
ORDER BY OBA.DIAS_PARADO DESC NULLS LAST;
