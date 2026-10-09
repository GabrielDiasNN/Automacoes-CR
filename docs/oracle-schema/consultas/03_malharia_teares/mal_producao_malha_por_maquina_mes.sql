/* =============================================================================
OBJETIVO: Produção de malha INTERNA por máquina e mês, com meta e paradas (visão gerencial)
ESCOPO: somente malharia interna. Tear (MAQUINA.TIPO_MAQUINA 145 circular ou 146
  retilíneo, conforme TIPOSMAQUINAS) cuja unidade fabril tem
  UNIDADE_FABRIL.EH_FACCAO = 'N' (CTE INTERNAS). Facções (grupos 0Txxx, máquinas
  TCTnn) ficam fora de produção, paradas e meta.
  PARADAS: mantido SETOR = 4. Paradas de teares retilíneos registradas no setor 7
  não entram.
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: MES + MAQUINA (uma linha por mês e tear interno)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente
  (CTE PARAM). Para outra janela, ajuste somente a CTE PARAM.
TABELAS PRINCIPAIS: SGTPRD.GERAPECASPRODUTO, SGTPRD.GERAPECAORDEMMALHA,
  SGTPRD.ORDEM_PRODUCAO_MALHA, SGTPRD.TB_ESP_PROD_TEOR_MAL, SGTPRD.PARADAS_MAQUINA,
  SGTPRD.MOTIVOS_PARADAS, SGTPRD.MAQUINA
COLUNAS:
  KG_PRODUZIDOS      soma de GERAPECASPRODUTO.QTLIQUIDA (kg) das peças de malha
                     com DATA_DA_ENTRADA_PECA no mês. Essa data é a da PESAGEM, que
                     pode ser posterior à produção: o mês é de pesagem (válido
                     em soma mensal; a fronteira entre meses pode deslocar peças).
  PECAS / ARTIGOS    peças distintas e artigos distintos no mês.
  KG_META_EFIC       soma diária de TB_ESP_PROD_TEOR_MAL.KG_DIA_EFIC (kg/dia com
                     eficiência prevista). Uma linha por máquina/dia (MAX).
  PCT_ATING_META_EFIC kg da máquina-dia COM meta / KG_META_EFIC * 100. Numerador e
                     denominador usam só máquina-dia com KG_DIA_EFIC não nulo (dia sem
                     ficha fica fora dos dois lados). NULL sem produção em dia com meta.
  KG_DIA_MEDIO       KG_PRODUZIDOS / dias do mês calendário.
  DIAS_COM_PRODUCAO  dias distintos com entrada de peça da máquina no mês.
  KG_DIA_COM_PRODUCAO KG_PRODUZIDOS / DIAS_COM_PRODUCAO. Use para comparar meses:
                     a meta conta dias corridos, inclusive a parada coletiva.
  MIN_PARADA         minutos de paradas do setor 4 (início no mês), todos os motivos.
  MIN_PARADA_EFIC    idem, só motivos com MOTIVOS_PARADAS.CALCULA_EFICIENCIA = '1'
                     (critério oficial de perda de eficiência).
  PCT_TEMPO_PARADO_CALENDARIO  MIN_PARADA / (dias do mês * 1440). Base calendário,
                     não horas programadas: não é disponibilidade oficial.
  RANK_KG_NO_MES     posição da máquina no mês por kg produzidos.
CUIDADOS OPERACIONAIS:
  - Produção NÃO sai de ORDEM_PRODUCAO_MALHA.QUANTIDADE_CONFIRMAD (zerado em
    todas as ordens) nem de PESOULTIMAPECAOPM (quase sempre nulo). O peso real vem
    de QTLIQUIDA das peças ligadas à ordem por GERAPECAORDEMMALHA.
  - QUANTIDADE_PROGRAMAD é kg programados da ordem, não entra nesta consulta.
  - MOVIMENTO_MAQUINA tem datas futuras (programação) e liga a poucas ordens de
    malha: não é fonte de produção realizada.
  - Peças com STPECAPRODUTO = 12 (estornadas) são excluídas.
  - Setor da malharia = 4 (tear circular). Teares retilíneos (setor 7) entram
    na produção via ordem de malha, mas as paradas consideram só o setor 4.
  - Parada coletiva de fim de ano: em dez/2025 não há peças de 22 a 31/12. A meta
    conta esses dias, então PCT_ATING_META_EFIC cai sem perda de desempenho. Compare
    meses por KG_DIA_COM_PRODUCAO.
  - Critério único de numerador e denominador do PCT_ATING_META_EFIC: só máquina-dia com
    KG_DIA_EFIC não nulo. Corrigido em 09/10/2026: antes o numerador somava toda a produção,
    inclusive a de máquina-dia sem linha de meta, e DIAS_COM_META contava linhas com KG nulo.
    Igual a mal_calendario_producao_diaria.sql e mal_scorecard_maquina_12m.sql.
    Medido em 09/10/2026 (janela de 12 meses, 1.069 linhas mês-máquina): 13 linhas mudam o
    PCT_ATING_META_EFIC (a maior: TC090 em 09/2026, de 405 para 313,1, com 360 kg de meta);
    nenhuma outra coluna muda, inclusive DIAS_COM_META.
  - As paradas registradas (PARADAS_MAQUINA, setor 4) somam ~2,4% do tempo
    calendário. Não explicam sozinhas a diferença para a meta.
  - Entre os motivos de maior tempo estão INÍCIO DE TURNO, LIMPEZA DE TETO e
    REUNIÃO (operacionais/planejadas). Separe-os dos técnicos (manutenção, defeito
    elétrico, pano caído) antes de concluir sobre causa.
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
/* Duas etapas: 1) agrega peças por mês, máquina, dia e artigo (sem COUNT DISTINCT
   sobre milhões de linhas); 2) conta artigos e dias distintos sobre esse conjunto
   bem menor. Cada peça aparece uma vez (IDPECASPRODUTO é único), então COUNT(*)
   é a contagem de peças. */
