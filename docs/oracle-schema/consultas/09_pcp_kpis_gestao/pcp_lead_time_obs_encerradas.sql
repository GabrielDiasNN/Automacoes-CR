/* =============================================================================
OBJETIVO: Lead time das OBs encerradas nos últimos 90 dias por mês de encerramento, fluxo e tipo de ordem: média, mediana, P90, e divisão em espera até o primeiro início e tempo de processo
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Painel/KPI
GRÃO: MES_ENCERRAMENTO + CODIGO_FLUXO + TIPO_ORDEM
PARÂMETROS / BINDS: Nenhum (janela: OBs encerradas nos últimos 90 dias)
TABELAS PRINCIPAIS: SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO
CUIDADOS OPERACIONAIS: Somente leitura. Complementa as consultas de OB em aberto, que só medem
  a idade até agora.
  Universo: OB.STATUS = 0 (encerrada) com TEMPO_ENCERRAMENTO_O na janela, TEMPO_EMISSAO_OB > 0
  e encerramento posterior à emissão. Tempos OB.TEMPO_* são minutos desde 1996-01-01.
  DIAS_TOTAL = encerramento - emissão. DIAS_ESPERA = primeiro início confirmado de fase
  (menor OB_FASES.TEMPO_INICIAL_CONFIR > 0) - emissão. DIAS_PROCESSO = encerramento - primeiro
  início. Nas OBs encerradas de 90 dias, todas têm início de fase; 4 de 8.325 iniciaram antes
  da emissão (dado atípico, dias de espera levemente negativos, mantidos como estão).
  Medianas e P90 não se somam: P50_DIAS_TOTAL não é P50_ESPERA + P50_PROCESSO.
  TIPO_ORDEM 6 leva cerca do dobro do tempo das ordens tipo 0 (8 a 10 contra ~4 dias no
  período conferido). Não há descrição do tipo 6 neste acervo; trate como ordem de tipo
  diferente até a área confirmar (provável retrabalho).
  OB encerrada (STATUS = 0) pode incluir ordens canceladas sem produção; no período
  conferido todas têm peso em OB_PRODUTO.KILOS.
  KG = OB_PRODUTO.KILOS (1:1 com a OB).
============================================================================= */

WITH OBS AS (
    SELECT /*+ MATERIALIZE */
           OBE.NUMERO_OB,
           OBE.CODIGO_FLUXO,
           OBE.TIPO_ORDEM,
           OBE.TEMPO_EMISSAO_OB     AS T_EMISSAO,
           OBE.TEMPO_ENCERRAMENTO_O AS T_ENCERRAMENTO
      FROM SGTPRD.OB OBE
     WHERE OBE.STATUS = 0
       AND OBE.TEMPO_EMISSAO_OB > 0
       AND OBE.TEMPO_ENCERRAMENTO_O > OBE.TEMPO_EMISSAO_OB
       AND OBE.TEMPO_ENCERRAMENTO_O >= (TRUNC(SYSDATE) - 90 - DATE '1996-01-01') * 1440
       AND OBE.TEMPO_ENCERRAMENTO_O <  (TRUNC(SYSDATE) + 1 - DATE '1996-01-01') * 1440
),
PRIMEIRO_INICIO AS (
    SELECT OBF.NUMERO_OB,
           MIN(NULLIF(OBF.TEMPO_INICIAL_CONFIR, 0)) AS T_INICIO
      FROM SGTPRD.OB_FASES OBF
     WHERE OBF.NUMERO_OB IN (SELECT NUMERO_OB FROM OBS)
     GROUP BY OBF.NUMERO_OB
),
BASE AS (
    SELECT OBS.CODIGO_FLUXO,
           OBS.TIPO_ORDEM,
           TO_CHAR(DATE '1996-01-01' + OBS.T_ENCERRAMENTO / 1440, 'YYYY-MM') AS MES_ENCERRAMENTO,
           NVL(OBP.KILOS, 0)                                   AS KG,
           (OBS.T_ENCERRAMENTO - OBS.T_EMISSAO) / 1440         AS DIAS_TOTAL,
           (PRI.T_INICIO - OBS.T_EMISSAO) / 1440               AS DIAS_ESPERA,
           (OBS.T_ENCERRAMENTO - PRI.T_INICIO) / 1440          AS DIAS_PROCESSO
      FROM OBS
      LEFT JOIN PRIMEIRO_INICIO PRI ON PRI.NUMERO_OB = OBS.NUMERO_OB
      LEFT JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = OBS.NUMERO_OB
)
SELECT BAS.MES_ENCERRAMENTO,
       BAS.CODIGO_FLUXO,
       BAS.TIPO_ORDEM,
       COUNT(*)                                                        AS QT_OBS,
       ROUND(SUM(BAS.KG))                                              AS KG,
       ROUND(AVG(BAS.DIAS_TOTAL), 1)                                   AS MEDIA_DIAS_TOTAL,
       ROUND(MEDIAN(BAS.DIAS_TOTAL), 1)                                AS P50_DIAS_TOTAL,
       ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY BAS.DIAS_TOTAL), 1) AS P90_DIAS_TOTAL,
       ROUND(MAX(BAS.DIAS_TOTAL), 1)                                   AS MAX_DIAS_TOTAL,
       ROUND(MEDIAN(BAS.DIAS_ESPERA), 2)                               AS P50_DIAS_ESPERA,
       ROUND(MEDIAN(BAS.DIAS_PROCESSO), 2)                             AS P50_DIAS_PROCESSO
  FROM BASE BAS
 GROUP BY BAS.MES_ENCERRAMENTO, BAS.CODIGO_FLUXO, BAS.TIPO_ORDEM
 ORDER BY BAS.MES_ENCERRAMENTO DESC, QT_OBS DESC
