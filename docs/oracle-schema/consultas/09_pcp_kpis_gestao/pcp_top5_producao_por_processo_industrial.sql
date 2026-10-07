/* =============================================================================
OBJETIVO: TOP 5 - Produção por PI
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\TOP 5 - Produção por PI.sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (janela: últimos 12 meses)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
OTIMIZAÇÃO: Substituição de Full Table Scan por Range Scan no índice BDPRODFA_IND_BDPRODFASE_DATA
  restringindo a janela aos últimos 12 meses. Tempo reduzido para ~3.6s.
============================================================================= */

SELECT TO_CHAR(VPF.DATA_FIM, 'MM/YYYY') AS MES_ANO,
       TO_CHAR(SUM(VPF.KILOS), '999G999G990D00') AS QT_PROD
  FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
 WHERE VPF.PI_REC = 1501
   AND VPF.TIPO_DESTINO = 0
   AND VPF.DATA_FIM >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)
 GROUP BY TO_CHAR(VPF.DATA_FIM, 'MM/YYYY')
 ORDER BY SUM(VPF.KILOS) DESC
 FETCH FIRST 5 ROWS ONLY
