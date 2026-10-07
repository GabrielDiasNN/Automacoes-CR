/* =============================================================================
OBJETIVO: OBs abertas aguardando receita no tingimento (sem receita ativa, receita bloqueada ou receita não emitida), com dias de espera e kg programado
DOMÍNIO: 01_beneficiamento_tingimento
TIPO: Monitoramento operacional
GRÃO: NUMERO_OB (uma linha por OB com a fase de tingimento pendente)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.CADASTRO_RECEITAS, SGTPRD.LIGA_CADREC_ITEMREC, SGTPRD.LABRECEITA_BLOQUEADA
CUIDADOS OPERACIONAIS: Somente leitura. Consolida em uma visão única o que hoje está espalhado em
  bnf_receitas_bloqueadas_por_ob.sql e bnf_receitas_pendentes_emissao_por_ob.sql (esta última só
  olha as 11 últimas OBs por número).
  Universo: OB.STATUS <> 0 e fase de tingimento (OB_FASES.CODIGO_FASE = 40) ainda não confirmada
  (STATUS <> 4). Nas OBs abertas hoje existe no máximo 1 sequência pendente por OB.
  SITUACAO_RECEITA, em ordem de precedência:
    SEM RECEITA ATIVA - nenhuma receita ativa (PROCESSO_ATIVO_PRODU = '1') casa com processo
                        industrial, cor, EP e processo específico da fase;
    BLOQUEADA         - a receita casada tem bloqueio (LABRECEITA_BLOQUEADA.BLOQUEIO_RECEITA = 0);
    NAO EMITIDA       - receita ok, mas a fase ainda está Programada (OB_FASES.STATUS = 0).
  Fases já Emitidas/Pesadas/Em execução (STATUS 1, 2, 3) não aparecem: a receita já saiu.
  Chave do casamento: processo industrial = CODIGO_FASE * 10 + TIPO_PROCESSO (40 * 10 + 1 = 401),
  cor = SUBSTR(CODCOR, 1, 11) = CODIGO_COR_DESENHO, EP e PE. Incluir PE é o que revela as OBs
  sem receita; sem ele todas casariam com exatamente uma receita.
  DIAS_DESDE_EMISSAO = SYSDATE - emissão da OB (OB.TEMPO_EMISSAO_OB, minutos desde 1996-01-01);
  NULL se a OB não tem data de emissão.
  KG_PROGRAMADO = OB_PRODUTO.KILOS_PROGRAMADOS: carga nominal do lote (valores redondos como 600,
  1000 e 1200 dominam), não peso real das peças; serve para dimensionar o gargalo, não para
  fechar peso.
============================================================================= */

