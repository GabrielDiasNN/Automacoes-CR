/*
================================================================================
TESTE DE PERFORMANCE: Diagnóstico de Custo
OBJETIVO: Verificar o plano de execução e estatísticas de I/O.
================================================================================
*/

SET TIMING ON;
SET AUTOTRACE TRACEONLY;

PROMPT >>> ANALISANDO CUSTO DA QUERY OTIMIZADA...

-- Execução simulada (traz apenas estatísticas, não os dados)
@query_otimizada.sql

SET AUTOTRACE OFF;
SET TIMING OFF;

/*
O QUE CHECAR NO RESULTADO:
1. 'consistent gets': Quanto menor este número, menos o banco trabalhou.
2. 'recursive calls': Deve ser próximo de zero na versão otimizada.
3. 'Rows Processed': Deve ser idêntico ao teste de integridade.
*/
