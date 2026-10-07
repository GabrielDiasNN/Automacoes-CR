/* =============================================================================
OBJETIVO: TOP 5 - Produção Diária por Operador
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\TOP 5 - Produção Diária por Operador.sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (filtro indexado no ano corrente)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.OPERADOR
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
OTIMIZAÇÃO: Adicionado predicado indexado em DATA_FIM (ano corrente) sobre o índice
  BDPRODFA_IND_BDPRODFASE_DATA, reduzindo o tempo de varredura global para ~3.8s.
============================================================================= */

SELECT TRIM(OPX.NOME) AS NOME_OPERADOR_FIM,
       VPF.DATA_FIM AS DT_PROD,
       TO_CHAR(SUM(VPF.KILOS), '999G999G990D00') AS QT_PROD
  FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
  JOIN SGTPRD.OPERADOR OPX 
    ON OPX.CODIGO = VPF.OPERADOR_FINAL
 WHERE VPF.PI_REC = 201
   AND VPF.DATA_FIM >= TRUNC(SYSDATE, 'YYYY')
 GROUP BY OPX.NOME, VPF.DATA_FIM
 ORDER BY SUM(VPF.KILOS) DESC
 FETCH FIRST 5 ROWS ONLY
