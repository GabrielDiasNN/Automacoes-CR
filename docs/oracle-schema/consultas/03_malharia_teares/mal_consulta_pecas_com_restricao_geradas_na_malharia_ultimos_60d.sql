-- =============================================================================
-- OBJETIVO: Consulta - Peças com restrição geradas na Malharia
-- DOMÍNIO: 03_malharia_teares
-- ARQUIVO ORIGINAL: (referência histórica) arquivo de origem fora deste repositório, não versionado aqui.
-- TIPO: Malharia e Teares
-- PARÂMETROS / BINDS: Nenhum (janela dinâmica indexada: últimos 60 dias de pesagem)
-- DATA_ENTRADA: alias de GPP.DATA_DA_ENTRADA_PECA, que é a data de PESAGEM
--   (pode ser posterior à produção), não a data de produção.
-- TABELAS PRINCIPAIS: SGTPRD.GERAPECAORDEMMALHA, SGTPRD.GERAPECACOMPLPECA, SGTPRD.GERAPECACRU, SGTPRD.GERAPECAORIGEMOB,
--                    SGTPRD.GERAPECASPRODUTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.TIPO_FINALIDADE_FIO,
--                    SGTPRD.XX2_ENUMERATES, SGTPRD.XX2_ENUMITEM
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
-- REVISÃO (08/10/2026):
--   - Causa do resultado vazio (versão anterior): CODIGO_REGISTRO = 2 combinado com INNER JOIN em
--     GERAPECACRU. Nas janelas de até 365 dias, peças com registro 2 não têm linha em GERAPECACRU, e as
--     peças com GERAPECACRU têm registro 1. Medido: 0 peças com registro 2 e CRU nas janelas de 30, 60,
--     90, 180 e 365 dias. O vazio era estrutural, não falta de dados. As consultas de expedição (pasta 07)
--     usam registro 2; o significado exato do código não está documentado no catálogo.
--   - Registro 1 = peça ativa (convenção do acervo). Base = peça com ordem de malha (GERAPECAORDEMMALHA),
--     conforme REGRAS_NEGOCIO.md §5.2 e §5.8 (filhas de reagrupamento sem ordem de malha ficam de fora).
--   - "Sem restrição" = FINALIDADE 1 e 8 (convenção do acervo: est_pecas_com_restricoes_estoque,
--     mal_necessidade_*, qld_conferencia_ob_montada_*). Antes era <> 1. Medido: nas janelas de 30 e 60 dias
--     nenhuma peça com ordem de malha tem FINALIDADE 8; o resultado não muda. A partir de 90 dias a diferença
--     cresce.
--     Ressalva: o cadastro TIPO_FINALIDADE_FIO descreve a FINALIDADE 8 como "FIO C/ RESÍDUO"; o acervo a trata
--     como sem restrição. Decisão de negócio pendente.
--   - Teto FETCH FIRST 100 removido: escondia 98% do resultado de 30 dias (6.396 linhas medidas em 08/10/2026).
--   - Janela de 60 dias (SYSDATE - 60), conforme o nome do arquivo. Medido em 09/10/2026: 11.760 linhas,
--     estáveis entre as execuções. Fetch completo pelo medir_sql_oracle.py (conexão fora da medição),
--     mediana de 3 execuções = 2,18 s (mín 2,17; máx 2,21; ruído 0,04 s; execução no Oracle, mediana 2,13 s).
--     Uma das 3 execuções precisou de nova tentativa. Dentro da meta de 3 s (consultas/README.md).
--     Com conexão nova em cada execução (login incluído, run_sql.py), a mediana foi 4,84 s
--     (23,67 s; 3,76 s; 4,84 s). O README pede mediana de 5 execuções; aqui foram 3.
--     Medição anterior (08/10/2026): 11.725 linhas, 8,75 s de tempo de parede, 2,27 s de execução no Oracle.
--   - Limiar de timeout (restaurado do histórico de 23/09/2026, commit 5faf392): a janela de 30 dias foi
--     calibrada para evitar estouro de timeout; o tempo caiu de >7,8 s (ORA-00028) para ~0,95 s. Na janela de
--     60 dias, a mediana do fetch ficou abaixo de 7,8 s, mas a 1ª execução com conexão nova (23,67 s) ficou
--     acima. A rede derruba sessões em consultas com primeira linha lenta (ORA-00028/DPY-4011). Se a execução
--     cair com um desses códigos, é falha, não resultado vazio: rode de novo a consulta isolada (consultas/README.md).
-- =============================================================================

SELECT /*+ INDEX(GPP GRPCPROD_INDIDATAENTRPECA) */
       TO_DATE(TO_CHAR(GPP.DATA_DA_ENTRADA_PECA), 'YYYYMMDD') AS DATA_ENTRADA,
       GPP.IDPECASPRODUTO AS ID_PECA,
       LTRIM(GPCR.NUMERO_MAQUINA, '0') AS TEAR,
       GPP.CODIGO_DEPOSITO AS DEPOSITO,
       ENI.DESCRIPTION AS STATUS,
       GPP.QTLIQUIDA AS QT_LIQ,
       GPP.LOTE_PRODUTO,
       GPP.CODIGO_REDUZIDO_PROD AS REDUZIDO,
       TRIM(ITE.DESCRICAO) AS DESCRICAO_ITEM,
       TRIM(GPC.FINALIDADE || ' - ' || TFF.DESCRICAO) AS RESTRICAO,
       GPO.NUMERO_OB
  FROM SGTPRD.GERAPECASPRODUTO GPP
  JOIN SGTPRD.GERAPECACOMPLPECA GPC ON GPC.IDPECASPRODUTO = GPP.IDPECASPRODUTO
  JOIN SGTPRD.GERAPECACRU GPCR ON GPCR.IDPECASPRODUTO = GPP.IDPECASPRODUTO
  LEFT JOIN SGTPRD.GERAPECAORIGEMOB GPO ON GPO.IDPECASPRODUTO = GPP.IDPECASPRODUTO
  LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = GPP.CODIGO_REDUZIDO_PROD
  LEFT JOIN SGTPRD.TIPO_FINALIDADE_FIO TFF ON TFF.NUMERO_FINALIDADE = GPC.FINALIDADE
  LEFT JOIN (
      SELECT ENI.SEQUENCE, ENI.DESCRIPTION
        FROM SGTPRD.XX2_ENUMERATES ENU
        JOIN SGTPRD.XX2_ENUMITEM ENI ON ENI.IDENUMERATE = ENU.ID
       WHERE ENU.NAME LIKE 'TSTATUSPECAPRODUTO%'
  ) ENI ON ENI.SEQUENCE = GPP.STPECAPRODUTO
 WHERE GPP.DATA_DA_ENTRADA_PECA >= TO_NUMBER(TO_CHAR(SYSDATE - 60, 'YYYYMMDD'))
   AND GPP.CODIGO_REGISTRO = 1
   -- Semijoin: a peça precisa ter ordem de malha, mas várias linhas de ordem não a repetem.
   AND EXISTS (SELECT 1 FROM SGTPRD.GERAPECAORDEMMALHA GOM WHERE GOM.IDPECASPRODUTO = GPP.IDPECASPRODUTO)
   AND GPC.FINALIDADE NOT IN (1, 8)
 ORDER BY GPP.DATA_DA_ENTRADA_PECA DESC, GPP.IDPECASPRODUTO
