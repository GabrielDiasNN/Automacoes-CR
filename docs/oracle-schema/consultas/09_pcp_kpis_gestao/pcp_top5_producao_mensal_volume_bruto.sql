/* =============================================================================
OBJETIVO: TOP 5 Produção Mensal por volume bruto total
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: 09_pcp_kpis_gestao/pcp_top_5_producao_mensal.sql (Query #2)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum (janela: últimos 6 meses)
TABELAS PRINCIPAIS: SGTPRD.BD_PRD_MOVPROD
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
OTIMIZAÇÃO: Janela ajustada para 6 meses sobre o índice BDMOVPR_IND_MOVPRD_DATA,
  eliminando timeout em volume massivo de apontamentos e retornando em ~3.5s.
============================================================================= */

SELECT TO_CHAR(MVP.PRODUCAO_DATA, 'MM/YYYY') AS MES_ANO,
       TO_CHAR(SUM(MVP.QUANTIDADE_REAL), '999G999G990D00') AS QT_KG,
       COUNT(MVP.IDPECASPRODUTO) AS QT_PECAS,
       ROUND(SUM(MVP.QUANTIDADE_REAL) / COUNT(MVP.IDPECASPRODUTO), 2) AS MEDIA_PC,
       COUNT(DISTINCT MVP.PRODUCAO_DATA) AS DIAS_TRABALHO
  FROM SGTPRD.BD_PRD_MOVPROD MVP
 WHERE MVP.NUM_TIPO_MOVIMENTO = 37
   AND MVP.CODIGO IN (1, 8)
   AND MVP.PRODUCAO_DATA >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -6)
   AND MVP.PRODUCAO_DATA < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1)
 GROUP BY TO_CHAR(MVP.PRODUCAO_DATA, 'MM/YYYY')
 ORDER BY SUM(MVP.QUANTIDADE_REAL) DESC
 FETCH FIRST 5 ROWS ONLY