PRODUCAO_MAQ_DIA AS (
    SELECT SUBSTR(TO_CHAR(P.DATA_DA_ENTRADA_PECA), 1, 6) AS MES,
           ORD.NUMERO_MAQUINA,
           P.DATA_DA_ENTRADA_PECA                        AS DIA,
           P.CODIGO_REDUZIDO_PROD                        AS REDUZIDO,
           COUNT(*)                                      AS PECAS,
           SUM(P.QTLIQUIDA)                              AS KG
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
     GROUP BY SUBSTR(TO_CHAR(P.DATA_DA_ENTRADA_PECA), 1, 6), ORD.NUMERO_MAQUINA,
              P.DATA_DA_ENTRADA_PECA, P.CODIGO_REDUZIDO_PROD
),
PRODUCAO AS (
    SELECT MES,
           NUMERO_MAQUINA,
           SUM(PECAS)                          AS PECAS,
           COUNT(DISTINCT REDUZIDO)            AS ARTIGOS,
           COUNT(DISTINCT DIA)                 AS DIAS_COM_PRODUCAO,
           ROUND(SUM(KG), 0)                   AS KG_PRODUZIDOS
      FROM PRODUCAO_MAQ_DIA
     GROUP BY MES, NUMERO_MAQUINA
),
META_DIA AS (
    SELECT TO_CHAR(T.DT_META, 'YYYYMM')  AS MES,
           T.NR_MAQUINA                  AS NUMERO_MAQUINA,
           TRUNC(T.DT_META)              AS DIA,
           MAX(T.KG_DIA_EFIC)            AS KG_DIA_EFIC
      FROM PARAM
      JOIN SGTPRD.TB_ESP_PROD_TEOR_MAL T
        ON T.DT_META >= TO_DATE(PARAM.D_INI, 'YYYYMMDD')
       AND T.DT_META <  TO_DATE(PARAM.D_FIM, 'YYYYMMDD')
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = T.NR_MAQUINA
     WHERE T.KG_DIA_EFIC IS NOT NULL  -- máquina-dia sem meta fica fora de numerador e denominador
     GROUP BY TO_CHAR(T.DT_META, 'YYYYMM'), T.NR_MAQUINA, TRUNC(T.DT_META)
),
META AS (
    SELECT MES,
           NUMERO_MAQUINA,
           COUNT(*)                      AS DIAS_COM_META,
           ROUND(SUM(KG_DIA_EFIC), 0)    AS KG_META_EFIC
      FROM META_DIA
     GROUP BY MES, NUMERO_MAQUINA
),
PRODUCAO_COM_META AS (
    SELECT PM.MES,
           PM.NUMERO_MAQUINA,
           ROUND(SUM(PM.KG), 0)          AS KG_PRODUZIDOS_COM_META
      FROM PRODUCAO_MAQ_DIA PM
      JOIN META_DIA MD
        ON MD.MES = PM.MES
       AND MD.NUMERO_MAQUINA = PM.NUMERO_MAQUINA
       AND TO_NUMBER(TO_CHAR(MD.DIA, 'YYYYMMDD')) = PM.DIA
     GROUP BY PM.MES, PM.NUMERO_MAQUINA
),
PARADAS_DUR AS (
    SELECT PM.DATA_INICIO,
           PM.NUMERO_MAQUINA,
           PM.CODIGO_PARADA,
           PM.SETOR,
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
PARADAS AS (
    SELECT SUBSTR(TO_CHAR(PD.DATA_INICIO), 1, 6) AS MES,
           PD.NUMERO_MAQUINA,
           ROUND(SUM(PD.MIN_PARADA), 0)                                            AS MIN_PARADA,
           ROUND(SUM(CASE WHEN MP.CALCULA_EFICIENCIA = '1' THEN PD.MIN_PARADA END), 0) AS MIN_PARADA_EFIC
      FROM PARADAS_DUR PD
      LEFT JOIN SGTPRD.MOTIVOS_PARADAS MP
        ON MP.CODIGO_PARADA = PD.CODIGO_PARADA
       AND MP.SETOR         = PD.SETOR
     GROUP BY SUBSTR(TO_CHAR(PD.DATA_INICIO), 1, 6), PD.NUMERO_MAQUINA
),
CHAVES AS (
    SELECT MES, NUMERO_MAQUINA FROM PRODUCAO
    UNION
    SELECT MES, NUMERO_MAQUINA FROM META
    UNION
    SELECT MES, NUMERO_MAQUINA FROM PARADAS
)
SELECT C.MES,
       LTRIM(C.NUMERO_MAQUINA, '0')                                        AS MAQUINA,
       TRIM(MQ.GRUPO)                                                      AS GRUPO_MAQUINA,
       TRIM(MQ.FABRICANTE)                                                 AS FABRICANTE,
       TRIM(MQ.MODELO)                                                     AS MODELO,
       NVL(PR.PECAS, 0)                                                    AS PECAS,
       NVL(PR.ARTIGOS, 0)                                                  AS ARTIGOS,
       NVL(PR.KG_PRODUZIDOS, 0)                                            AS KG_PRODUZIDOS,
       NVL(ME.DIAS_COM_META, 0)                                            AS DIAS_COM_META,
       NVL(ME.KG_META_EFIC, 0)                                             AS KG_META_EFIC,
       ROUND(100 * PCC.KG_PRODUZIDOS_COM_META / NULLIF(ME.KG_META_EFIC, 0), 1) AS PCT_ATING_META_EFIC,
       ROUND(NVL(PR.KG_PRODUZIDOS, 0) / C.DIAS_MES, 0)                     AS KG_DIA_MEDIO,
       NVL(PR.DIAS_COM_PRODUCAO, 0)                                        AS DIAS_COM_PRODUCAO,
       ROUND(PR.KG_PRODUZIDOS / NULLIF(PR.DIAS_COM_PRODUCAO, 0), 0)        AS KG_DIA_COM_PRODUCAO,
       NVL(PA.MIN_PARADA, 0)                                               AS MIN_PARADA,
       NVL(PA.MIN_PARADA_EFIC, 0)                                          AS MIN_PARADA_EFIC,
       ROUND(100 * NVL(PA.MIN_PARADA, 0) / (C.DIAS_MES * 1440), 1)         AS PCT_TEMPO_PARADO_CALENDARIO,
       RANK() OVER (PARTITION BY C.MES ORDER BY NVL(PR.KG_PRODUZIDOS, 0) DESC) AS RANK_KG_NO_MES
  FROM (
        SELECT CH.MES,
               CH.NUMERO_MAQUINA,
               TO_NUMBER(TO_CHAR(LAST_DAY(TO_DATE(CH.MES, 'YYYYMM')), 'DD')) AS DIAS_MES
          FROM CHAVES CH
       ) C
  LEFT JOIN PRODUCAO PR ON PR.MES = C.MES AND PR.NUMERO_MAQUINA = C.NUMERO_MAQUINA
  LEFT JOIN META     ME ON ME.MES = C.MES AND ME.NUMERO_MAQUINA = C.NUMERO_MAQUINA
  LEFT JOIN PRODUCAO_COM_META PCC ON PCC.MES = C.MES AND PCC.NUMERO_MAQUINA = C.NUMERO_MAQUINA
  LEFT JOIN PARADAS  PA ON PA.MES = C.MES AND PA.NUMERO_MAQUINA = C.NUMERO_MAQUINA
  LEFT JOIN SGTPRD.MAQUINA MQ ON MQ.NUMERO_MAQUINA = C.NUMERO_MAQUINA
 ORDER BY C.MES, RANK_KG_NO_MES, MAQUINA;
