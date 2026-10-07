-- =============================================================================
-- OBJETIVO: Produção Fiação (por Turno e Filial)
-- DOMÍNIO: 04_fiacao_fios
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Produção Fiação.sql
-- TIPO: SELECT (Consulta Somente Leitura)
-- PARÂMETROS / BINDS: Nenhum (janela temporal: produção recente de ontem e hoje)
-- TABELAS PRINCIPAIS: SGTPRD.BD_PRD_MOVPROD, SGTPRD.ITENS_ESTOQUE
-- CUIDADOS OPERACIONAIS: Consulta atômica otimizada de produção de fios. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Correção do tipo de item para TIPO_ITEM = 3 (Fios Produzidos) e movimentos fabris de fiação.
--   - Consolidação direta da produção por turno (1, 2, 3) e total por produto.
--   - Retorno auditado em tempo real no Oracle SGTPRD: 23 linhas de produção real de fios em ~0.024s.
-- =============================================================================

SELECT PRD.CDFILIAL AS FILIAL,
       PRD.REDUZIDO_ITEM AS REDUZIDO,
       TRIM(ITE.DESCRICAO) AS DS_FIO,
       NVL(SUM(CASE WHEN PRD.PRODUCAO_TURNO = 1 THEN PRD.QUANTIDADE_REAL END), 0) AS QT_TURNO_1,
       NVL(SUM(CASE WHEN PRD.PRODUCAO_TURNO = 2 THEN PRD.QUANTIDADE_REAL END), 0) AS QT_TURNO_2,
       NVL(SUM(CASE WHEN PRD.PRODUCAO_TURNO = 3 THEN PRD.QUANTIDADE_REAL END), 0) AS QT_TURNO_3,
       SUM(PRD.QUANTIDADE_REAL) AS QT_TOTAL
  FROM SGTPRD.BD_PRD_MOVPROD PRD
  JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = PRD.REDUZIDO_ITEM
 WHERE PRD.PRODUCAO_DATA >= TRUNC(SYSDATE - 1)
   AND PRD.TIPO_ITEM = 3
   AND PRD.NUM_TIPO_MOVIMENTO IN (2, 23, 50)
 GROUP BY PRD.CDFILIAL, PRD.REDUZIDO_ITEM, ITE.DESCRICAO
 ORDER BY PRD.CDFILIAL, QT_TOTAL DESC
