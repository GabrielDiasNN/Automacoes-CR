/* =============================================================================
OBJETIVO: Calendário diário da malharia interna - máquinas com produção, kg
          produzidos e meta do dia. Separa dia sem pesagem (SEM_PRODUCAO) de queda
          de desempenho (dia com pesagem abaixo da meta). Não identifica parada
          coletiva: a consulta não cruza com paradas.
DOMÍNIO: 03_malharia_teares
TIPO: Monitoramento operacional
GRÃO: DIA (uma linha por dia do calendário da janela)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
TABELAS PRINCIPAIS: SGTPRD.GERAPECASPRODUTO, SGTPRD.GERAPECAORDEMMALHA,
  SGTPRD.ORDEM_PRODUCAO_MALHA, SGTPRD.TB_ESP_PROD_TEOR_MAL,
  SGTPRD.MAQUINA, SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
COLUNAS:
  DIA                 data do calendário. KG e máquinas são pela DATA DE PESAGEM
                      (DATA_DA_ENTRADA_PECA), que pode ser posterior à produção.
                      Use para ritmo de mês/semana, não para cruzar com paradas do dia.
  DIA_SEMANA          abreviação do dia da semana (DOM, SEG, ... SAB), sem depender de NLS.
  MAQ_COM_PRODUCAO    máquinas com entrada de peça no dia.
  KG_PRODUZIDOS       kg do dia (QTLIQUIDA).
  MAQ_COM_META        máquinas com meta no dia (KG_DIA_EFIC não nulo).
  MAQ_PROD_COM_META   máquinas com produção E com meta no dia (base de PRODUCAO_PARCIAL).
  KG_PRODUZIDOS_COM_META  kg do dia só das máquinas com meta (numerador de PCT_ATING_DIA).
  KG_META_DIA         soma, por máquina, do MAX(KG_DIA_EFIC) do dia (uma linha por máquina/dia,
                      como nos irmãos de produção e scorecard).
  PCT_ATING_DIA       KG_PRODUZIDOS_COM_META / KG_META_DIA * 100 (apenas dias com produção de
                      máquina com meta; NULL caso contrário).
  TIPO_DIA            SEM_PRODUCAO, PRODUCAO_PARCIAL (menos de 50% das máquinas com
                      meta produziram: MAQ_PROD_COM_META < 50% de MAQ_COM_META) ou
                      PRODUCAO_NORMAL.
CUIDADOS OPERACIONAIS:
  - A meta conta dias corridos (inclui fins de semana e paradas coletivas).
    Por isso PCT_ATING_DIA deve ser lido apenas nos dias com produção.
  - PRODUCAO_PARCIAL compara máquinas que produziram e têm meta no dia com as que têm meta
    (corrigido em 09/10/2026: antes comparava todas as produtivas, inclusive sem meta).
  - Critério único de numerador e denominador: só máquina-dia com KG_DIA_EFIC não nulo entra em
    KG_PRODUZIDOS_COM_META, KG_META_DIA, MAQ_COM_META e MAQ_PROD_COM_META. Igual a
    mal_oee_aproximado_grupo.sql (dia sem ficha fica fora dos dois lados). Corrigido em 09/10/2026:
    antes PCT_ATING_DIA somava a produção de todas as máquinas, inclusive a de máquina-dia sem
    linha de meta, e MAQ_COM_META contava linhas com KG nulo, se houvesse.
  - Escopo: teares internos 145/146 (EH_FACCAO = 'N').
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM,
           TO_DATE(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD'), 'YYYYMMDD') AS DT_INI,
           TRUNC(SYSDATE, 'MM')                                                  AS DT_FIM
      FROM DUAL
),
INTERNAS AS (
    SELECT DISTINCT MQI.NUMERO_MAQUINA
      FROM SGTPRD.MAQUINA MQI
      JOIN SGTPRD.GRUPO_MAQUINAS GMQ
        ON GMQ.GRUPO = MQI.GRUPO
       AND GMQ.SETOR = MQI.SETOR
      JOIN SGTPRD.UNIDADE_FABRIL UFM
        ON UFM.CODIGO_UNIDADE_FABRI = GMQ.UNIDADE_FABRIL
     WHERE MQI.TIPO_MAQUINA IN (145, 146)
       AND UFM.EH_FACCAO = 'N'
),
PRODUCAO AS (
    SELECT P.DATA_DA_ENTRADA_PECA AS DIA_NUM,
           ORD.NUMERO_MAQUINA,
           SUM(P.QTLIQUIDA)       AS KG
      FROM PARAM
      JOIN SGTPRD.GERAPECASPRODUTO P
        ON P.DATA_DA_ENTRADA_PECA >= PARAM.D_INI
       AND P.DATA_DA_ENTRADA_PECA <  PARAM.D_FIM
       AND P.STPECAPRODUTO <> 12
      JOIN SGTPRD.GERAPECAORDEMMALHA GM
        ON GM.IDPECASPRODUTO = P.IDPECASPRODUTO
      JOIN SGTPRD.ORDEM_PRODUCAO_MALHA ORD
        ON ORD.NUMERO_ORDEM = GM.NUMERO_ORDEM_MALHA
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = ORD.NUMERO_MAQUINA
     GROUP BY P.DATA_DA_ENTRADA_PECA, ORD.NUMERO_MAQUINA
),
PROD_DIA AS (
    SELECT DIA_NUM,
           COUNT(*)            AS MAQ_COM_PRODUCAO,
           ROUND(SUM(KG), 0)   AS KG_PRODUZIDOS
      FROM PRODUCAO
     GROUP BY DIA_NUM
),
META_MAQ_DIA AS (
    SELECT TO_NUMBER(TO_CHAR(TRUNC(T.DT_META), 'YYYYMMDD')) AS DIA_NUM,
           T.NR_MAQUINA                                     AS NUMERO_MAQUINA,
           MAX(T.KG_DIA_EFIC)                               AS KG_DIA_EFIC
      FROM PARAM
      JOIN SGTPRD.TB_ESP_PROD_TEOR_MAL T
        ON T.DT_META >= PARAM.DT_INI
       AND T.DT_META <  PARAM.DT_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = T.NR_MAQUINA
     WHERE T.KG_DIA_EFIC IS NOT NULL  -- máquina-dia sem meta fica fora de numerador e denominador
     GROUP BY TRUNC(T.DT_META), T.NR_MAQUINA
),
META_DIA AS (
    SELECT DIA_NUM,
           COUNT(*)                   AS MAQ_COM_META,
           ROUND(SUM(KG_DIA_EFIC), 0) AS KG_META_DIA
      FROM META_MAQ_DIA
     GROUP BY DIA_NUM
),
PROD_COM_META AS (
    SELECT P.DIA_NUM,
           COUNT(*)            AS MAQ_PROD_COM_META,
           ROUND(SUM(P.KG), 0) AS KG_PRODUZIDOS_COM_META
      FROM PRODUCAO P
      JOIN META_MAQ_DIA MM
        ON MM.DIA_NUM = P.DIA_NUM
       AND MM.NUMERO_MAQUINA = P.NUMERO_MAQUINA
     GROUP BY P.DIA_NUM
),
CALENDARIO AS (
    SELECT TO_NUMBER(TO_CHAR(PARAM.DT_INI + LEVEL - 1, 'YYYYMMDD')) AS DIA_NUM,
           PARAM.DT_INI + LEVEL - 1                                  AS DIA
      FROM PARAM
     CONNECT BY LEVEL <= PARAM.DT_FIM - PARAM.DT_INI
)
SELECT C.DIA,
       CASE MOD(TRUNC(C.DIA) - DATE '2000-01-02', 7)
           WHEN 0 THEN 'DOM' WHEN 1 THEN 'SEG' WHEN 2 THEN 'TER' WHEN 3 THEN 'QUA'
           WHEN 4 THEN 'QUI' WHEN 5 THEN 'SEX' ELSE 'SAB'
       END                                                           AS DIA_SEMANA,
       NVL(PD.MAQ_COM_PRODUCAO, 0)                                   AS MAQ_COM_PRODUCAO,
       NVL(PD.KG_PRODUZIDOS, 0)                                      AS KG_PRODUZIDOS,
       NVL(MD.MAQ_COM_META, 0)                                       AS MAQ_COM_META,
       NVL(PC.MAQ_PROD_COM_META, 0)                                  AS MAQ_PROD_COM_META,
       NVL(PC.KG_PRODUZIDOS_COM_META, 0)                             AS KG_PRODUZIDOS_COM_META,
       NVL(MD.KG_META_DIA, 0)                                        AS KG_META_DIA,
       ROUND(100 * PC.KG_PRODUZIDOS_COM_META / NULLIF(MD.KG_META_DIA, 0), 1) AS PCT_ATING_DIA,
       CASE
           WHEN NVL(PD.MAQ_COM_PRODUCAO, 0) = 0 THEN 'SEM_PRODUCAO'
           WHEN NVL(PC.MAQ_PROD_COM_META, 0) < 0.5 * NVL(MD.MAQ_COM_META, 0) THEN 'PRODUCAO_PARCIAL'
           ELSE 'PRODUCAO_NORMAL'
       END                                                           AS TIPO_DIA
  FROM CALENDARIO C
  LEFT JOIN PROD_DIA PD ON PD.DIA_NUM = C.DIA_NUM
  LEFT JOIN META_DIA MD ON MD.DIA_NUM = C.DIA_NUM
  LEFT JOIN PROD_COM_META PC ON PC.DIA_NUM = C.DIA_NUM
 WHERE C.DIA < TRUNC(SYSDATE, 'MM')
 ORDER BY C.DIA;
