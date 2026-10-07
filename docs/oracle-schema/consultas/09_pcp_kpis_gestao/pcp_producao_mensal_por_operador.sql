-- =============================================================================
-- OBJETIVO: Produção Mensal por Operador nas Fases do Beneficiamento
-- DOMÍNIO: 09_pcp_kpis_gestao
-- TIPO: PCP e Indicadores Fabris / Ranking Operacional Consolidado
-- PARÂMETROS / BINDS: Mês histórico opcional na CTE PARAMETROS ('YYYY-MM') ou NULL
--                     para execução automática sobre o último mês completamente encerrado.
-- TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.FASES_FLUXO, SGTPRD.OPERADOR
-- CUIDADOS OPERACIONAIS:
--   - Execução estritamente somente leitura.
--   - Exclusão obrigatória da Fase 40 (Tinturaria): apontamentos automáticos da integração
--     ORGATEX que não refletem operadores nominais (2.092 apontamentos com usuário ORGATEX).
--   - Fases fabris elegíveis e Mapeamento de Grupos Operacionais:
--       * Fase 20         -> REVISAO_MALHA_CRUA | Revisão de Malha Crua (Processo contínuo - Carga Média = NULL)
--       * Fases 50 e 55   -> HIDROEXTRATORES    | Hidroextratores       (Lote / Batelada - Fases 50 e 55 somadas)
--       * Fase 60         -> SECADORES          | Secadores             (Lote / Batelada - SC01 Óleo e SC02 Vapor)
--       * Fase 65         -> FELPADEIRA         | Felpadeira            (Lote / Batelada)
--       * Fase 70         -> CALANDRA_BRILHO    | Calandra de Brilho    (Lote / Batelada)
--       * Fase 80         -> CALANDRA_COMPACTA  | Calandra Compacta     (Lote / Batelada)
--       * Fase 90         -> ABRIDOR            | Abridor               (Processo contínuo - Carga Média = NULL)
--       * Fases 100 e 110 -> RAMAS              | Ramas                 (Lote / Batelada - Fases 100 e 110 somadas)
--   - Menor Grão Físico: (NUMEROUP, NUMERO_OB, SEQUENCIA).
--   - Chave Física de Partida: TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA).
--   - Volume Atribuído: Volume apontado/concluído pelo operador (OPERADOR_FINAL) ao encerrar
--     a ordem/partida. Em trocas de turno/operador, o volume é atribuído ao operador finalizador.
--   - Níveis Analíticos / Saídas Suportadas:
--       * A. RANKING_GRUPO       -> (Visão Principal Gerencial) 1 linha por operador por grupo operacional.
--       * B. RANKING_FASE        -> (Visão Técnica Detalhada) 1 linha por operador por código de fase.
--       * C. RANKING_EQUIPAMENTO -> (Visão por Máquina) 1 linha por operador em cada máquina específica.
--       * D. RANKING_GERAL       -> (Ranking Geral por Volume Apontado) Consolida todas as fases elegíveis.
--       * E. OPERADOR_TURNO      -> Detalhamento dimensional por turno trabalhado.
--   - Carga Média: calculada apenas para processos em batelada/lote (PRODUCAO_KG / QTD_PARTIDAS).
--   - Dias Trabalhados: COUNT(DISTINCT TRUNC(DATA_FIM)) preservando datas-calendário.
-- HISTÓRICO:
--   - 02/10/2026: Versão final consolidada com chave física de partida completa (UP|OB|SEQ),
--     agrupamento gerencial de processos (Hidroextratores 50/55 e Ramas 100/110) e reconciliação total.
-- =============================================================================

