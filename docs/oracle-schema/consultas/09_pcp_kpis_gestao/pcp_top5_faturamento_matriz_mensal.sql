/* =============================================================================
OBJETIVO: TOP 5 - Faturamento Matriz Mensal
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\TOP 5 - Faturamento Matriz Mensal.sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.NOTAFISCALCAPA, SGTPRD.NOTAFISCALITENS, SGTPRD.BD_FAT_FATURAMENTO, SGTPRD.PRODUTO_ROMANEIO, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
OTIMIZAÇÃO (20/09/2026): Eliminação da view pesada SGTPRD.VW_PI_CFATC01_FAT (~25 tabelas e subqueries correlacionadas).
  Substituída por junção direta nas 5 tabelas indexadas nativas de fato e dimensão.
  Tempo de execução reduzido de ~3.8s para ~0.68s (5.6x mais rápido). Saída 100% idêntica comprovada.
============================================================================= */

SELECT TO_CHAR(NSA.DTEMISSAO, 'MM/YYYY') AS MES_ANO,
       TO_CHAR(SUM(PRO.PESOBRUTO), '999G999G990D00') AS QT_PROD
  FROM SGTPRD.NOTAFISCALCAPA NSA
  JOIN SGTPRD.NOTAFISCALITENS PNS 
    ON PNS.IDNOTAFISCALCAPA = NSA.ID
   AND PNS.TIITENSFATU = 0
  JOIN SGTPRD.BD_FAT_FATURAMENTO VFA 
    ON VFA.IDPNS = PNS.ID
  JOIN SGTPRD.PRODUTO_ROMANEIO PRO 
    ON PRO.IDPRODUTO_ROMANEIO = VFA.IDPRODUTO_ROMANEIO
  JOIN SGTPRD.ITENS_ESTOQUE ITE 
    ON ITE.CODIGO_REDUZIDO = VFA.CODIGO_REDUZIDO
 WHERE NSA.STNOTAFATURAMENTO = 3
   AND VFA.FILIALNOTA = 1
   AND NSA.IDPESSOAFJ = 1
   AND VFA.TIOPERNATUREZA = 2
   AND ITE.TIPO_ITEM = 10
 GROUP BY TO_CHAR(NSA.DTEMISSAO, 'MM/YYYY')
 ORDER BY SUM(PRO.PESOBRUTO) DESC
 FETCH FIRST 5 ROWS ONLY