/* =============================================================================
OBJETIVO: Consulta de permissões de atividades liberadas para usuários
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: 13_utilitarios_snippets/util_atividade_liberada_nos_usuarios.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.CRISTAL, SGTPRD.SENHA_ATIVIDADE
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT C.USUARIO, S.ATIVIDADE, S.CODREDUSUARIO
  FROM SGTPRD.SENHA_ATIVIDADE S
 INNER JOIN SGTPRD.CRISTAL C
    ON C.CODREDUSUARIO = S.CODREDUSUARIO
 WHERE S.ATIVIDADE IN (3012);
