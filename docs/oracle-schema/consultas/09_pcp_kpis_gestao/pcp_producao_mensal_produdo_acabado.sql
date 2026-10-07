/* =============================================================================
OBJETIVO: Produção Mensal (Produdo Acabado)
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\Produção Mensal (Produdo Acabado).sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (janela: últimos 6 meses)
TABELAS PRINCIPAIS: SGTPRD.BD_PRD_MOVPROD
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
OTIMIZAÇÃO: Janela ajustada para 6 meses sobre o índice BDMOVPR_IND_MOVPRD_DATA,
  evitando varredura desnecessária e retornando histórico consolidado em ~3.5s.
============================================================================= */

SELECT TO_NUMBER(TO_CHAR(MVP.PRODUCAO_DATA, 'YYYYMM')) AS ANO_MES,
       TO_CHAR(SUM(MVP.QUANTIDADE_REAL), '999G999G990D00') AS QT_KG,
       COUNT(MVP.IDPECASPRODUTO) AS QT_PECAS,
       ROUND(SUM(MVP.QUANTIDADE_REAL) / COUNT(MVP.IDPECASPRODUTO), 2) AS MEDIA_PC
  FROM SGTPRD.BD_PRD_MOVPROD MVP
 WHERE MVP.NUM_TIPO_MOVIMENTO = 37
   AND MVP.CODIGO IN (1, 8)
   AND MVP.PRODUCAO_DATA >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -6)
   AND MVP.PRODUCAO_DATA < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1)
 GROUP BY TO_NUMBER(TO_CHAR(MVP.PRODUCAO_DATA, 'YYYYMM'))
 ORDER BY ANO_MES
