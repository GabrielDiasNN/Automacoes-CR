-- =============================================================================
-- OFST-06 — OBs com fluxo 204 (direto para rama, sem tingimento)
-- Retorna as OBs candidatas a montagem: emitidas e ainda nao montadas.
--
-- Contrato de colunas (validado por validators.validate_ob_query):
--   NUMERO_OB, CODIGO_FLUXO, CODIGO_REDUZIDO_CRU, STATUS, TOTAL_PECAS,
--   KILOS_PROGRAMADOS, OBMONTADA, CODIGO_ARTIGO_CRU, DT_ENTREGA, ID_CLIENTE,
--   NOME_CLIENTE
--
-- Dominios (confirmados via ALL_TAB_COLUMNS e amostra real em 16/07/2026):
--   OB.STATUS      -> 0 = encerrada | 1 = emitida | 3 = programada
--   PPOB.OBMONTADA -> texto '1' = montada/atendida | '0' = nao montada
--
-- Chaves de join reais (SGTPRD nao usa "ID"/"ID_OB" como no rascunho inicial):
--   SGTPRD.OB.NUMERO_OB (PK)               -> identificador da OB
--   SGTPRD.OB_PRODUTO.NUMERO_OB            -> FK para OB (chave composta com
--                                             CODPRO_REDUZIDO/NUMERO_PEDIDO/etc,
--                                             mas 1:1 com OB para fluxo 204/status 1
--                                             — confirmado por amostragem real:
--                                             LINHAS_BRUTAS = OBS_DISTINTAS)
--   SGTPRD.PEDPRODUCAOOB.NUMEROOB          -> FK para OB (sem underscore)
--
-- Metrica de comparacao com o estoque e TOTAL_PECAS (nunca KILOS_PROGRAMADOS).
--
-- Artigo cru (16/07/2026): SGTPRD.ENGEITEMESTOARTCRU.CDARTIGOCRU, join por
-- CDREDUZIDO = OB.CODIGO_REDUZIDO_CRU. Validado 1:1 sem nulos em amostra real
-- de 1293 OBs historicas de fluxo 204 (mesmo padrao de Receitas Emitidas e
-- OBs Paradas Fase). LEFT JOIN por seguranca, mas o dominio real e sempre 1:1.
--
-- Filtro de pedido comercial (16/07/2026): exclui OBs cujo PEDIDOCLIENTE
-- (SGTPRD.PEDIDOCOMERCIAL) termina em 'R' ou 'S'. O caminho de join ate
-- PEDIDOCOMERCIAL e o mesmo usado em Montagem de Terceirizados e OBs Paradas
-- Fase:
--   PEDPRODUCAOOB -> OFORDENS (NUMEROPEDPRODUCAO+REDUZIDO)
--                 -> OFPEDIDO (NUMEROOF+NIVEL+REDUZIDO)
--                 -> ITENSPEDIDOQTDES (IDITENSPEDIDOQTDES)
--                 -> ITENSPEDIDOGRADE (IDITEMPEDGRADE)
--                 -> ITENSPEDIDOCOMERCIAL (PEDIDO+ITEMPEDIDO)
--                 -> PEDIDOCOMERCIAL (PEDIDO)
-- ATENCAO — fan-out real confirmado por amostragem (nao e hipotetico): em 1293
-- OBs historicas de fluxo 204, 18 tinham mais de uma linha de OFPEDIDO por OB e
-- em 7 delas o PEDIDOCLIENTE resultante era DIFERENTE entre as linhas — sempre
-- por causa de um pedido "placeholder" (PEDIDOCLIENTE='0', mesmo PEDIDO/ITEM em
-- casos distintos) que convive com o pedido comercial real na mesma OFORDENS.
-- O filtro `OFP.QUANTIDADE_ATUAL <> 0` na condicao do LEFT JOIN com OFPEDIDO
-- (mesmo filtro usado na CTE ENTREGA_OB de OBs Paradas Fase) elimina esse
-- placeholder e devolve exatamente 1 linha por OB nas mesmas 1293 OBs, sem
-- nenhum PEDIDOCLIENTE conflitante. Nao remover esse filtro achando redundante.
--
-- OB sem pedido comercial associado (PEDIDOCLIENTE nulo apos os LEFT JOINs) e
-- tratada como "sem sufixo R/S conhecido" e permanece na lista — o filtro so
-- exclui quando ha certeza de que o pedido termina em R ou S.
--
-- Entrega e filial destino (17/07/2026): mesmos campos/joins da CTE ENTREGA_OB
-- de OBs Paradas Fase — DT_ENTREGA = TO_DATE(IPC.EXPEDIREM, 'YYYYMMDD') e
-- NOME_CLIENTE = TRIM(PES.NOMEFANTASIA), via SGTPRD.PESSOASFJ.IDPESSOAFJ =
-- PED.IDFILIALRESPONSAVEL. ID_CLIENTE (= IDFILIALRESPONSAVEL) alimenta a regra
-- de priorizacao em validators.priorizar_obs: id 1 = CR-MATRIZ/PR (deposito de
-- malhas) vai para o fim da lista; os demais ids sao lojas, que tem prioridade.
-- LEFT JOIN porque OB sem pedido comercial permanece na lista (campos nulos).
--
-- Plano de execucao (EXPLAIN PLAN, 16/07/2026 — antes dos joins de artigo e
-- pedido comercial): NESTED LOOPS via OB_INDOB_DTENTRPEDIDO +
-- OB_PROD_PK_OB_PRODUTO + PPRODUOB_IND_OB_NUMERO, custo total 19, sem full
-- table scan. Os joins de artigo/pedido comercial adicionados em 16/07/2026
-- usam FKs indexadas (mesmo caminho de Montagem de Terceirizados/OBs Paradas
-- Fase); reavaliar o plano se a cardinalidade real mudar.
-- =============================================================================
SELECT OB.NUMERO_OB,
       OB.CODIGO_FLUXO,
       OB.CODIGO_REDUZIDO_CRU,
       OB.STATUS,
       OBP.TOTAL_PECAS,
       OBP.KILOS_PROGRAMADOS,
       PPOB.OBMONTADA,
       ART.CDARTIGOCRU AS CODIGO_ARTIGO_CRU,
       TO_DATE(IPC.EXPEDIREM, 'YYYYMMDD') AS DT_ENTREGA,
       PED.IDFILIALRESPONSAVEL AS ID_CLIENTE,
       TRIM(PES.NOMEFANTASIA) AS NOME_CLIENTE
  FROM SGTPRD.OB OB
 INNER JOIN SGTPRD.OB_PRODUTO OBP
    ON OB.NUMERO_OB = OBP.NUMERO_OB
 INNER JOIN SGTPRD.PEDPRODUCAOOB PPOB
    ON OB.NUMERO_OB = PPOB.NUMEROOB
  LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ART
    ON ART.CDREDUZIDO = OB.CODIGO_REDUZIDO_CRU
  LEFT JOIN SGTPRD.OFORDENS OFO
    ON OFO.NUMEROPEDPRODUCAO = PPOB.NUMERO
   AND OFO.REDUZIDO = PPOB.REDUZIDO
  LEFT JOIN SGTPRD.OFPEDIDO OFP
    ON OFP.NUMEROOF = OFO.NUMEROOF
   AND OFP.NIVEL = OFO.NIVEL
   AND OFP.REDUZIDO = OFO.REDUZIDO
   AND OFP.QUANTIDADE_ATUAL <> 0
  LEFT JOIN SGTPRD.ITENSPEDIDOQTDES IPQ
    ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
  LEFT JOIN SGTPRD.ITENSPEDIDOGRADE IPG
    ON IPG.IDITENSPEDIDOGRADE = IPQ.IDITEMPEDGRADE
  LEFT JOIN SGTPRD.ITENSPEDIDOCOMERCIAL IPC
    ON IPC.PEDIDO = IPG.PEDIDO
   AND IPC.ITEMPEDIDO = IPG.ITEMPEDIDO
  LEFT JOIN SGTPRD.PEDIDOCOMERCIAL PED
    ON PED.PEDIDO = IPC.PEDIDO
  LEFT JOIN SGTPRD.PESSOASFJ PES
    ON PES.IDPESSOAFJ = PED.IDFILIALRESPONSAVEL
 WHERE OB.CODIGO_FLUXO = 204
   AND OB.STATUS = 1
   AND PPOB.OBMONTADA = '0'
   AND (
        PED.PEDIDOCLIENTE IS NULL
     OR (PED.PEDIDOCLIENTE NOT LIKE '%R' AND PED.PEDIDOCLIENTE NOT LIKE '%S')
   )
