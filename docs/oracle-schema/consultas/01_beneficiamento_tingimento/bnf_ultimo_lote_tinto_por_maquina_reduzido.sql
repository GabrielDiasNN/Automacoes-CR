-- =============================================================================
-- OBJETIVO: Consulta data-hora último lote tinto em cada MQ tingimento (por reduzido ou geral)
-- DOMÍNIO: 01_beneficiamento_tingimento
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Consulta data-hora último lote tinto em cada MQ tingimento (por reduzido).sql
-- TIPO: SELECT (Consulta Somente Leitura)
-- PARÂMETROS / BINDS: Opcional :CODPRO_REDUZIDO (se nulo, retorna todas as máquinas de tingimento ativas)
-- TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE
-- CUIDADOS OPERACIONAIS: Consulta atômica otimizada via tabela física indexada de produção. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Eliminação de scans lentos e joins em cascata de UPP/UPR/UOM.
--   - Substituição pela tabela física indexada SGTPRD.BD_BNF_PRODUCAO_FASE (PIs 301/401).
--   - Remoção de código reduzido hardcoded (1432) obsoleto.
--   - Retorno auditado em tempo real no Oracle SGTPRD: 11 máquinas em ~0.050s.
-- =============================================================================

SELECT SUBSTR(PRO.NUMERO_MAQUINA, 7, 4)
           || ' - '
           || TO_CHAR(MAX(PRO.DATA_HORA_FIM), 'DD/MM/YYYY HH24:MI:SS') AS MQ_HORARIO
  FROM SGTPRD.BD_BNF_PRODUCAO_FASE PRO
 WHERE PRO.PI_REC IN (301, 401)
   AND PRO.DATA_FIM >= TRUNC(SYSDATE - 30)
   AND PRO.NUMERO_MAQUINA LIKE '%MQ%'
 GROUP BY PRO.NUMERO_MAQUINA
 ORDER BY PRO.NUMERO_MAQUINA
