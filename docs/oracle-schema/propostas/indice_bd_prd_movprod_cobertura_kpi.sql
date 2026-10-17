/* =============================================================================
PROPOSTA DE ÍNDICE - NÃO EXECUTAR SEM APROVAÇÃO EXPLÍCITA DO DBA
Tabela: SGTPRD.BD_PRD_MOVPROD (60.228.251 linhas nas estatísticas de 14/10/2026)
Objetivo: cobrir o filtro e as colunas lidas pelas consultas de KPI de produção
          (pcp_producao_12m_matriz_pivotada e pcp_producao_12m_fato_serie_temporal)
          para permitir leitura só pelo índice, sem acesso à tabela.
Justificativa e medições: ver indice_bd_prd_movprod_cobertura_kpi.md (mesma pasta).
Este arquivo é somente proposta. Nenhuma parte dele foi executada no Oracle.
============================================================================= */

-- ---------------------------------------------------------------------------
-- 1. PRÉ-CHECAGEM (somente leitura). Conferir antes de criar.
-- ---------------------------------------------------------------------------
-- 1a. Nenhum índice existente já cobre o mesmo prefixo:
SELECT INDEX_NAME, COLUMN_POSITION, COLUMN_NAME
  FROM ALL_IND_COLUMNS
 WHERE TABLE_OWNER = 'SGTPRD' AND TABLE_NAME = 'BD_PRD_MOVPROD'
 ORDER BY INDEX_NAME, COLUMN_POSITION;
-- Em 16/10/2026 o prefixo (CODIGO, PRODUCAO_DATA) existia em BDMOVPR_IND_MOVPRD_DATA e
-- BDMOVPR_IND_MOVPRD_DATAN, mas sem NUM_TIPO_MOVIMENTO, PRODUCAO_TURNO, REDUZIDO_ITEM,
-- ESTAMPADO, QUANTIDADE_REAL e IDPECASPRODUTO. Por isso o acesso à tabela continua.

-- 1b. Espaço livre no tablespace (ajustar o tamanho conforme o resultado):
SELECT TABLESPACE_NAME, ROUND(SUM(BYTES)/1024/1024) AS MB_LIVRES
  FROM DBA_FREE_SPACE
 WHERE TABLESPACE_NAME = 'COSTARICADT'
 GROUP BY TABLESPACE_NAME;

-- ---------------------------------------------------------------------------
-- 2. CRIAÇÃO (DDL). Executar só após aprovação do DBA e em janela de baixa carga.
--    ONLINE: não bloqueia DML na tabela de produção durante a construção.
--    LOGGING: mantém o padrão dos índices existentes (todos LOGGING = YES).
--    Sem PARALLEL no índice: o padrão atual é DEGREE 1; ajustar se o DBA preferir.
-- ---------------------------------------------------------------------------
CREATE INDEX SGTPRD.BDMOVPR_IND_KPI_COBERTURA
    ON SGTPRD.BD_PRD_MOVPROD (
        CODIGO,               -- igualdade (IN (1, 8))
        NUM_TIPO_MOVIMENTO,   -- igualdade (= 37)
        PRODUCAO_DATA,        -- faixa (janela de 13 meses)
        PRODUCAO_TURNO,       -- colunas lidas pela consulta (cobertura)
        REDUZIDO_ITEM,
        ESTAMPADO,
        QUANTIDADE_REAL,
        IDPECASPRODUTO
    )
    TABLESPACE COSTARICADT
    LOGGING
    ONLINE;

-- 2b. Estatísticas do novo índice (o otimizador precisa delas para escolhê-lo):
BEGIN
    DBMS_STATS.GATHER_INDEX_STATS(
        ownname => 'SGTPRD',
        indname => 'BDMOVPR_IND_KPI_COBERTURA'
    );
END;
/

-- ---------------------------------------------------------------------------
-- 3. VALIDAÇÃO após criar (somente leitura):
--    a) Rodar medir_sql_oracle.py nas duas consultas, com --explain, e confirmar que
--       o plano usa BDMOVPR_IND_KPI_COBERTURA como INDEX RANGE/FAST FULL SCAN, sem
--       TABLE ACCESS BY INDEX ROWID em BD_PRD_MOVPROD para o trecho do filtro.
--    b) Medir a mediana (3 execuções) antes/depois e comparar com a linha de base.
--    c) Confirmar equivalência de resultado com comparar_equivalencia.py:
--       --chaves ORDEM,INDICADOR_FABRIL (matriz) e as chaves do GRÃO (fato).
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 4. ROLLBACK (se a validação ou o desempenho do DML piorar):
-- ---------------------------------------------------------------------------
-- DROP INDEX SGTPRD.BDMOVPR_IND_KPI_COBERTURA;
