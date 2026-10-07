/* =============================================================================
OBJETIVO: Consulta Peso Bruto e Líquido
DOMÍNIO: 07_expedicao_pedidos_comercial
ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta Peso Bruto e Líquido.sql
TIPO: Comercial, Pedidos e Expedição
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ITENS_ESTOQUE, SGTPRD.PRODUTO_ROMANEIO, SGTPRD.ROMANEIO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT PR.CODIGO_PRODUTO_REDUZ REDUZIDO,
       TRIM(IE.DESCRICAO) DESCRIO,
       SUM(PR.PESOBRUTO) PESO_BRUTO,
       SUM(PR.QUANTIDADE_KILOS) PESO_LQUIDO,
       SUM(PR.PESOBRUTO) - SUM(PR.QUANTIDADE_KILOS) INSUMOS,
       SUM(PR.NUMERO_PECAS) PEAS
  FROM SGTPRD.PRODUTO_ROMANEIO PR,
       SGTPRD.ITENS_ESTOQUE    IE,
       SGTPRD.ROMANEIO         RO
 WHERE IE.CODIGO_REDUZIDO = PR.CODIGO_PRODUTO_REDUZ
   AND RO.NUMERO_ROMANEIO = PR.NUMERO_ROMANEIO
   AND PR.NUMERO_PEDIDO = 5748 --(Altervel) - escolher o pedido desejado
   --AND RO.STATUS IN (3, 8)     --(Altervel) - escolher status dos romaneios
 GROUP BY PR.CODIGO_PRODUTO_REDUZ, IE.DESCRICAO
 ORDER BY IE.DESCRICAO
