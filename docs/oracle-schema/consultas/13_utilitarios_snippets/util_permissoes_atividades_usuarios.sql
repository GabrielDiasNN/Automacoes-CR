/* =============================================================================
OBJETIVO: Consulta de permissões de atividades liberadas para usuários
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: 13_utilitarios_snippets/util_atividade_liberada_nos_usuarios.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.CRISTAL, SGTPRD.SENHA_ATIVIDADE
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT C.USUARIO, S.*
  FROM SGTPRD.SENHA_ATIVIDADE S, SGTPRD.CRISTAL C
 WHERE C.CODREDUSUARIO = S.CODREDUSUARIO
   AND S.ATIVIDADE IN (3012);
