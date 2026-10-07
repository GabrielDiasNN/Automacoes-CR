/* =============================================================================
OBJETIVO: Produção Acabado Mensal (atual)
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\Produção Acabado Mensal (atual).sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.BD_PRD_MOVPROD
CUIDADOS OPERACIONAIS: Consulta agregada mensal por horário de turno industrial (05:00h às 04:59h do dia seguinte).
============================================================================= */

SELECT COUNT(B.IDPECASPRODUTO)                           AS QT_PCS,
       TO_CHAR(SUM(B.QUANTIDADE_REAL), '999G999G990D00') AS ACABADO_MENSAL
  FROM SGTPRD.BD_PRD_MOVPROD B
 WHERE B.CODIGO = 1
   AND B.DATA_DOCUMENTO >= TRUNC(SYSDATE, 'MM') + 5/24
   AND B.DATA_DOCUMENTO < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1) + 5/24;
