/* =============================================================================
OBJETIVO: Acumulado (Montagem-Tingimento) - Por Dia
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\Acumulado (Montagem-Tingimento) - Por Dia.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.DESTINO, SGTPRD.GRUPO_DESTINO, SGTPRD.GRUPO_MAQUINAS, SGTPRD.ITENS_ESTOQUE, SGTPRD.MAQUINA, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.PROCESSO_INDUSTRIAL, SGTPRD.TABELA_DATAS, SGTPRD.UNIDADE_MEDIDA, SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UNIDADE_PROGR_PROD, SGTPRD.UP_ORDEM_MVTO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
OTIMIZAÇÃO: Vínculo da CTE UP_OB diretamente no escopo de FASES e junções ANSI,
  evitando scan global de fases históricas e reduzindo tempo de ~4.8s para ~1.8s.
============================================================================= */

--------------------------------------------------------------------------------
-- ACUMULADO MONTAGEM x REVISÃO x TINGIMENTO  (POR DIA)  -  100% TABELAS NATIVAS
--
-- Mesma lógica nativa da versão por turno, agregada apenas por DATA.
-- Substitui a cadeia de views:
--   VW_PI_CBPAP02_PRODBENEF -> VW_BNF_OB_FASES_UP + VW_PI_CENGA03_PRODACA
--------------------------------------------------------------------------------
WITH
-- 1. Calendário (uma linha por dia do período) — garante continuidade temporal
DATAS AS (
    SELECT D.DATA, D.DIA_SEM
    FROM   SGTPRD.TABELA_DATAS D
    WHERE  D.DATA BETWEEN TRUNC(ADD_MONTHS(SYSDATE, -1), 'MONTH') AND TRUNC(SYSDATE)
),
-- 2. UP_OB  (substitui VW_BNF_OB_FASES_UP)
--    Data de FIM da UP por (NUMERO_OB, SEQ). Setor 5 = beneficiamento.
--    Filtros canônicos de produção real (ver Produção_por_Fases_Diário.sql):
--      SETOR=5, EXCLUIDA=0, TIPOUP=0, STATUS=0 (UP concluída) + JOIN MAQUINA.
--    Filtro de data aplicado aqui dentro (predicate pushdown nativo).
UP_OB AS (
    SELECT /*+ MATERIALIZE */
           UOM.NUMEROORDEMREAL    AS NUMERO_OB,
           UOM.SEQUENCIAORDEMREAL AS SEQ,
           UPP.DATA_FIM
    FROM   SGTPRD.UNIDADE_PROGR_PROD  UPP,
           SGTPRD.UNIDADE_PROGRAMACAO UPR,
           SGTPRD.UP_ORDEM_MVTO       UOM,
           SGTPRD.MAQUINA             MAQ
    WHERE  UPR.NUMEROUP       = UPP.NUMEROUP
      AND  UPR.SETOR          = 5
      AND  UPR.EXCLUIDA       = 0
      AND  UPR.TIPOUP         = 0
      AND  UPR.STATUS         = 0
      AND  UOM.NUMEROUP       = UPR.NUMEROUP
      AND  MAQ.NUMERO_MAQUINA = UPR.NUMERO_MAQUINA
      AND  UPP.DATA_FIM >= TRUNC(ADD_MONTHS(SYSDATE, -1), 'MONTH')
      AND  UPP.DATA_FIM <  TRUNC(SYSDATE) + 1
),
-- 3. FASES  (substitui o núcleo de VW_PI_CBPAP02_PRODBENEF)
--    Vinculado diretamente a UP_OB para evitar scan global na OB_FASES histórica.
--    Peso real da fase: kilos/metros produzidos; se 0, cai para o do OB_PRODUTO.
--    PRI e GPR atuavam só como FILTRO na view -> trocados por EXISTS (não multiplicam).
--    REPROCESSO = 0  =>  tipo_destino do grupo de destino <> 1.
FASES AS (
    SELECT /*+ MATERIALIZE */
           OBF.NUMERO_OB,
           OBF.SEQUENCIA,
           OBF.CODIGO_FASE,
           OBE.CODIGO_REDUZIDO AS REDUZ,
           DECODE(OBF.KILOS_PRODUZIDOS,  0, OBP.KILOS,  OBF.KILOS_PRODUZIDOS)  AS KILOS,
           DECODE(OBF.METROS_PRODUZIDOS, 0, OBP.METROS, OBF.METROS_PRODUZIDOS) AS METROS,
           UO.DATA_FIM
    FROM   UP_OB UO
    JOIN   SGTPRD.OB_FASES   OBF ON OBF.NUMERO_OB = UO.NUMERO_OB AND OBF.SEQUENCIA = UO.SEQ
    JOIN   SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = OBF.NUMERO_OB
    JOIN   SGTPRD.OB         OBE ON OBE.NUMERO_OB = OBF.NUMERO_OB AND OBE.CODIGO_REDUZIDO = OBP.CODPRO_REDUZIDO
    JOIN   SGTPRD.MAQUINA    MAQ ON MAQ.NUMERO_MAQUINA = OBF.NUMERO_MAQUINA AND MAQ.SETOR = 5
    WHERE  OBF.CODIGO_FASE IN (10, 20, 40)
      AND  EXISTS (SELECT 1
                     FROM SGTPRD.PROCESSO_INDUSTRIAL PRI
                    WHERE PRI.CODIGO_FASE   = OBF.CODIGO_FASE
                      AND PRI.TIPO_PROCESSO = OBF.TIPO_PROCESSO)
      AND  EXISTS (SELECT 1
                     FROM SGTPRD.GRUPO_MAQUINAS GPR
                    WHERE GPR.SETOR = MAQ.SETOR
                      AND GPR.GRUPO = MAQ.GRUPO)
      AND  NVL((SELECT GDX.TIPO_DESTINO
                  FROM SGTPRD.DESTINO       DEX,
                       SGTPRD.GRUPO_DESTINO GDX
                 WHERE DEX.DESTINO      = OBF.DESTINO_RECEITA
                   AND GDX.CODIGO_GRUPO = DEX.CODIGO_GRUPO), 0) <> 1
),
-- 4. UM_RED  (substitui VW_PI_CENGA03_PRODACA -> só a unidade de medida)
--    TPUNIDADEMEDIDA = 1 -> mede em KG ; senão -> metros.
UM_RED AS (
    SELECT ITE.CODIGO_REDUZIDO AS REDUZ,
           UND.TPUNIDADEMEDIDA
    FROM   SGTPRD.ITENS_ESTOQUE ITE,
           SGTPRD.UNIDADE_MEDIDA UND
    WHERE  UND.IDUNIDADEMEDIDA = ITE.IDUNIDADEMEDIDA
      AND  ITE.TIPO_ITEM = 10
),
-- 5. PRODUCAO: pivô por fase, agregado POR DIA (sem turno)
PRODUCAO AS (
    SELECT F.DATA_FIM AS DATA_PROD,
           SUM(CASE WHEN F.CODIGO_FASE = 10 THEN DECODE(U.TPUNIDADEMEDIDA, 1, F.KILOS, F.METROS) END) AS QT_MTG,
           SUM(CASE WHEN F.CODIGO_FASE = 20 THEN DECODE(U.TPUNIDADEMEDIDA, 1, F.KILOS, F.METROS) END) AS QT_REV,
           SUM(CASE WHEN F.CODIGO_FASE = 40 THEN DECODE(U.TPUNIDADEMEDIDA, 1, F.KILOS, F.METROS) END) AS QT_TIN
    FROM   FASES F
    JOIN   UM_RED U ON U.REDUZ = F.REDUZ
    GROUP  BY F.DATA_FIM
)
-- 6. RELATÓRIO FINAL: calendário LEFT JOIN produção + janelas por data
SELECT
    D.DATA,
    D.DIA_SEM,
    ROUND(NVL(P.QT_MTG, 0), 2) AS QT_MTG,
    ROUND(NVL(P.QT_REV, 0), 2) AS QT_REV,
    ROUND(NVL(P.QT_TIN, 0), 2) AS QT_TIN,
    ROUND(NVL(P.QT_MTG, 0) - NVL(P.QT_REV, 0), 2) AS DIF_MTG_REV,
    ROUND(NVL(P.QT_REV, 0) - NVL(P.QT_TIN, 0), 2) AS DIF_REV_TIN,
    ROUND(SUM(NVL(P.QT_MTG, 0) - NVL(P.QT_REV, 0)) OVER (ORDER BY D.DATA), 2) AS ACUM_MTG_REV,
    ROUND(SUM(NVL(P.QT_REV, 0) - NVL(P.QT_TIN, 0)) OVER (ORDER BY D.DATA), 2) AS ACUM_REV_TIN,
    ROUND(SUM(NVL(P.QT_MTG, 0) - NVL(P.QT_TIN, 0)) OVER (ORDER BY D.DATA), 2) AS ACUM_MTG_TIN
FROM   DATAS D
LEFT   JOIN PRODUCAO P
       ON  P.DATA_PROD = D.DATA
ORDER  BY D.DATA