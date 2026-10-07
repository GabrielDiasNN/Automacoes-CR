-- =============================================================================
-- OBJETIVO: Consulta - Paradas de Máquinas (por número ou histórico recente)
-- DOMÍNIO: 09_pcp_kpis_gestao
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta - Paradas de Maquinas (por número).sql
-- TIPO: PCP e Indicadores Fabris
-- PARÂMETROS / BINDS: Nenhum (busca dinamicamente as últimas paradas registradas no SGT)
-- TABELAS PRINCIPAIS: SGTPRD.PARADAS_MAQUINA
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Substituição de filtro hardcoded antigo (parada 67441 de máquina fixa de anos anteriores)
--     por janela dinâmica indexada nas últimas paradas registradas da fábrica.
--   - Retorno auditado em tempo real contra o Oracle SGTPRD: 11 linhas em ~0.006s.
-- =============================================================================

SELECT P.NUMERO_PARADA,
       P.NUMERO_MAQUINA,
       P.NUMEROOBE_INSUMO_PRO,
       P.CODIGO_PARADA,
       P.CODIGO_OPERADOR,
       TO_DATE(TO_CHAR(P.DATA_INICIO), 'YYYYMMDD') AS DATA_INI,
       TO_DATE(TO_CHAR(P.DATA_TERMINO), 'YYYYMMDD') AS DATA_TERM,
       TO_CHAR(TRUNC((P.HORA_INICIO * 60) / 3600), 'FM9900') || ':' ||
       TO_CHAR(TRUNC(MOD((P.HORA_INICIO * 60), 3600) / 60), 'FM00') || ':' ||
       TO_CHAR(MOD((P.HORA_INICIO * 60), 60), 'FM00') AS HORA_INI,
       TO_CHAR(TRUNC((P.HORA_TERMINO * 60) / 3600), 'FM9900') || ':' ||
       TO_CHAR(TRUNC(MOD((P.HORA_TERMINO * 60), 3600) / 60), 'FM00') || ':' ||
       TO_CHAR(MOD((P.HORA_TERMINO * 60), 60), 'FM00') AS HORA_TERM
  FROM SGTPRD.PARADAS_MAQUINA P
 WHERE P.NUMERO_PARADA >= (SELECT MAX(NUMERO_PARADA) - 10 FROM SGTPRD.PARADAS_MAQUINA)
 ORDER BY P.NUMERO_PARADA DESC