WITH PARAMETROS AS (
    SELECT /*+ MATERIALIZE */
           -- Informar no formato 'YYYY-MM' para mês histórico (ex: '2026-09')
           -- ou NULL para modo automático (último mês completamente encerrado)
           CAST(NULL AS VARCHAR2(7)) AS MES_HISTORICO
      FROM DUAL
),
PERIODO AS (
    SELECT /*+ MATERIALIZE */
           CASE 
               WHEN P.MES_HISTORICO IS NOT NULL 
               THEN TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD')
               ELSE TRUNC(ADD_MONTHS(SYSDATE, -1), 'MM')
           END AS DT_INICIO,
           CASE 
               WHEN P.MES_HISTORICO IS NOT NULL 
               THEN ADD_MONTHS(TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD'), 1)
               ELSE TRUNC(SYSDATE, 'MM')
           END AS DT_FIM,
           CASE 
               WHEN P.MES_HISTORICO IS NOT NULL 
               THEN P.MES_HISTORICO
               ELSE TO_CHAR(ADD_MONTHS(SYSDATE, -1), 'YYYY-MM')
           END AS MES_REFERENCIA
      FROM PARAMETROS P
),
BASE_APONTAMENTOS AS (
    SELECT /*+ MATERIALIZE */
           PER.MES_REFERENCIA,
           VPF.NUMEROUP,
           VPF.NUMERO_OB,
           VPF.SEQUENCIA,
           VPF.CODIGO_FASE,
           TRIM(FFL.DESCRICAO_FASE) AS FASE,
           -- Mapeamento padronizado de Grupos Operacionais
           CASE 
               WHEN VPF.CODIGO_FASE = 20           THEN 'REVISAO_MALHA_CRUA'
               WHEN VPF.CODIGO_FASE IN (50, 55)    THEN 'HIDROEXTRATORES'
               WHEN VPF.CODIGO_FASE = 60           THEN 'SECADORES'
               WHEN VPF.CODIGO_FASE = 65           THEN 'FELPADEIRA'
               WHEN VPF.CODIGO_FASE = 70           THEN 'CALANDRA_BRILHO'
               WHEN VPF.CODIGO_FASE = 80           THEN 'CALANDRA_COMPACTA'
               WHEN VPF.CODIGO_FASE = 90           THEN 'ABRIDOR'
               WHEN VPF.CODIGO_FASE IN (100, 110)  THEN 'RAMAS'
               ELSE 'OUTROS'
           END AS COD_GRUPO_OPERACIONAL,
           CASE 
               WHEN VPF.CODIGO_FASE = 20           THEN 'Revisão de Malha Crua'
               WHEN VPF.CODIGO_FASE IN (50, 55)    THEN 'Hidroextratores'
               WHEN VPF.CODIGO_FASE = 60           THEN 'Secadores'
               WHEN VPF.CODIGO_FASE = 65           THEN 'Felpadeira'
               WHEN VPF.CODIGO_FASE = 70           THEN 'Calandra de Brilho'
               WHEN VPF.CODIGO_FASE = 80           THEN 'Calandra Compacta'
               WHEN VPF.CODIGO_FASE = 90           THEN 'Abridor'
               WHEN VPF.CODIGO_FASE IN (100, 110)  THEN 'Ramas'
               ELSE 'Outros'
           END AS GRUPO_OPERACIONAL,
           TRIM(LTRIM(VPF.NUMERO_MAQUINA, '0')) AS EQUIPAMENTO,
           LTRIM(TRIM(VPF.OPERADOR_FINAL), '0') AS CODIGO_OPERADOR,
           TRIM(OPX.NOME) AS NOME_OPERADOR,
           VPF.TURNO_FIM AS TURNO,
           VPF.DATA_FIM,
           VPF.KILOS,
           -- Volume acumulado por turno para identificar o turno principal de cada operador no grupo
           SUM(VPF.KILOS) OVER (
               PARTITION BY 
                   CASE 
                       WHEN VPF.CODIGO_FASE = 20           THEN 'REVISAO_MALHA_CRUA'
                       WHEN VPF.CODIGO_FASE IN (50, 55)    THEN 'HIDROEXTRATORES'
                       WHEN VPF.CODIGO_FASE = 60           THEN 'SECADORES'
                       WHEN VPF.CODIGO_FASE = 65           THEN 'FELPADEIRA'
                       WHEN VPF.CODIGO_FASE = 70           THEN 'CALANDRA_BRILHO'
                       WHEN VPF.CODIGO_FASE = 80           THEN 'CALANDRA_COMPACTA'
                       WHEN VPF.CODIGO_FASE = 90           THEN 'ABRIDOR'
                       WHEN VPF.CODIGO_FASE IN (100, 110)  THEN 'RAMAS'
                       ELSE 'OUTROS'
                   END,
                   LTRIM(TRIM(VPF.OPERADOR_FINAL), '0'),
                   VPF.TURNO_FIM
           ) AS KG_TURNO
      FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
     CROSS JOIN PERIODO PER
      LEFT JOIN SGTPRD.FASES_FLUXO FFL
        ON FFL.CODIGO_FASE = VPF.CODIGO_FASE
      LEFT JOIN SGTPRD.OPERADOR OPX
        ON OPX.CODIGO = VPF.OPERADOR_FINAL
     WHERE VPF.DATA_FIM >= PER.DT_INICIO
       AND VPF.DATA_FIM < PER.DT_FIM
       -- Fases produtivas elegíveis do Beneficiamento (com apontamento nominal confiável)
       AND VPF.CODIGO_FASE IN (20, 50, 55, 60, 65, 70, 80, 90, 100, 110)
       -- Exclusão obrigatória da Fase 40 (Tinturaria - integração ORGATEX)
       AND VPF.CODIGO_FASE <> 40
       -- Exclusão preventiva de integradores, usuários de sistema ou apontamentos nulos
       AND UPPER(TRIM(OPX.NOME)) NOT LIKE '%ORGATEX%'
       AND UPPER(TRIM(VPF.OPERADOR_FINAL)) NOT LIKE '%ORGATEX%'
       AND VPF.OPERADOR_FINAL IS NOT NULL
),
-- =============================================================================
-- A. RANKING POR GRUPO OPERACIONAL (Visão Principal Gerencial - 1 linha por operador por grupo)
-- =============================================================================
OPERADOR_GRUPO AS (
    SELECT MES_REFERENCIA,
           COD_GRUPO_OPERACIONAL,
           GRUPO_OPERACIONAL,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           -- Turno onde o operador obteve a maior quantidade de produção no grupo (Turno Principal)
           MAX(TURNO) KEEP (DENSE_RANK LAST ORDER BY KG_TURNO, TURNO) AS TURNO_PRINCIPAL,
           ROUND(SUM(KILOS), 2) AS PRODUCAO_KG,
           COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)) AS QTD_PARTIDAS,
           COUNT(*) AS QTD_APONTAMENTOS,
           COUNT(DISTINCT TRUNC(DATA_FIM)) AS DIAS_COM_PRODUCAO,
           CASE 
               WHEN COD_GRUPO_OPERACIONAL IN ('HIDROEXTRATORES', 'SECADORES', 'FELPADEIRA', 'CALANDRA_BRILHO', 'CALANDRA_COMPACTA', 'RAMAS')
               THEN ROUND(SUM(KILOS) / NULLIF(COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)), 0), 2)
               ELSE NULL
           END AS CARGA_MEDIA
      FROM BASE_APONTAMENTOS
     GROUP BY MES_REFERENCIA,
              COD_GRUPO_OPERACIONAL,
              GRUPO_OPERACIONAL,
              CODIGO_OPERADOR,
              NOME_OPERADOR
),
RANKING_GRUPO AS (
    SELECT MES_REFERENCIA,
           COD_GRUPO_OPERACIONAL,
           GRUPO_OPERACIONAL,
           DENSE_RANK() OVER (
               PARTITION BY MES_REFERENCIA, COD_GRUPO_OPERACIONAL 
               ORDER BY PRODUCAO_KG DESC
           ) AS RANK_GRUPO_OPERACIONAL,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           TURNO_PRINCIPAL,
           PRODUCAO_KG,
           QTD_PARTIDAS,
           QTD_APONTAMENTOS,
           DIAS_COM_PRODUCAO,
           CARGA_MEDIA
      FROM OPERADOR_GRUPO
),
-- =============================================================================
-- B. RANKING DETALHADO POR FASE (1 linha por operador por código de fase)
-- =============================================================================
OPERADOR_FASE AS (
    SELECT MES_REFERENCIA,
           CODIGO_FASE,
           FASE,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           ROUND(SUM(KILOS), 2) AS PRODUCAO_KG,
           COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)) AS QTD_PARTIDAS,
           COUNT(*) AS QTD_APONTAMENTOS,
           COUNT(DISTINCT TRUNC(DATA_FIM)) AS DIAS_COM_PRODUCAO,
           CASE 
               WHEN CODIGO_FASE IN (50, 55, 60, 65, 70, 80, 100, 110)
               THEN ROUND(SUM(KILOS) / NULLIF(COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)), 0), 2)
               ELSE NULL
           END AS CARGA_MEDIA
      FROM BASE_APONTAMENTOS
     GROUP BY MES_REFERENCIA,
              CODIGO_FASE,
              FASE,
              CODIGO_OPERADOR,
              NOME_OPERADOR
),
RANKING_FASE AS (
    SELECT MES_REFERENCIA,
           CODIGO_FASE,
           FASE,
           DENSE_RANK() OVER (
               PARTITION BY MES_REFERENCIA, CODIGO_FASE 
               ORDER BY PRODUCAO_KG DESC
           ) AS RANK_FASE,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           PRODUCAO_KG,
           QTD_PARTIDAS,
           QTD_APONTAMENTOS,
           DIAS_COM_PRODUCAO,
           CARGA_MEDIA
      FROM OPERADOR_FASE
),
-- =============================================================================
-- C. RANKING POR FASE + EQUIPAMENTO (1 linha por operador por máquina específica)
-- =============================================================================
OPERADOR_EQUIPAMENTO AS (
    SELECT MES_REFERENCIA,
           CODIGO_FASE,
           FASE,
           EQUIPAMENTO,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           ROUND(SUM(KILOS), 2) AS PRODUCAO_KG,
           COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)) AS QTD_PARTIDAS,
           COUNT(*) AS QTD_APONTAMENTOS,
           COUNT(DISTINCT TRUNC(DATA_FIM)) AS DIAS_COM_PRODUCAO,
           CASE 
               WHEN CODIGO_FASE IN (50, 55, 60, 65, 70, 80, 100, 110)
               THEN ROUND(SUM(KILOS) / NULLIF(COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)), 0), 2)
               ELSE NULL
           END AS CARGA_MEDIA
      FROM BASE_APONTAMENTOS
     GROUP BY MES_REFERENCIA,
              CODIGO_FASE,
              FASE,
              EQUIPAMENTO,
              CODIGO_OPERADOR,
              NOME_OPERADOR
),
RANKING_EQUIPAMENTO AS (
    SELECT MES_REFERENCIA,
           CODIGO_FASE,
           FASE,
           EQUIPAMENTO,
           DENSE_RANK() OVER (
               PARTITION BY MES_REFERENCIA, CODIGO_FASE, EQUIPAMENTO 
               ORDER BY PRODUCAO_KG DESC
           ) AS RANK_FASE_EQUIPAMENTO,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           PRODUCAO_KG,
           QTD_PARTIDAS,
           QTD_APONTAMENTOS,
           DIAS_COM_PRODUCAO,
           CARGA_MEDIA
      FROM OPERADOR_EQUIPAMENTO
),
-- =============================================================================
-- D. DETALHAMENTO ANALÍTICO POR TURNO
-- =============================================================================
OPERADOR_TURNO AS (
    SELECT MES_REFERENCIA,
           CODIGO_FASE,
           FASE,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           TURNO,
           ROUND(SUM(KILOS), 2) AS PRODUCAO_KG,
           COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)) AS QTD_PARTIDAS,
           COUNT(*) AS QTD_APONTAMENTOS,
           COUNT(DISTINCT TRUNC(DATA_FIM)) AS DIAS_COM_PRODUCAO
      FROM BASE_APONTAMENTOS
     GROUP BY MES_REFERENCIA,
              CODIGO_FASE,
              FASE,
              CODIGO_OPERADOR,
              NOME_OPERADOR,
              TURNO
),
-- =============================================================================
-- E. RANKING GERAL POR VOLUME APONTADO (todas as fases elegíveis consolidadas)
-- =============================================================================
OPERADOR_GERAL AS (
    SELECT MES_REFERENCIA,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           ROUND(SUM(KILOS), 2) AS PRODUCAO_KG,
           COUNT(DISTINCT CODIGO_FASE) AS QTD_FASES_DISTINTAS,
           COUNT(DISTINCT TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)) AS QTD_PARTIDAS,
           COUNT(*) AS QTD_APONTAMENTOS,
           COUNT(DISTINCT TRUNC(DATA_FIM)) AS DIAS_COM_PRODUCAO
      FROM BASE_APONTAMENTOS
     GROUP BY MES_REFERENCIA,
              CODIGO_OPERADOR,
              NOME_OPERADOR
),
RANKING_GERAL AS (
    SELECT MES_REFERENCIA,
           DENSE_RANK() OVER (
               PARTITION BY MES_REFERENCIA 
               ORDER BY PRODUCAO_KG DESC
           ) AS RANK_GERAL_VOLUME,
           CODIGO_OPERADOR,
           NOME_OPERADOR,
           PRODUCAO_KG,
           QTD_FASES_DISTINTAS,
           QTD_PARTIDAS,
           QTD_APONTAMENTOS,
           DIAS_COM_PRODUCAO
      FROM OPERADOR_GERAL
)
-- =============================================================================
-- SAÍDA PRINCIPAL ATIVA: Ranking por Grupo Operacional (Visão Gerencial Preferencial)
-- =============================================================================
SELECT MES_REFERENCIA,
       COD_GRUPO_OPERACIONAL,
       GRUPO_OPERACIONAL,
       RANK_GRUPO_OPERACIONAL,
       CODIGO_OPERADOR,
       NOME_OPERADOR,
       TURNO_PRINCIPAL,
       PRODUCAO_KG,
       QTD_PARTIDAS,
       QTD_APONTAMENTOS,
       DIAS_COM_PRODUCAO,
       CARGA_MEDIA
  FROM RANKING_GRUPO
 ORDER BY COD_GRUPO_OPERACIONAL, RANK_GRUPO_OPERACIONAL, PRODUCAO_KG DESC

