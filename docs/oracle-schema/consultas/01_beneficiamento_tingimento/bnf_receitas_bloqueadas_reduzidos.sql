/* =============================================================================
OBJETIVO: Receitas de tingimento bloqueadas por código reduzido
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: 01_beneficiamento_tingimento/bnf_receitas_bloqueadas_cores_eps_e_reduzidos.sql (Query #2)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.CADASTRO_RECEITAS, SGTPRD.ITENS_ESTOQUE, SGTPRD.LABRECEITA_BLOQUEADA, SGTPRD.LIGA_CADREC_ITEMREC
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
============================================================================= */

SELECT ITE.CODIGO_REDUZIDO,
       DECODE(LRB.BLOQUEIO_RECEITA, 0, 'BLOQUEADO', 1, 'OK') SIT_RECEITA
  FROM SGTPRD.CADASTRO_RECEITAS    CRE,
       SGTPRD.LIGA_CADREC_ITEMREC  LCR,
       SGTPRD.LABRECEITA_BLOQUEADA LRB,
       SGTPRD.ITENS_ESTOQUE        ITE
 WHERE LCR.CODIGO_REDUZIDO_RECE = CRE.CODIGO_REDUZIDO_RECE
   AND LRB.ID_LABRECEITA_BLOQ = LCR.ID_LABRECEITA_BLOQ
   AND TRIM(CRE.CODCOR) = SUBSTR(ITE.CODIGO, 13, 5)
   AND CRE.ESPECIFICACAO_PRODUT = ITE.ESPECIFICACAOPRODUTO
   AND ITE.TIPO_ITEM = 10
   AND CRE.PROCESSOINDUSTRIAL = 401
   AND CRE.PROCESSO_ATIVO_PRODU = 1
   AND LRB.BLOQUEIO_RECEITA = 0;