WITH TINGIMENTO AS (
    SELECT /*+ MATERIALIZE */
           OBF.NUMERO_OB,
           OBF.STATUS                                  AS STATUS_FASE,
           OB.STATUS                                   AS STATUS_OB,
           OBF.CODIGO_FASE * 10 + OBF.TIPO_PROCESSO    AS PROCESSO_INDUSTRIAL,
           OBF.CODIGO_COR_DESENHO                      AS COR,
           OBF.ESPECIFICACAO_PRODUT                    AS EP,
           OBF.PROCESSO_ESPECIFICO                     AS PE,
           CASE WHEN OB.TEMPO_EMISSAO_OB > 0
                THEN SYSDATE - (DATE '1996-01-01' + OB.TEMPO_EMISSAO_OB / 1440)
           END                                         AS DIAS_DESDE_EMISSAO
      FROM SGTPRD.OB_FASES OBF
      JOIN SGTPRD.OB OB ON OB.NUMERO_OB = OBF.NUMERO_OB
     WHERE OB.STATUS <> 0
       AND OBF.CODIGO_FASE = 40
       AND OBF.STATUS <> 4
),
RECEITA AS (
    SELECT /*+ MATERIALIZE */
           CRE.PROCESSOINDUSTRIAL                      AS PROCESSO_INDUSTRIAL,
           SUBSTR(CRE.CODCOR, 1, 11)                   AS COR,
           CRE.ESPECIFICACAO_PRODUT                    AS EP,
           CRE.PROCESSO_ESPECIFICO                     AS PE,
           MIN(CRE.CODIGO_REDUZIDO_RECE)               AS CODIGO_REDUZIDO_RECE,
           MAX(CASE WHEN LRB.BLOQUEIO_RECEITA = 0 THEN 1 ELSE 0 END) AS BLOQUEADA
      FROM SGTPRD.CADASTRO_RECEITAS CRE
      LEFT JOIN SGTPRD.LIGA_CADREC_ITEMREC LCR
        ON LCR.CODIGO_REDUZIDO_RECE = CRE.CODIGO_REDUZIDO_RECE
      LEFT JOIN SGTPRD.LABRECEITA_BLOQUEADA LRB
        ON LRB.ID_LABRECEITA_BLOQ = LCR.ID_LABRECEITA_BLOQ
     WHERE CRE.PROCESSO_ATIVO_PRODU = '1'
       AND CRE.PROCESSOINDUSTRIAL IN (SELECT PROCESSO_INDUSTRIAL FROM TINGIMENTO)
     GROUP BY CRE.PROCESSOINDUSTRIAL,
              SUBSTR(CRE.CODCOR, 1, 11),
              CRE.ESPECIFICACAO_PRODUT,
              CRE.PROCESSO_ESPECIFICO
),
CLASSIFICADA AS (
    SELECT TIN.NUMERO_OB,
           TIN.STATUS_OB,
           TIN.STATUS_FASE,
           TIN.COR,
           TIN.EP,
           TIN.PE,
           REC.CODIGO_REDUZIDO_RECE,
           TIN.DIAS_DESDE_EMISSAO,
           CASE
               WHEN REC.PROCESSO_INDUSTRIAL IS NULL THEN 'SEM RECEITA ATIVA'
               WHEN REC.BLOQUEADA = 1               THEN 'BLOQUEADA'
               WHEN TIN.STATUS_FASE = 0             THEN 'NAO EMITIDA'
           END AS SITUACAO_RECEITA
      FROM TINGIMENTO TIN
      LEFT JOIN RECEITA REC
        ON REC.PROCESSO_INDUSTRIAL = TIN.PROCESSO_INDUSTRIAL
       AND REC.COR = TIN.COR
       AND REC.EP  = TIN.EP
       AND REC.PE  = TIN.PE
)
SELECT CLA.NUMERO_OB,
       CLA.SITUACAO_RECEITA,
       ROUND(CLA.DIAS_DESDE_EMISSAO, 1)                AS DIAS_DESDE_EMISSAO,
       CASE CLA.STATUS_OB
           WHEN 1 THEN 'EMITIDA'
           WHEN 3 THEN 'PROGRAMADA'
           WHEN 5 THEN 'INTERDITADA KANBAN'
           ELSE TO_CHAR(CLA.STATUS_OB)
       END                                             AS STATUS_OB,
       CLA.COR,
       CLA.EP,
       CLA.PE,
       CLA.CODIGO_REDUZIDO_RECE,
       ROUND(NVL(OBP.KILOS_PROGRAMADOS, 0), 1)         AS KG_PROGRAMADO
  FROM CLASSIFICADA CLA
  LEFT JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = CLA.NUMERO_OB
 WHERE CLA.SITUACAO_RECEITA IS NOT NULL
 ORDER BY CASE CLA.SITUACAO_RECEITA
              WHEN 'SEM RECEITA ATIVA' THEN 1
              WHEN 'BLOQUEADA'         THEN 2
              ELSE                          3
          END,
          CLA.DIAS_DESDE_EMISSAO DESC NULLS LAST,
          CLA.NUMERO_OB
