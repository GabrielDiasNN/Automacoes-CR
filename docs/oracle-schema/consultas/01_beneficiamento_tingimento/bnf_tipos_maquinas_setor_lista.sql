/* =============================================================================
OBJETIVO: Tabela de tipos de máquinas por setor industrial
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: 01_beneficiamento_tingimento/bnf_liga_numero_up_na_ob.sql (Query #5a)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.TIPOSMAQUINAS
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT TM.IDTIPOSMAQUINA AS TIPO_MAQUINA,
       TM.DESCRICAO,
       TM.SETOR
  FROM SGTPRD.TIPOSMAQUINAS TM
 ORDER BY 1;
