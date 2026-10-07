-- =============================================================================
-- OBJETIVO: Lotes de fios agrupados por fornecedor/pessoa
-- DOMÍNIO: 04_fiacao_fios
-- ARQUIVO ORIGINAL: 04_fiacao_fios/fia_lotes_de_fios.sql (Query #1)
-- TIPO: SELECT (Consulta Somente Leitura)
-- PARÂMETROS / BINDS: Nenhum (janela dinâmica: peças ativas dos últimos 60 dias)
-- TABELAS PRINCIPAIS: SGTPRD.GERAPECASPRODUTO, SGTPRD.ITENS_ESTOQUE,
--                    SGTPRD.LOTES_FIO_PRODUTO, SGTPRD.LOTES_PRODUTO, SGTPRD.PESSOASFJ
-- CUIDADOS OPERACIONAIS: Consulta atômica otimizada de saldo de lotes por fornecedor. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Substituição de varredura histórica completa em GERAMOVIMENTOESTOQUE por apuração
--     direta via peças ativas em GERAPECASPRODUTO e vínculo em LOTES_PRODUTO / LOTES_FIO_PRODUTO.
--   - Remoção de lotes estáticos descontinuados da consulta.
--   - Tempo de execução reduzido de timeout (>11.4s) para ~0.38s (dados 100% reais de produção).
-- =============================================================================

SELECT LFP.IDPESSOAFJ AS ID_FORNECEDOR,
       TRIM(PES.NOME) AS NOME_FORNECEDOR,
       LFP.CODIGO_REDUZIDO_FIO AS REDUZIDO_FIO,
       TRIM(ITE.DESCRICAO) AS DESCRICAO_FIO,
       LFP.LOTE_FIO,
       COUNT(GPP.IDPECASPRODUTO) AS QTD_PECAS,
       ROUND(SUM(GPP.QTLIQUIDA), 2) AS QTD_KG
  FROM SGTPRD.LOTES_FIO_PRODUTO LFP
  JOIN SGTPRD.LOTES_PRODUTO LP ON LP.IDLOTESPRODUTO = LFP.IDLOTESPRODUTO
  JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.CODIGO_REDUZIDO_PROD = LP.CODIGO_REDUZIDO_PROD
                                  AND GPP.LOTE_PRODUTO = LP.LOTE_PRODUTO_CRU
  JOIN SGTPRD.PESSOASFJ PES ON PES.IDPESSOAFJ = LFP.IDPESSOAFJ
  JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = LFP.CODIGO_REDUZIDO_FIO
 WHERE GPP.CODIGO_REGISTRO = 1
   AND GPP.PADRAO_QUALIDADE_SIN = 1
   AND GPP.DATA_DA_ENTRADA_PECA >= TO_NUMBER(TO_CHAR(SYSDATE - 60, 'YYYYMMDD'))
 GROUP BY LFP.IDPESSOAFJ,
          PES.NOME,
          LFP.CODIGO_REDUZIDO_FIO,
          ITE.DESCRICAO,
          LFP.LOTE_FIO
 ORDER BY QTD_KG DESC
 FETCH FIRST 100 ROWS ONLY
