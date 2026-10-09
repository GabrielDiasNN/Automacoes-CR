/* =============================================================================
OBJETIVO: Scorecard de teares internos (12 meses) - produção, meta, paradas,
          manutenção, paradas longas e quebra de agulha, uma linha por máquina
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: MAQUINA (uma linha por tear interno)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente
  (CTE PARAM). Para outra janela, ajuste somente a CTE PARAM.
TABELAS PRINCIPAIS: SGTPRD.GERAPECASPRODUTO, SGTPRD.GERAPECAORDEMMALHA,
  SGTPRD.ORDEM_PRODUCAO_MALHA, SGTPRD.TB_ESP_PROD_TEOR_MAL, SGTPRD.PARADAS_MAQUINA,
  SGTPRD.MOTIVOS_PARADAS, SGTPRD.QUEBRA_AGULHA_MALHAR, SGTPRD.MAQUINA,
  SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
COLUNAS:
  DIAS_PRODUCAO        dias distintos com pesagem (entrada de peça) da máquina na janela.
                       Nome histórico: a data é de pesagem, não de produção.
  KG_12M               kg produzidos (QTLIQUIDA das peças de malha).
  KG_DIA_ATIVO         KG_12M / DIAS_PRODUCAO (média nos dias com pesagem). Ritmo de máquina ativa.
  KG_META_12M          soma diária de KG_DIA_EFIC (uma linha por máquina/dia com KG_DIA_EFIC não nulo).
  KG_12M_COM_META      kg produzidos só nos dias com meta (KG_DIA_EFIC não nulo). Numerador de PCT_ATING_META.
  PCT_ATING_META       KG_12M_COM_META / KG_META_12M * 100 (NULL sem produção em dia com meta).
                       Meta em dias corridos: o SQL não filtra dia da semana nem dia com
                       pesagem, então dias sem pesagem (ex.: paradas coletivas) entram na meta.
                       Ler como ritmo na janela, não como percentual de dias úteis.
  MIN_PARADA_TOTAL     minutos de paradas do setor 4 (todos os motivos).
  MIN_MANUTENCAO       paradas MLC02, MLC03, MLC04, MLC22, MLC23, MLC25.
  MIN_ELETRICA         paradas MLC23 (defeito elétrico).
  MIN_FIO_PROCESSO     paradas de fio, processo e pano (ver CASE).
  MIN_OPERACIONAL      turno, reunião e intervalo (MLC05, MLC07, MLC09, MLC10, MLC21).
  EVT_PARADA_8H        paradas com duração acima de 480 min.
  AGULHAS_QUEBRADAS    soma de QUANTIDADE_AGULHAS na janela.
  RANK_KG_DIA_ATIVO    posição por ritmo (1 = maior kg por dia ativo).
ESCOPO: teares internos. Tear = MAQUINA.TIPO_MAQUINA 145 ou 146 em unidade
  com UNIDADE_FABRIL.EH_FACCAO = 'N' (CTE INTERNAS). Paradas: SETOR = 4.
CUIDADOS OPERACIONAIS:
  - Produção vem de GERAPECASPRODUTO.QTLIQUIDA (não de QUANTIDADE_CONFIRMAD).
  - Data de referência = DATA_DA_ENTRADA_PECA (YYYYMMDD numérico). É a data de PESAGEM,
    que pode ser posterior à produção. Kg de um dia não prova produção naquele dia;
    use a soma da janela.
  - Duração de parada = (DATA_TERMINO + HORA_TERMINO/1440) - (DATA_INICIO + HORA_INICIO/1440).
  - Operador, turno e lote de fio das paradas e das quebras não são confiáveis
    (valores padrão); não usar esses campos aqui.
  - Critério único de numerador e denominador do PCT_ATING_META: só máquina-dia com KG_DIA_EFIC
    não nulo (dia sem ficha fica fora dos dois lados, como mal_oee_aproximado_grupo.sql).
    Corrigido em 09/10/2026: antes o numerador somava toda a produção, inclusive a de dias sem
    linha de meta (e KG_DIA_EFIC nulo, se houvesse), o que inflava o percentual nas máquinas com
    cobertura parcial de meta.
  - Numerador (KG_12M_COM_META) sai da própria CTE PROD, por LEFT JOIN de PROD_DIA com META_DIA:
    PROD_DIA é referenciada uma só vez. Uma CTE separada para o numerador (PROD_COM_META) referenciava
    PROD_DIA de novo e, na janela de 12 meses, a execução caía por queda de sessão (~10 s).
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM
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
PROD_DIA AS (
    SELECT /*+ MATERIALIZE */ ORD.NUMERO_MAQUINA,
           TO_DATE(TO_CHAR(P.DATA_DA_ENTRADA_PECA), 'YYYYMMDD') AS DIA,
           SUM(P.QTLIQUIDA)                                      AS KG
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
     GROUP BY ORD.NUMERO_MAQUINA, P.DATA_DA_ENTRADA_PECA
),
META_DIA AS (
    SELECT T.NR_MAQUINA AS NUMERO_MAQUINA,
           TRUNC(T.DT_META) AS DIA,
           MAX(T.KG_DIA_EFIC) AS KG_DIA_EFIC
      FROM PARAM
      JOIN SGTPRD.TB_ESP_PROD_TEOR_MAL T
        ON T.DT_META >= TO_DATE(PARAM.D_INI, 'YYYYMMDD')
       AND T.DT_META <  TO_DATE(PARAM.D_FIM, 'YYYYMMDD')
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = T.NR_MAQUINA
     WHERE T.KG_DIA_EFIC IS NOT NULL  -- máquina-dia sem meta fica fora de numerador e denominador
     GROUP BY T.NR_MAQUINA, TRUNC(T.DT_META)
),
META AS (
    SELECT NUMERO_MAQUINA, ROUND(SUM(KG_DIA_EFIC), 0) AS KG_META_12M
      FROM META_DIA
     GROUP BY NUMERO_MAQUINA
),
PROD AS (
    SELECT PD.NUMERO_MAQUINA,
           COUNT(*)                                                    AS DIAS_PRODUCAO,
           ROUND(SUM(PD.KG), 0)                                        AS KG_12M,
           ROUND(SUM(CASE WHEN MD.DIA IS NOT NULL THEN PD.KG END), 0)  AS KG_12M_COM_META
      FROM PROD_DIA PD
      LEFT JOIN META_DIA MD
        ON MD.NUMERO_MAQUINA = PD.NUMERO_MAQUINA
       AND MD.DIA = PD.DIA
     GROUP BY PD.NUMERO_MAQUINA
),
PARADAS_DUR AS (
    SELECT PM.NUMERO_MAQUINA,
           PM.CODIGO_PARADA,
           GREATEST(0,
               ((TO_DATE(TO_CHAR(PM.DATA_TERMINO), 'YYYYMMDD') + PM.HORA_TERMINO / 1440)
              - (TO_DATE(TO_CHAR(PM.DATA_INICIO),  'YYYYMMDD') + PM.HORA_INICIO  / 1440)) * 1440
           ) AS MIN_PARADA
      FROM PARAM
      JOIN SGTPRD.PARADAS_MAQUINA PM
        ON PM.SETOR = 4
       AND PM.DATA_INICIO >= PARAM.D_INI
       AND PM.DATA_INICIO <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = PM.NUMERO_MAQUINA
     WHERE PM.DATA_TERMINO IS NOT NULL
),
PAR AS (
    SELECT NUMERO_MAQUINA,
           ROUND(SUM(MIN_PARADA), 0) AS MIN_PARADA_TOTAL,
           ROUND(SUM(CASE WHEN CODIGO_PARADA IN ('MLC02','MLC03','MLC04','MLC22','MLC23','MLC25')
                          THEN MIN_PARADA ELSE 0 END), 0) AS MIN_MANUTENCAO,
           ROUND(SUM(CASE WHEN CODIGO_PARADA = 'MLC23' THEN MIN_PARADA ELSE 0 END), 0) AS MIN_ELETRICA,
           ROUND(SUM(CASE WHEN CODIGO_PARADA IN ('MLC12','MLC19','MLC20','MLC26','MLC27','MLC28',
                                                 'MLC29','MLC30','MLC31','MLC32','MLC33','MLC34',
                                                 'MLC35','MLC36','MLC38','MLC39','MLC41')
                          THEN MIN_PARADA ELSE 0 END), 0) AS MIN_FIO_PROCESSO,
           ROUND(SUM(CASE WHEN CODIGO_PARADA IN ('MLC05','MLC07','MLC09','MLC10','MLC21')
                          THEN MIN_PARADA ELSE 0 END), 0) AS MIN_OPERACIONAL,
           SUM(CASE WHEN MIN_PARADA > 480 THEN 1 ELSE 0 END) AS EVT_PARADA_8H
      FROM PARADAS_DUR
     GROUP BY NUMERO_MAQUINA
),
QUEBRA AS (
    SELECT Q.NUMERO_MAQUINA,
           SUM(Q.QUANTIDADE_AGULHAS) AS AGULHAS_QUEBRADAS
      FROM PARAM
      JOIN SGTPRD.QUEBRA_AGULHA_MALHAR Q
        ON Q.DATA_QUEBRA >= PARAM.D_INI
       AND Q.DATA_QUEBRA <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = Q.NUMERO_MAQUINA
     GROUP BY Q.NUMERO_MAQUINA
),
BASE AS (
    SELECT M.NUMERO_MAQUINA,
           TRIM(M.GRUPO)      AS GRUPO,
           TRIM(M.FABRICANTE) AS FABRICANTE,
           TRIM(M.MODELO)     AS MODELO
      FROM SGTPRD.MAQUINA M
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = M.NUMERO_MAQUINA
)
SELECT LTRIM(B.NUMERO_MAQUINA, '0')                                        AS MAQUINA,
       B.GRUPO,
       B.FABRICANTE,
       B.MODELO,
       NVL(PR.DIAS_PRODUCAO, 0)                                            AS DIAS_PRODUCAO,
       NVL(PR.KG_12M, 0)                                                   AS KG_12M,
       ROUND(NVL(PR.KG_12M, 0) / NULLIF(PR.DIAS_PRODUCAO, 0), 0)           AS KG_DIA_ATIVO,
       NVL(ME.KG_META_12M, 0)                                              AS KG_META_12M,
       NVL(PR.KG_12M_COM_META, 0)                                          AS KG_12M_COM_META,
       ROUND(100 * PR.KG_12M_COM_META / NULLIF(ME.KG_META_12M, 0), 1)    AS PCT_ATING_META,
       NVL(PA.MIN_PARADA_TOTAL, 0)                                         AS MIN_PARADA_TOTAL,
       NVL(PA.MIN_MANUTENCAO, 0)                                           AS MIN_MANUTENCAO,
       NVL(PA.MIN_ELETRICA, 0)                                             AS MIN_ELETRICA,
       NVL(PA.MIN_FIO_PROCESSO, 0)                                         AS MIN_FIO_PROCESSO,
       NVL(PA.MIN_OPERACIONAL, 0)                                          AS MIN_OPERACIONAL,
       NVL(PA.EVT_PARADA_8H, 0)                                            AS EVT_PARADA_8H,
       NVL(QB.AGULHAS_QUEBRADAS, 0)                                        AS AGULHAS_QUEBRADAS,
       RANK() OVER (ORDER BY ROUND(NVL(PR.KG_12M, 0) / NULLIF(PR.DIAS_PRODUCAO, 0), 0) DESC NULLS LAST)
                                                                           AS RANK_KG_DIA_ATIVO
  FROM BASE B
  LEFT JOIN PROD   PR ON PR.NUMERO_MAQUINA = B.NUMERO_MAQUINA
  LEFT JOIN META   ME ON ME.NUMERO_MAQUINA = B.NUMERO_MAQUINA
  LEFT JOIN PAR    PA ON PA.NUMERO_MAQUINA = B.NUMERO_MAQUINA
  LEFT JOIN QUEBRA QB ON QB.NUMERO_MAQUINA = B.NUMERO_MAQUINA
 ORDER BY RANK_KG_DIA_ATIVO, MAQUINA;
