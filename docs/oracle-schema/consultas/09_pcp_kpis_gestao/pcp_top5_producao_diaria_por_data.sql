/* =============================================================================
OBJETIVO: TOP 5 - Produção Diária por Data
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\TOP 5 - Produção Diária por Data.sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT VPF.DATA_FIM AS DT_PROD,
       SUM(VPF.KILOS) AS QT_PROD
  FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
 WHERE VPF.PI_REC IN (302, 401)
   AND VPF.TIPO_DESTINO = 0
 GROUP BY VPF.DATA_FIM
 ORDER BY SUM(VPF.KILOS) DESC
 FETCH FIRST 5 ROWS ONLY

