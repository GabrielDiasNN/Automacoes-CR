/* =============================================================================
OBJETIVO: Itens dos pedidos das lojas Costa Rica dos últimos 12 meses, com ano-mês (detalhe por item de pedido)
DOMÍNIO: 07_expedicao_pedidos_comercial
ARQUIVO ORIGINAL: 07_expedicao_pedidos_comercial/com_vendas_das_lojas.sql (Query #2)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.ITENSPEDIDOCOMERCIAL, SGTPRD.ITENS_ESTOQUE, SGTPRD.PEDIDOCOMERCIAL, SGTPRD.PESSOASFJ
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
AUDITORIA (29/09/2026): a consulta filtrava CD_SUBTIPOPED = 11, mas o subtipo 11 foi uma campanha
  única (346 pedidos de 58 lojas, todos até 30/06/2022) e nunca mais foi usado: por isso ela
  ficou vazia. Não existe mais um subtipo "lojas"; as lojas Costa Rica pedem hoje pelo subtipo 1
  (e 12), misturadas com outras filiais. A loja passou a ser identificada pelo nome da filial de
  cobrança (PESSOASFJ.NOMEFANTASIA começa com 'CR-'), sem a matriz ('CR-MATRIZ...') e sem
  'CR-TEX...' (unidade industrial, não loja). Conferido no Oracle: as 58 lojas do subtipo 11
  têm todas o prefixo 'CR-'; nos últimos 12 meses há pedidos todos os meses (de 1 a 20 por mês).
  Valores: QT_FATURADO = IPC.EXPEDIDO (0 enquanto o pedido não expedir) e VL_FATURADO é o valor
  total do item no pedido, não necessariamente já faturado.
============================================================================= */

SELECT TO_CHAR(PED.DATEMISSAO,'YYYYMM')           ANO_MES_FATURAMENTO,
       PES.NOMEFANTASIA                           DS_LOJA,
       PED.PEDIDO                                 NR_PEDIDO,
       IPC.ITEMPEDIDO                             SQ_ITEM_PEDIDO,
       IPC.REDUZIDOITEM                           CD_REDUZIDO,
       ITE.DESCRICAO                              DS_PRODUTO,
       IPC.EXPEDIDO                               QT_FATURADO,
       IPC.PRECOTOTALMOEDA                        VL_FATURADO,
       IPC.PRECOUNITARIO                          PR_MEDIO
FROM   SGTPRD.PEDIDOCOMERCIAL      PED,
       SGTPRD.ITENSPEDIDOCOMERCIAL IPC,
       SGTPRD.PESSOASFJ            PES,
       SGTPRD.ITENS_ESTOQUE        ITE
WHERE  IPC.PEDIDO          = PED.PEDIDO
AND    PES.IDPESSOAFJ      = PED.IDFILIALCOBRANCA
AND    ITE.CODIGO_REDUZIDO = IPC.REDUZIDOITEM
AND    TRIM(PES.NOMEFANTASIA) LIKE 'CR-%'
AND    TRIM(PES.NOMEFANTASIA) NOT LIKE 'CR-MATRIZ%'
AND    TRIM(PES.NOMEFANTASIA) NOT LIKE 'CR-TEX%'
-- Janela: últimos 12 meses incluindo o corrente (antes: janeiro/2022 fixo)
AND    PED.DATEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -11)
AND    PED.DATEMISSAO <  ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1)
ORDER BY 1,2,3,4;
