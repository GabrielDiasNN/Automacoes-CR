/* =============================================================================
OBJETIVO: OB_FASES - seleciona última sequência da fase
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\OB_FASES - seleciona última sequência da fase.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.OB_FASES
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
VOLUME: histórico completo de OB_FASES, ~1,33 milhão de linhas e ~16 s de mediana (16/10/2026).
  Para o estado das fases das OBs emitidas nos últimos 365 dias, use
  bnf_ob_fases_ultima_sequencia_fase_ultimos_365d.sql (~214 mil linhas, ~2,9 s; mesmas colunas e valores).
============================================================================= */

SELECT
    H.NUMERO_OB,
    H.CODIGO_FASE,
    MAX(H.STATUS) KEEP (DENSE_RANK LAST ORDER BY H.SEQUENCIA) AS STATUS_ULT,
    MAX(H.NUMERO_MAQUINA) KEEP (DENSE_RANK LAST ORDER BY H.SEQUENCIA) AS NR_MAQ_ULT,
    MAX(H.SEQUENCIA) AS SEQ_ULT
  FROM sgtprd.OB_FASES H
  GROUP BY H.NUMERO_OB, H.CODIGO_FASE
  ORDER BY H.NUMERO_OB DESC, MAX(H.SEQUENCIA) ASC