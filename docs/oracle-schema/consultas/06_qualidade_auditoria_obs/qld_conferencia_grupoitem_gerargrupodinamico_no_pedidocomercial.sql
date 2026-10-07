/* =============================================================================
OBJETIVO: Conferência - GrupoItem (gerargrupodinamico) no PedidoComercial
DOMÍNIO: 06_qualidade_auditoria_obs
ARQUIVO ORIGINAL: Comandos SQL - CR\Conferência - GrupoItem (gerargrupodinamico) no PedidoComercial.sql
TIPO: Auditoria e Qualidade de OBs
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ITENSPEDIDOCOMERCIAL, SGTPRD.XX2_ENUMERATES, SGTPRD.XX2_ENUMITEM
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

WITH SITUACAO_PEDCOM AS (
    SELECT ENI.SEQUENCE AS STATUS,
           CASE
               WHEN ENI.SEQUENCE IN (10, 12, 13, 14, 18) THEN 0
               WHEN ENI.SEQUENCE IN (6) THEN 2
               ELSE 1
           END AS SIT
      FROM SGTPRD.XX2_ENUMERATES ENU
      JOIN SGTPRD.XX2_ENUMITEM ENI
        ON ENI.IDENUMERATE = ENU.ID
     WHERE ENU.NAME LIKE 'TSITUACAOPEDCOM%'
)
SELECT IPC.PEDIDO, IPC.GRUPOITEM, COUNT(IPC.REDUZIDOITEM) QT_RED_GRUPOITEM
  FROM SGTPRD.ITENSPEDIDOCOMERCIAL IPC
  JOIN SITUACAO_PEDCOM SIT
    ON SIT.STATUS = IPC.SITUACAOITEM
 WHERE SIT.SIT = 1
   AND IPC.GRUPOITEM <> 0
 GROUP BY IPC.PEDIDO, IPC.GRUPOITEM
HAVING COUNT(IPC.REDUZIDOITEM) > 1
 ORDER BY IPC.PEDIDO
