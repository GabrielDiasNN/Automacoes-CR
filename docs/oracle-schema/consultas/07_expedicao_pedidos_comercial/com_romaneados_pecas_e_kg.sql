/* =============================================================================
OBJETIVO: Romaneados - Peças e (kg)
DOMÍNIO: 07_expedicao_pedidos_comercial
ARQUIVO ORIGINAL: Comandos SQL - CR\Romaneados - Peças e (kg).sql
TIPO: Comercial, Pedidos e Expedição
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ITENSPEDIDOCOMERCIAL, SGTPRD.ITENS_ESTOQUE, SGTPRD.PRODUTO_ROMANEIO, SGTPRD.ROMANEIO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT ROM.STATUS ST,
       SUM(PRO.QUILOS_ORIGINAIS) PESO,
       SUM(PRO.PECAS_ORIGINAIS) PS

  FROM SGTPRD.ROMANEIO             ROM,
       SGTPRD.PRODUTO_ROMANEIO     PRO,
       SGTPRD.ITENSPEDIDOCOMERCIAL ITP,
       SGTPRD.ITENS_ESTOQUE        ITE

 WHERE PRO.NUMERO_ROMANEIO = ROM.NUMERO_ROMANEIO
   AND ITP.PEDIDO = PRO.NUMERO_PEDIDO
   AND ITP.ITEMPEDIDO = PRO.ITEM_PEDIDO
   AND ITE.CODIGO_REDUZIDO = PRO.CODIGO_PRODUTO_REDUZ
      
   AND ROM.IDTIPOROMA IN (1000)
   AND ROM.STATUS IN (3,8)
   AND ITE.CODIGO_REDUZIDO IN
       (SELECT IT.CODIGO_REDUZIDO
          FROM SGTPRD.ITENS_ESTOQUE IT
         WHERE IT.TIPO_ITEM = 10
           AND TRIM(IT.IDMASCARATIPOINSUMO) IN ('BNF', 'BNR')
           AND ITE.LINHAPRODUTOCOMERCIA <> 4)

 GROUP BY ROM.STATUS
 ORDER BY 1