-- =============================================================================
-- CONSULTAS ALTERNATIVAS DISPONÍVEIS NA MESMA ESTRUTURA:
--
-- 1. RANKING DETALHADO POR FASE:
--    Substituir o SELECT final por:
--    SELECT MES_REFERENCIA, CODIGO_FASE, FASE, RANK_FASE, CODIGO_OPERADOR,
--           NOME_OPERADOR, PRODUCAO_KG, QTD_PARTIDAS, QTD_APONTAMENTOS,
--           DIAS_COM_PRODUCAO, CARGA_MEDIA
--      FROM RANKING_FASE
--     ORDER BY CODIGO_FASE, RANK_FASE, PRODUCAO_KG DESC;
--
-- 2. RANKING POR FASE + EQUIPAMENTO:
--    Substituir o SELECT final por:
--    SELECT MES_REFERENCIA, CODIGO_FASE, FASE, EQUIPAMENTO, RANK_FASE_EQUIPAMENTO,
--           CODIGO_OPERADOR, NOME_OPERADOR, PRODUCAO_KG, QTD_PARTIDAS,
--           QTD_APONTAMENTOS, DIAS_COM_PRODUCAO, CARGA_MEDIA
--      FROM RANKING_EQUIPAMENTO
--     ORDER BY CODIGO_FASE, EQUIPAMENTO, RANK_FASE_EQUIPAMENTO;
--
-- 3. RANKING GERAL POR VOLUME APONTADO:
--    Substituir o SELECT final por:
--    SELECT MES_REFERENCIA, RANK_GERAL_VOLUME, CODIGO_OPERADOR, NOME_OPERADOR,
--           PRODUCAO_KG, QTD_FASES_DISTINTAS, QTD_PARTIDAS, QTD_APONTAMENTOS,
--           DIAS_COM_PRODUCAO
--      FROM RANKING_GERAL
--     ORDER BY RANK_GERAL_VOLUME;
--
-- 4. DETALHAMENTO ANALÍTICO POR TURNO:
--    Substituir o SELECT final por:
--    SELECT MES_REFERENCIA, CODIGO_FASE, FASE, TURNO, CODIGO_OPERADOR,
--           NOME_OPERADOR, PRODUCAO_KG, QTD_PARTIDAS, QTD_APONTAMENTOS,
--           DIAS_COM_PRODUCAO
--      FROM OPERADOR_TURNO
--     ORDER BY CODIGO_FASE, TURNO, PRODUCAO_KG DESC;
-- =============================================================================
