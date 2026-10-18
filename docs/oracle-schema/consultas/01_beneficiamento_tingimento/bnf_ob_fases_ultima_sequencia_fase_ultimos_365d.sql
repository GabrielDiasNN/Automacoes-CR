/* =============================================================================
OBJETIVO: OB_FASES - última sequência por fase, apenas OBs emitidas nos últimos 365 dias
DOMÍNIO: 01_beneficiamento_tingimento
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (janela fixa de 365 dias a partir de SYSDATE)
GRANULARIDADE: uma linha por NUMERO_OB e CODIGO_FASE
VARIANTE DE: bnf_ob_fases_seleciona_ultima_sequencia_da_fase.sql (mesma lógica, filtro por OB)
VALIDADE: 16/10/2026, equivalente à consulta completa no subconjunto de OBs (213.776 linhas, sem diferença)
TEMPO: ~2,9 s contra ~16 s da consulta completa (mediana de 3 execuções)
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura. Sem ORDER BY: remover a ordenação não mudou o tempo.
============================================================================= */

SELECT
    H.NUMERO_OB,
    H.CODIGO_FASE,
    MAX(H.STATUS) KEEP (DENSE_RANK LAST ORDER BY H.SEQUENCIA) AS STATUS_ULT,
    MAX(H.NUMERO_MAQUINA) KEEP (DENSE_RANK LAST ORDER BY H.SEQUENCIA) AS NR_MAQ_ULT,
    MAX(H.SEQUENCIA) AS SEQ_ULT
  FROM sgtprd.OB_FASES H
  WHERE H.NUMERO_OB IN (SELECT OBE.NUMERO_OB FROM sgtprd.OB OBE WHERE OBE.TEMPO_EMISSAO_OB >= (TRUNC(SYSDATE) - 365 - DATE '1996-01-01') * 1440)
  GROUP BY H.NUMERO_OB, H.CODIGO_FASE
  
