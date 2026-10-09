/* =============================================================================
OBJETIVO: Estoque de malha crua agrupado por número de agulhas do tear
DOMÍNIO: 03_malharia_teares
ARQUIVO ORIGINAL: (referência histórica; o arquivo de origem não existe mais no repositório; era a Query #3)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.GERAPECACOMPLPECA, SGTPRD.GERAPECACRU, SGTPRD.GERAPECASPRODUTO, SGTPRD.GRUPO_MAQUINAS, SGTPRD.ITENS_ESTOQUE, SGTPRD.MAQUINA, SGTPRD.TIPO_FINALIDADE_FIO
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
REVISÃO (08/10/2026): GRUPO_MAQUINAS é único por (SETOR, GRUPO), não por GRUPO. Sem o SETOR,
  o grupo 0G020 (setor 4 e setor 7) duplicava as peças: cada peça contava também no agulhas 0 (setor 7).
  Junção corrigida por (SETOR, GRUPO), uma linha por máquina.
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
  - Escopo desta consulta (depósito 95, reduzido 133, status 0/16/18; medido em 09/10/2026, 04:36): 53 peças, todas
    com status 0; 0 filhas de reagrupamento e 0 mães no escopo. Nenhuma dupla contagem nesta consulta.
  - Status 16 ou 18 no histórico do depósito 95 (CODIGO_REGISTRO = 1): zero peças (medido em 09/10/2026, 04:36).
    O status 18 não altera o resultado hoje. Se o depósito ou o reduzido mudar, reconferir.
  - Pendência de negócio (não é erro de contagem): confirmar se a reserva para romaneio de transferência tira a peça do estoque.
    Se tirar, o status 18 sai do filtro, do mesmo modo que o 13.
  - REGRA DO FILTRO DE FINALIDADE (conferida no Oracle em 09/10/2026): FINALIDADE IN (1, 8) = sem restrição, como em
    mal_necessidade_balanco_faltas_sobras.sql. Antes era FINALIDADE = 1; a troca não muda o resultado hoje (impacto abaixo).
  - FINALIDADE 8 é decisão de negócio em aberto (REGRAS_NEGOCIO.md, seção 5.11): o cadastro TIPO_FINALIDADE_FIO a
    descreve como "FIO C/ RESÍDUO". Esta consulta não tem janela de data.
  - Impacto medido no escopo desta consulta (depósito 95, reduzido 133, status 0/16/18): 53 peças com FINALIDADE = 1
    e 53 com IN (1, 8); zero peças FINALIDADE 8 (2 agulhas, saída idêntica). Se o cadastro ou a decisão mudar, reconferir.
============================================================================= */

WITH BASE AS (
    SELECT GPM.NUMERO_AGULHAS_CILIN AS AGULHAS_TEAR,
           GPP.IDPECASPRODUTO,
           LTRIM(GCR.NUMERO_MAQUINA, 0) AS TEAR
      FROM SGTPRD.GERAPECASPRODUTO GPP
      JOIN SGTPRD.GERAPECACOMPLPECA GPC
        ON GPP.IDPECASPRODUTO = GPC.IDPECASPRODUTO
      JOIN SGTPRD.GERAPECACRU GCR
        ON GPC.IDPECASPRODUTO = GCR.IDPECASPRODUTO
      JOIN SGTPRD.MAQUINA MQ
        ON MQ.NUMERO_MAQUINA = GCR.NUMERO_MAQUINA
      JOIN SGTPRD.GRUPO_MAQUINAS GPM
        ON GPM.SETOR = MQ.SETOR
       AND GPM.GRUPO = MQ.GRUPO
      JOIN SGTPRD.TIPO_FINALIDADE_FIO TFF
        ON GPC.FINALIDADE = TFF.NUMERO_FINALIDADE
      JOIN SGTPRD.ITENS_ESTOQUE ITE
        ON GPP.CODIGO_REDUZIDO_PROD = ITE.CODIGO_REDUZIDO
     WHERE GPP.CODIGO_REGISTRO = 1
       AND GPP.STPECAPRODUTO IN (0, 16, 18)
       AND GPP.IDPESSOAFJESTOQUE = 2
       AND GPP.PADRAO_QUALIDADE_SIN = 1
       AND GPP.CODIGO_DEPOSITO = 95
       AND GPC.FINALIDADE IN (1, 8)
       AND GPP.TIDOCUMENTOENTRADA <> 8
       AND ITE.CODIGO_REDUZIDO = 133
), TEARES AS (
    SELECT AGULHAS_TEAR,
           LISTAGG(TEAR, ', ') WITHIN GROUP (ORDER BY TEAR) AS TEAR
      FROM (SELECT DISTINCT AGULHAS_TEAR, TEAR FROM BASE)
     GROUP BY AGULHAS_TEAR
)
SELECT B.AGULHAS_TEAR,
       COUNT(B.IDPECASPRODUTO) AS PEAS,
       T.TEAR
  FROM BASE B
  JOIN TEARES T ON T.AGULHAS_TEAR = B.AGULHAS_TEAR
 GROUP BY B.AGULHAS_TEAR, T.TEAR
 ORDER BY B.AGULHAS_TEAR;
