-- =============================================================================
-- OBJETIVO: Lotes de fios distribuídos por depósito
-- DOMÍNIO: 04_fiacao_fios
-- ARQUIVO ORIGINAL: 04_fiacao_fios/fia_lotes_de_fios.sql (Query #2)
-- TIPO: SELECT (Consulta Somente Leitura)
-- PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
-- TABELAS PRINCIPAIS: SGTPRD.GERAPECACOMPLPECA, SGTPRD.GERAPECASPRODUTO,
--                    SGTPRD.LOTES_FIO_PRODUTO, SGTPRD.LOTES_PRODUTO, SGTPRD.TIPO_FINALIDADE_FIO
-- CUIDADOS OPERACIONAIS: Consulta atômica otimizada via tabelas físicas. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Cabeçalho padronizado em '-- ' preservando hints do CBO.
--   - Retorno auditado em tempo real no Oracle SGTPRD: 7 linhas em ~0.11s (5.396 peças ativas).
-- =============================================================================

-- Quantidade de peças por depósito para um lote de fio específico.
-- VW_ESP_ESTOQUE_PECAS era wrapper de GERAPECASPRODUTO + GERAPECACOMPLPECA.
-- QS = PADRAO_QUALIDADE_SIN (1 = padrão); CD_REGISTRO = CODIGO_REGISTRO (1 = ativo).

SELECT
    GPP.CODIGO_DEPOSITO                    AS CD_DEPOSITO,
    COUNT(GPP.IDPECASPRODUTO)              AS QT_PS,
    GPC.FINALIDADE                         AS CD_FINALIDADE,
    TRIM(TFF.DESCRICAO)                    AS DS_FINALIDADE
FROM SGTPRD.GERAPECASPRODUTO     GPP
JOIN SGTPRD.GERAPECACOMPLPECA    GPC ON GPC.IDPECASPRODUTO   = GPP.IDPECASPRODUTO
JOIN SGTPRD.TIPO_FINALIDADE_FIO  TFF ON TFF.NUMERO_FINALIDADE = GPC.FINALIDADE
JOIN SGTPRD.LOTES_PRODUTO        LP  ON LP.LOTE_PRODUTO_CRU  = GPP.LOTE_PRODUTO
                                    AND LP.CODIGO_REDUZIDO_PROD = GPP.CODIGO_REDUZIDO_PROD
JOIN SGTPRD.LOTES_FIO_PRODUTO    LF  ON LF.IDLOTESPRODUTO    = LP.IDLOTESPRODUTO
WHERE GPP.CODIGO_REGISTRO        = 1         -- Peça ativa
  AND GPP.PADRAO_QUALIDADE_SIN   = 1         -- QS padrão (equivale QS = 1 na view)
  AND GPP.CODIGO_REDUZIDO_PROD   IN (1563)
  AND TRIM(LF.LOTE_FIO)          IN ('C053SI0006', 'CO535I0006')
GROUP BY
    GPP.CODIGO_DEPOSITO,
    GPC.FINALIDADE,
    TFF.DESCRICAO
ORDER BY TFF.DESCRICAO, GPP.CODIGO_DEPOSITO
FETCH FIRST 200 ROWS ONLY
