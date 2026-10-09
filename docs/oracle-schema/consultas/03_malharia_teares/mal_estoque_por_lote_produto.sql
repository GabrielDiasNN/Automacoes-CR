/* =============================================================================
OBJETIVO: Estoque de malha crua agrupado por lote
DOMÍNIO: 03_malharia_teares
ARQUIVO ORIGINAL: (referência histórica; o arquivo de origem não existe mais no repositório; era a Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.GERAPECACOMPLPECA, SGTPRD.GERAPECACRU, SGTPRD.GERAPECASPRODUTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.TIPO_FINALIDADE_FIO
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
REGRA DO FILTRO DE STATUS (conferida no Oracle em 09/10/2026):
  - STPECAPRODUTO 0 = Normal (TISITUACAOESTOQUE 0); 16 = Alocada Inventário e 18 = Reserva p/ Romaneio Transfer
    (TISITUACAOESTOQUE 1, ou seja, peça ainda no estoque físico do depósito). Status 13 (Romaneio Saída) e 14 (Pedido Venda)
    ficam fora do filtro.
  - O status 18 inclui peças de reagrupamento: sem ordem de malha (GERAPECAORDEMMALHA) e com linhagem (GERAPECAORIGEM).
    A consulta não junta GERAPECAORDEMMALHA, então essas filhas entram no filtro se estiverem em status 0, 16 ou 18.
  - Dupla contagem só ocorre se a filha e a mãe estiverem no filtro ao mesmo tempo. Medido em 09/10/2026 (04:35), no
    depósito 95 com CODIGO_REGISTRO = 1, sem recorte de reduzido: 127 filhas sem ordem de malha e com linhagem, todas com
    status 4 (Utilizada), ou seja, fora do filtro. Elas têm 481 ligações (linhas de GERAPECAORIGEM) para 475 mães distintas:
    478 ligações (472 mães) para mães com status 4 e 3 ligações (3 mães) para mães com status 8. Nenhuma mãe tem status
    0, 16 ou 18. Logo hoje não há dupla contagem. Se esses números mudarem, reconferir.
  - Escopo desta consulta (depósito 95, reduzido 11852, status 0/16/18; medido em 09/10/2026, 04:36): 1.414 peças, todas
    com status 0; 0 filhas de reagrupamento e 0 mães no escopo. Nenhuma dupla contagem nesta consulta.
  - Status 16 ou 18 no histórico do depósito 95 (CODIGO_REGISTRO = 1): zero peças (medido em 09/10/2026, 04:36).
    O status 18 não altera o resultado hoje. Se o depósito ou o reduzido mudar, reconferir.
  - Pendência de negócio (não é erro de contagem): confirmar se a reserva para romaneio de transferência tira a peça do estoque.
    Se tirar, o status 18 sai do filtro, do mesmo modo que o 13.
  - REGRA DO FILTRO DE FINALIDADE (conferida no Oracle em 09/10/2026): FINALIDADE IN (1, 8) = sem restrição, como em
    mal_necessidade_balanco_faltas_sobras.sql. Antes era FINALIDADE = 1; a troca não muda o resultado hoje (impacto abaixo).
  - FINALIDADE 8 é decisão de negócio em aberto (REGRAS_NEGOCIO.md, seção 5.11): o cadastro TIPO_FINALIDADE_FIO a
    descreve como "FIO C/ RESÍDUO". Esta consulta não tem janela de data.
  - Impacto medido no escopo desta consulta (depósito 95, reduzido 11852, status 0/16/18): 1.414 peças com FINALIDADE = 1
    e 1.414 com IN (1, 8); zero peças FINALIDADE 8 (4 lotes, saída idêntica). Se o cadastro ou a decisão mudar, reconferir.
============================================================================= */

SELECT GPP.LOTE_PRODUTO LOTE,
       COUNT(GPP.IDPECASPRODUTO) PEAS
  FROM SGTPRD.GERAPECASPRODUTO GPP
 INNER JOIN SGTPRD.GERAPECACOMPLPECA GPC
    ON GPP.IDPECASPRODUTO = GPC.IDPECASPRODUTO
 INNER JOIN SGTPRD.GERAPECACRU GCR
    ON GPC.IDPECASPRODUTO = GCR.IDPECASPRODUTO
 INNER JOIN SGTPRD.TIPO_FINALIDADE_FIO TFF
    ON GPC.FINALIDADE = TFF.NUMERO_FINALIDADE
 INNER JOIN SGTPRD.ITENS_ESTOQUE ITE
    ON GPP.CODIGO_REDUZIDO_PROD = ITE.CODIGO_REDUZIDO
   AND GPP.CODIGO_REGISTRO = 1
   AND GPP.STPECAPRODUTO IN (0, 16, 18)
   AND GPP.IDPESSOAFJESTOQUE = 2
   AND GPP.PADRAO_QUALIDADE_SIN = 1
   AND GPP.CODIGO_DEPOSITO IN (95)
   AND GPC.FINALIDADE IN (1, 8)
   AND GPP.TIDOCUMENTOENTRADA <> 8
   AND ITE.CODIGO_REDUZIDO IN (11852)
 GROUP BY GPP.LOTE_PRODUTO
 ORDER BY GPP.LOTE_PRODUTO;
