-- =============================================================================
-- ORB-07 — finalidades de peça compatíveis com as classificações de cor alvo.
--
-- Esta consulta NAO define o conjunto contabilizado: ele e fixo em
-- FINALIDADES_PECA_ALVO = {3, 4} (models.py). SGTPRD.COR_FINALIDADE serve aqui
-- para dois fins: resolver as descricoes oficiais das finalidades e falhar de
-- forma observavel caso 3 ou 4 deixem de constar como compativeis com as
-- classes brancas. Ampliar o saldo com as demais finalidades do cadastro — em
-- especial a 1 (SEM RESTRICAO) — e proibido pela regra de negocio.
--
-- O marcador /*IN_BINDS*/ é substituído por binds gerados em queries.py com as
-- classificações alvo (6 = BRANCO, 9 = BRANCO 2 FIBRAS).
-- =============================================================================
SELECT CF.CODCLASSIFICACAO_COR,
       CF.CODFINALIDADE,
       TRIM(TFF.DESCRICAO) AS DESCRICAO_FINALIDADE
  FROM SGTPRD.COR_FINALIDADE CF
 INNER JOIN SGTPRD.TIPO_FINALIDADE_FIO TFF
    ON TFF.NUMERO_FINALIDADE = CF.CODFINALIDADE
 WHERE CF.CODCLASSIFICACAO_COR IN (/*IN_BINDS*/)
 ORDER BY CF.CODCLASSIFICACAO_COR, CF.CODFINALIDADE
