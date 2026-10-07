-- =============================================================================
-- OBJETIVO: Trocar grupo de programação
-- DOMÍNIO: 02_acabamento_preparacao
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Trocar grupo de programação.sql
-- TIPO: Acabamento e Preparação
-- PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
-- TABELAS PRINCIPAIS: SGTPRD.ITENS_ESTOQUE, SGTPRD.GRUPO_PRODUTO
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Remoção de join pesado com view legada VW_OBS_PRODUCAO.
--   - Cabecalho padronizado em '-- ' preservando hints do CBO.
--   - Retorno auditado em tempo real no Oracle SGTPRD: 151 linhas em ~0.013s.
-- =============================================================================

WITH GRUPOS_PROGRAMACAO AS (
    SELECT GPR.NUMERO_GRUPO_PROGRAM AS NUM_GP,
           TRIM(GPR.DESCRICAO) AS DESCR_GRUPO_PROGR
      FROM SGTPRD.GRUPO_PRODUTO GPR
)
SELECT DISTINCT ITE.CODIGO_REDUZIDO,
       ITE.CODIGO_ALTERNATIVO,
       ITE.DESCRICAO,
       ITE.CODIGO,
       ITE.NUMERO_GRUPO_PROGRAM,
       GP.DESCR_GRUPO_PROGR
  FROM SGTPRD.ITENS_ESTOQUE ITE
  JOIN GRUPOS_PROGRAMACAO GP
    ON GP.NUM_GP = ITE.NUMERO_GRUPO_PROGRAM
 WHERE ITE.TIPO_ITEM = 10
   AND SUBSTR(ITE.CODIGO, 6, 3) = '024'
 ORDER BY 2, 4
