/* =============================================================================
OBJETIVO: Usuários ativos
DOMÍNIO: 13_utilitarios_snippets
ARQUIVO ORIGINAL: Comandos SQL - CR\Usuários ativos.sql
TIPO: Segurança e Usuários
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ORABLOQUEIO_USUARIOS, SGTPRD.CRISTAL, SGTPRD.SETOR_USUARIO
CUIDADOS OPERACIONAIS: Consulta somente tabelas físicas. A informação dinâmica de programa, antes
                         obtida de GV$SESSION, fica NULL porque views de sessão estão fora do escopo.
============================================================================= */

SELECT O.CDFILIAL AS FILIAL,
       TRIM(O.USUARIO) AS USUARIO_SGT,
       O.DATALOGON AS DATA_HORA_LOGIN,
       CAST(NULL AS VARCHAR2(128)) AS PROGRAMA,
       O.VERSAO_EXECUTAVEL AS RELEASE,
       TRIM(SUS.DESCRICAO) AS DESCR_SETOR,
       CRI.SESSAO_SIMULTANEA
  FROM SGTPRD.ORABLOQUEIO_USUARIOS O
  LEFT JOIN SGTPRD.CRISTAL CRI
    ON TRIM(CRI.USUARIO) = TRIM(O.USUARIO)
  LEFT JOIN SGTPRD.SETOR_USUARIO SUS
    ON SUS.ID = CRI.ID_SETOR_USUARIO
 ORDER BY O.CDFILIAL, TRIM(O.USUARIO), O.DATALOGON;
