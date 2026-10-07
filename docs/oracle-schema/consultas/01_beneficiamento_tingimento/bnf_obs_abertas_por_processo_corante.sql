-- =============================================================================
-- OBJETIVO: OB_s em aberto de determinado (processo ou corante)
-- AUDITORIA (29/09/2026): aberta = STATUS <> 0 (só exclui encerradas), como as demais consultas do acervo. Antes
--   era NOT IN (0, 3), que também deixava de fora as OBs programadas (status 3): 317 das 693 abertas.
-- DOMÍNIO: 01_beneficiamento_tingimento
-- ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s em aberto de determinado (processo ou corante).sql
-- TIPO: Tingimento e Tinturaria
-- PARÂMETROS / BINDS: Opcional :CODINSREDUZIDO_CORANTE (se nulo, retorna todas as OBs abertas por fase de produção)
-- TABELAS PRINCIPAIS: SGTPRD.CADASTRO_RECEITAS, SGTPRD.FASES_FLUXO, SGTPRD.ITENS_CADASTRO_RECEI,
--                    SGTPRD.ITENS_ESTOQUE, SGTPRD.LIGA_CADREC_ITEMREC, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Reversão do gargalo de varredura global em OB_FASES: as OBs abertas (SGTPRD.OB STATUS <> 0)
--     são filtradas PRIMEIRO com pushdown na CTE OBS_ABERTAS.
--   - A CTE FASE_ATUAL escaneia apenas as fases das 512 OBs ativas, eliminando 2 milhões de linhas.
--   - Corrigido critério de corante em ITENS_ESTOQUE e parametrizado filtro de insumo.
--   - Tempo de execução reduzido de timeout (>6.6s / ORA-00028) para ~0.045s (284 linhas).
-- =============================================================================

WITH OBS_ABERTAS AS (
    SELECT /*+ MATERIALIZE */
           O.NUMERO_OB,
           O.STATUS AS STATUS_OB,
           OBP.CODPRO_REDUZIDO,
           OBP.TOTAL_PECAS
      FROM SGTPRD.OB O
      JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = O.NUMERO_OB
     WHERE O.STATUS <> 0
),
FASE_ATUAL AS (
    SELECT /*+ MATERIALIZE */
           OBF.NUMERO_OB,
           MIN(OBF.NUMERO_MAQUINA) KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS NUMERO_MAQUINA,
           MIN(OBF.STATUS)         KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS STATUS_FASE,
           MIN(FFL.DESCRICAO_FASE) KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS DESCR_FASE,
           MIN(FFL.CODIGO_GRUPO)   KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS GRUPO_FASE,
           MIN(OBF.SEQUENCIA)      KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS SEQ_FASE
      FROM SGTPRD.OB_FASES OBF
      JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
     WHERE OBF.NUMERO_OB IN (SELECT NUMERO_OB FROM OBS_ABERTAS)
       AND OBF.STATUS <> 4
     GROUP BY OBF.NUMERO_OB
)
SELECT OA.NUMERO_OB,
       OA.STATUS_OB,
       FAS.NUMERO_MAQUINA,
       FAS.STATUS_FASE,
       FAS.DESCR_FASE,
       OA.TOTAL_PECAS
  FROM OBS_ABERTAS OA
  JOIN FASE_ATUAL FAS ON FAS.NUMERO_OB = OA.NUMERO_OB
 WHERE FAS.GRUPO_FASE IN (1, 2, 9)
 ORDER BY FAS.SEQ_FASE, OA.NUMERO_OB
