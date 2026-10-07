/* =============================================================================
OBJETIVO: Consulta Status Peça
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta Status Peça.sql
TIPO: PCP e Produção
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.XX2_ENUMERATES, SGTPRD.XX2_ENUMITEM
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
OTIMIZAÇÃO (20/09/2026): Eliminação da view SGTPRD.VW_ENU_PECAS_STPECAPRODUTO,
  consultando diretamente as tabelas nativas indexadas de enumerações (XX2_ENUMERATES / XX2_ENUMITEM).
============================================================================= */

SELECT ENI.SEQUENCE AS STPECAPRODUTO,
       ENI.DESCRIPTION AS DESCRICAO
  FROM SGTPRD.XX2_ENUMERATES ENU
  JOIN SGTPRD.XX2_ENUMITEM ENI 
    ON ENI.IDENUMERATE = ENU.ID
 WHERE ENU.NAME LIKE 'TSTATUSPECAPRODUTO%'
 ORDER BY ENI.SEQUENCE