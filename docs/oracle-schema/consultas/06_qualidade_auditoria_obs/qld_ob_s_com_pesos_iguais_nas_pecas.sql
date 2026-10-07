/* =============================================================================
OBJETIVO: OB_s com pesos iguais nas peças (Auditoria de Balança e Pesagem)
DOMÍNIO: 06_qualidade_auditoria_obs
ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s com pesos iguais nas peças.sql
TIPO: Auditoria e Qualidade de OBs
PARÂMETROS / BINDS: Nenhum (janela: últimos 7 dias de produção)
TABELAS PRINCIPAIS: SGTPRD.GERAPECADESTINOOB, SGTPRD.GERAPECAORIGEM, SGTPRD.GERAPECASPRODUTO
CUIDADOS OPERACIONAIS: Auditoria operacional semanal de chão de fábrica.
OTIMIZAÇÃO: Janela de auditoria recente de 7 dias com hint LEADING no índice de entrada,
  reduzindo de timeout/cancelamento para ~2.8s.
AUDITORIA (29/09/2026): removido o teto FETCH FIRST 100 ROWS ONLY. Em 29/09 a consulta devolve 266 linhas;
  com o teto a auditoria mostrava só 100 (37%) e escondia o resto sem aviso.
============================================================================= */

WITH DELTA_PECAS AS (
    SELECT /*+ MATERIALIZE LEADING(GPP DES LIG GPC) */ DISTINCT
           DES.NUMERO_OB AS NR_OB,
           GPP.IDPECASPRODUTO AS ID_PECA_ACA,
           GPP.QTLIQUIDA AS PESO_LIQUIDO,
           GPP.DATA_DA_ENTRADA_PECA AS DATA_ENTRADA
      FROM SGTPRD.GERAPECASPRODUTO GPP
      JOIN SGTPRD.GERAPECADESTINOOB DES ON DES.IDPECASPRODUTO = GPP.IDPECASPRODUTO
      JOIN SGTPRD.GERAPECAORIGEM LIG ON LIG.IDPECASPRODUTO = GPP.IDPECASPRODUTO
      JOIN SGTPRD.GERAPECASPRODUTO GPC ON GPC.IDPECASPRODUTO = LIG.IDPECASPRODUTOORIGEM
     WHERE GPP.TISITUACAOESTOQUE IS NOT NULL
       AND GPC.QTLIQUIDA <> 0
       AND GPP.DATA_DA_ENTRADA_PECA >= TO_NUMBER(TO_CHAR(SYSDATE - 7, 'YYYYMMDD'))
       AND (100 - (GPP.QTLIQUIDA / NULLIF(GPC.QTLIQUIDA, 0) * 100) >= 20
         OR 100 - (GPP.QTLIQUIDA / NULLIF(GPC.QTLIQUIDA, 0) * 100) <= -20)
)
SELECT DEL.NR_OB AS NUMERO_OB,
       COUNT(DEL.ID_PECA_ACA) AS QTD_PECAS,
       DEL.PESO_LIQUIDO,
       DEL.DATA_ENTRADA
  FROM DELTA_PECAS DEL
 GROUP BY DEL.NR_OB,
          DEL.PESO_LIQUIDO,
          DEL.DATA_ENTRADA
 ORDER BY 2 DESC
