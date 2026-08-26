-- =============================================================================
-- ORB-07 — peças cruas do depósito 95 elegíveis para OBs classificadas como
-- branco (classes 6 e 9).
--
-- As finalidades aceitas sao FIXAS por regra de negocio: 3 (CORES CLARAS) e
-- 4 (BRANCO). Elas chegam por bind (FINALIDADES_PECA_ALVO em models.py) apenas
-- para nao ficarem literais no SQL. SGTPRD.COR_FINALIDADE lista para as classes
-- brancas um conjunto maior ({1,3,4,6,8,12,13}), mas a finalidade 1
-- (SEM RESTRICAO) NAO pode ser contabilizada por esta automacao.
--
-- GROUPING SETS devolve, na mesma passada, uma linha TOTAL por reduzido
-- (EH_TOTAL = 1, FINALIDADE nula) e uma linha por finalidade. O total é
-- COUNT(DISTINCT) sobre a união e é o saldo autoritativo — somar as linhas por
-- finalidade seria correto só enquanto cada peça tiver uma única finalidade
-- cadastrada, o que o SQL não garante. QTD_LINHAS_BRUTAS detecta fan-out.
--
-- O marcador /*IN_BINDS*/ recebe os reduzidos e /*FIN_BINDS*/ as finalidades;
-- ambos são gerados em queries.py, nunca interpolados.
-- =============================================================================
SELECT GPP.CODIGO_REDUZIDO_PROD,
       GPC.FINALIDADE,
       GROUPING(GPC.FINALIDADE) AS EH_TOTAL,
       COUNT(DISTINCT GPP.IDPECASPRODUTO) AS QTD_PECAS_DISPONIVEIS,
       COUNT(GPP.IDPECASPRODUTO) AS QTD_LINHAS_BRUTAS
  FROM SGTPRD.GERAPECASPRODUTO GPP
 INNER JOIN SGTPRD.GERAPECACOMPLPECA GPC
    ON GPC.IDPECASPRODUTO = GPP.IDPECASPRODUTO
 INNER JOIN SGTPRD.GERAPECACRU GCR
    ON GCR.IDPECASPRODUTO = GPC.IDPECASPRODUTO
 WHERE GPP.CODIGO_REGISTRO = 1
   -- TIPO_FINALIDADE_FIO e ITENS_ESTOQUE sao filtros de EXISTENCIA, nao fontes de
   -- coluna: a peca so' entra no saldo se a finalidade estiver cadastrada na tabela
   -- de dominio e o reduzido existir no cadastro de itens de estoque. Como INNER JOIN
   -- (forma anterior) eles multiplicavam a linha quando a chave nao era unica,
   -- inflando QTD_LINHAS_BRUTAS e disparando WARN permanente de fan-out em
   -- _fetch_estoque. EXISTS preserva a semantica de filtro sem duplicar linha.
   AND EXISTS (
           SELECT 1
             FROM SGTPRD.TIPO_FINALIDADE_FIO TFF
            WHERE TFF.NUMERO_FINALIDADE = GPC.FINALIDADE
       )
   AND EXISTS (
           SELECT 1
             FROM SGTPRD.ITENS_ESTOQUE ITE
            WHERE ITE.CODIGO_REDUZIDO = GPP.CODIGO_REDUZIDO_PROD
       )
   AND GPP.STPECAPRODUTO IN (0, 16, 18)
   AND GPP.IDPESSOAFJESTOQUE = 2
   AND GPP.PADRAO_QUALIDADE_SIN = 1
   AND GPP.CODIGO_DEPOSITO = 95
   AND GPC.FINALIDADE IN (/*FIN_BINDS*/)
   AND GPP.CODIGO_REDUZIDO_PROD IN (/*IN_BINDS*/)
 GROUP BY GROUPING SETS (
           (GPP.CODIGO_REDUZIDO_PROD),
           (GPP.CODIGO_REDUZIDO_PROD, GPC.FINALIDADE)
       )
