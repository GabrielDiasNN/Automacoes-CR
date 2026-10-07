/* =============================================================================
OBJETIVO: Conferência - OB montada consulta NF de entrada das peças (facção)
DOMÍNIO: 06_qualidade_auditoria_obs
ARQUIVO ORIGINAL: Comandos SQL - CR\Conferência - OB montada consulta NF de entrada das peças (facção).sql
TIPO: Auditoria e Qualidade de OBs
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.GERAPECANOTAENTRADA, SGTPRD.GERAPECAORIGEMOB, SGTPRD.PESSOASFJ
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT GPO.NUMERO_OB                           NUMERO_OB,
       COUNT(GPO.IDPECASPRODUTO)               PECAS,
       GPN.NUMERO_NOTA                         NF_ENTRADA,
       GPN.LOTE                                LOTE_PRODUTO,
       (SELECT TRIM(PJ.NOME) 
          FROM SGTPRD.PESSOASFJ PJ 
         WHERE PJ.IDPESSOAFJ = GPN.IDPESSOAFJ) NOME_FACCAO
  FROM SGTPRD.GERAPECANOTAENTRADA GPN, 
       SGTPRD.GERAPECAORIGEMOB GPO
 WHERE GPN.IDPECASPRODUTO = GPO.IDPECASPRODUTO
   AND GPO.NUMERO_OB IN (103260) --AQUI POSSO ALTERAR A OB QUE QUERO CONSULTAR
 GROUP BY GPO.NUMERO_OB,
       GPN.NUMERO_NOTA,
       GPN.LOTE,
       GPN.IDPESSOAFJ
 ORDER BY 1, 2 DESC
