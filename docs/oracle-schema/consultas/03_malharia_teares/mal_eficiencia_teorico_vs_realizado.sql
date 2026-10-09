/* =============================================================================
OBJETIVO: Teórico (engenharia do reduzido) x realizado por produto e grupo de
          máquina. Aponta gaps entre o realizado e a eficiência prevista da ficha
          (FICHA_MALHA.PERCPRODUCAOPREVISTO) para investigação. NÃO DECISÓRIO (ver CUIDADOS).
DOMÍNIO: 03_malharia_teares
TIPO: Conferência pontual
GRÃO: REDUZIDO + GRUPO (um produto por grupo de máquinas)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
  Mínimo de dias para entrar: CTE PARAM (MIN_MAQ_DIAS = 30).
TABELAS PRINCIPAIS: SGTPRD.FICHA_MALHA, SGTPRD.FIOS_FICHA_MALHARIA_,
  SGTPRD.ITENS_COMPLEMENTO_FI, SGTPRD.GERAPECASPRODUTO, SGTPRD.GERAPECAORDEMMALHA,
  SGTPRD.ORDEM_PRODUCAO_MALHA, SGTPRD.PARADAS_MAQUINA, SGTPRD.MAQUINA,
  SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL, SGTPRD.ITENS_ESTOQUE
MÉTODO:
  TEORICO_KG_H_100  kg/hora a 100%, pela fórmula da engenharia de mal_oee_aproximado_grupo.sql,
                    sem a guarda 0,00001: soma por fio de 453,6/768,096 *
                    (AGULHAS * PONTOS_GRAMA_RAPORT)/100 * CONES / (TITULO * INDIESTITITULO)
                    * CABOS, multiplicada por RPM * 60 / 1000.
                    NÃO reproduz a meta de engenharia (KG_DIA_100 / 24): ver
                    REGRAS_NEGOCIO.md 5.3 e 5.7. Não usar como referência absoluta.
                    NULL explícito (09/10/2026):
                    Fibra com AGULHAS, PONTOS_GRAMA_RAPORT, CONES ou TITULO nulo ou <= 0 torna o teórico do produto NULL; RPM nulo ou <= 0 também.
                    Esse produto fica com SINAL FICHA_INCOMPLETA. INDIESTITITULO e CABOS NULL valem 1 (convenção herdada).
                    A guarda 0,00001 continua em mal_eficiencia_global_engenharia.sql,
                    mal_eficiencia_por_grupo_maquinas.sql e mal_eficiencia_ordens_em_aberto.sql
                    (herdada, não alterada). mal_oee_aproximado_grupo.sql usa a regra deste
                    arquivo desde 09/10/2026.
  TEORICO_KG_DIA    TEORICO_KG_H_100 * 24 (base de 24 h, igual à meta).
  Realizado         kg por máquina-dia, só em dias com UM único produto na máquina
                    (evita trocas de artigo no mesmo dia). ATENÇÃO: o dia é o da
                    PESAGEM (DATA_DA_ENTRADA_PECA), defasado em relação à produção.
                    O agregado do período é válido; o resultado por dia não é.
CAMPOS:
  EFIC_REAL_PCT       realizado / teórico do dia * 100, somado por produto e grupo.
  EFIC_PREV_PCT       PERCPRODUCAOPREVISTO da ficha (o que a meta usa).
  GAP_PTS             EFIC_REAL_PCT - EFIC_PREV_PCT (pontos percentuais).
  PCT_PARADA_GLOBAL   minutos de paradas do setor 4 / (teares do setor 4 x dias x 1440).
                      Parte do gap é parada real; o restante é ritmo (RPM, ficha).
  EFIC_REAL_AJ_PCT    EFIC_REAL_PCT / (1 - PCT_PARADA_GLOBAL). Indicador não validado
                      como percentual absoluto (REGRAS 5.7): só para comparar grupos.
  SINAL               REVISAR_PARA_BAIXO  realizado abaixo da previsão em 5 pts ou mais
                      (previsão otimista; revisar RPM/ficha antes de ajustar o %)
                      REVISAR_PARA_CIMA   realizado acima da previsão em 5 pts ou mais
                      (previsão conservadora ou ficha desatualizada)
                      EQUILIBRADO         diferença menor que 5 pts
                      AMOSTRA_PEQUENA     menos de 100 máquina-dias: não usar para decisão
                      FICHA_INCOMPLETA    teórico NULL ou zero, ou previsão NULL: não avaliado
CUIDADOS OPERACIONAIS:
  - NÃO DECISÓRIO: SINAL e EFIC_REAL_AJ_PCT comparam realizado/teórico como percentual
    absoluto, que não é validado (REGRAS_NEGOCIO.md 5.3 e 5.7). Use para comparar grupos
    e abrir investigação; não altere PERCPRODUCAOPREVISTO a partir desta consulta.
  - Não alterar o percentual sem revisar RPM e ficha do produto: o gap pode vir de
    velocidade real diferente do RPM cadastrado.
  - Dias com parada coletiva e domingos parciais reduzem o realizado; o teórico
    considera 24 h, igual à meta.
  - Escopo: teares internos 145/146 (EH_FACCAO = 'N'). A produção usa os dois setores;
    paradas e N_MAQUINAS (denominador de PCT_PARADA_GLOBAL) usam só SETOR = 4 (REGRAS 5.1).
  - Consulta de leitura. Execução somente leitura.
REVISÃO (08/10/2026), sem alteração de lógica:
  - O registro antigo "parse_ok_smoke_error" (cancelado, inconclusivo) não era custo da consulta. A causa foi
    queda de sessão de rede (ORA-00028 / DPY-4011). Execução medida: ~8,6 s, mediana de 6 execuções.
  - O custo está no bloco PRODUCAO_MAQ_DIA (GERAPECASPRODUTO por faixa de datas de pesagem).
  - A CTE TEO usa só FICHA_MALHA: produtos de FICHA_RETILINEA (14 linhas) ficam fora do COMPARADO (JOIN com TEO).
    Decisão de negócio pendente: incluir ou não a retilínea no teórico.
  - FICHA_MALHA tem PK (CODPROREDUZIDO, GRUPO); por isso MAX(PERCPRODUCAOPREVISTO) e MAX(RPM) não alteram o resultado.
REVISÃO (09/10/2026), com alteração de lógica:
  - TEO: NULL explícito por fibra e por produto (ver TEORICO_KG_H_100). Produto com ficha
    completa mantém o teórico de antes; muda só o produto com fibra incompleta ou com zero
    (AGULHAS, PONTOS, CONES, TITULO ou RPM).
  - N_MAQUINAS e paradas: só setor 4. Antes contava os teares do setor 7, que não têm parada
    registrada, e diluía PCT_PARADA_GLOBAL.
  - SINAL: FICHA_INCOMPLETA em vez de EQUILIBRADO quando faltam teórico ou previsão.
  - Cabeçalho: removida a conferência '75 de 85', que contradizia REGRAS_NEGOCIO.md 5.3.
  - Divisores de PCT_PARADA_GLOBAL e EFIC_REAL_AJ_PCT com NULLIF (regra 8 de consultas/README.md).
    Sem efeito nos resultados: N_MAQUINAS é maior que zero e a parada não chega a 100%.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM,
           TRUNC(SYSDATE, 'MM') - ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)          AS DIAS_JANELA,
           30                                                                    AS MIN_MAQ_DIAS,
           100                                                                   AS MIN_SINAL_DIAS
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
FIBRA_TEO AS (
    SELECT FMA.CODPROREDUZIDO AS REDUZIDO,
           FMA.GRUPO,
           FMA.PERCPRODUCAOPREVISTO,
           FMA.RPM,
           CASE WHEN FFI.AGULHAS > 0 AND FFI.PONTOS_GRAMA_RAPORT > 0 AND FFI.CONES > 0
                     AND ICF.TITULO_FIO_NE > 0
                THEN 453.6 / 768.096 * (FFI.AGULHAS * FFI.PONTOS_GRAMA_RAPORT) / 100
                     * FFI.CONES / (ICF.TITULO_FIO_NE
                     * DECODE(NVL(FFI.INDIESTITITULO, 0), 0, 1, FFI.INDIESTITITULO))
                     * DECODE(NVL(FFI.NUMERO_CABOS, 0), 0, 1, FFI.NUMERO_CABOS)
           END AS PARCELA
      FROM SGTPRD.FICHA_MALHA FMA
      LEFT JOIN SGTPRD.FIOS_FICHA_MALHARIA_ FFI
        ON FFI.GRUPO_MAQUINA = FMA.GRUPO
       AND FFI.CODIGO_PRODUTO = FMA.CODPROREDUZIDO
      LEFT JOIN SGTPRD.ITENS_COMPLEMENTO_FI ICF
        ON ICF.CODIGO_REDUZIDO = FFI.CODIGO_FIO
),
/* Parcela NULL (fibra com AGULHAS, PONTOS_GRAMA_RAPORT, CONES ou TITULO nulo ou <= 0, ou ficha
   sem fibra) deixa o produto com teórico NULL; RPM nulo ou <= 0 faz o mesmo. */
TEO AS (
    SELECT REDUZIDO,
           GRUPO,
           MAX(PERCPRODUCAOPREVISTO) AS EFIC_PREV_PCT,
           CASE WHEN COUNT(*) = COUNT(PARCELA) AND MAX(RPM) > 0
                THEN ROUND(SUM(PARCELA) * MAX(RPM) * 60 / 1000, 2)
           END AS TEORICO_KG_H_100
      FROM FIBRA_TEO
     GROUP BY REDUZIDO, GRUPO
),
PRODUCAO_MAQ_DIA AS (
    SELECT /*+ MATERIALIZE */ ORD.NUMERO_MAQUINA,
           P.DATA_DA_ENTRADA_PECA AS DIA,
           ORD.CODIGO_REDUZIDO_PROD AS REDUZIDO,
           SUM(P.QTLIQUIDA) AS KG
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
     GROUP BY ORD.NUMERO_MAQUINA, P.DATA_DA_ENTRADA_PECA, ORD.CODIGO_REDUZIDO_PROD
),
MAQ_DIA_UNICO AS (
    SELECT NUMERO_MAQUINA, DIA
      FROM PRODUCAO_MAQ_DIA
     GROUP BY NUMERO_MAQUINA, DIA
    HAVING COUNT(*) = 1
),
PARADA_MIN AS (
    SELECT SUM(GREATEST(0,
               ((TO_DATE(TO_CHAR(PM.DATA_TERMINO), 'YYYYMMDD') + PM.HORA_TERMINO / 1440)
              - (TO_DATE(TO_CHAR(PM.DATA_INICIO),  'YYYYMMDD') + PM.HORA_INICIO  / 1440)) * 1440)) AS MIN_TOTAL
      FROM PARAM
      JOIN SGTPRD.PARADAS_MAQUINA PM
        ON PM.SETOR = 4
       AND PM.DATA_INICIO >= PARAM.D_INI
       AND PM.DATA_INICIO <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = PM.NUMERO_MAQUINA
     WHERE PM.DATA_TERMINO IS NOT NULL
),
N_MAQUINAS AS (
    SELECT COUNT(*) AS N
      FROM SGTPRD.MAQUINA MQN
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = MQN.NUMERO_MAQUINA
     WHERE MQN.SETOR = 4
),
PARADA_GLOBAL AS (
    SELECT PMN.MIN_TOTAL / NULLIF(NM.N * PA.DIAS_JANELA * 1440, 0) AS PCT_PARADA_GLOBAL
      FROM PARADA_MIN PMN
      CROSS JOIN N_MAQUINAS NM
      CROSS JOIN PARAM PA
),
COMPARADO AS (
    SELECT PMD.REDUZIDO,
           M.GRUPO,
           COUNT(*)                                      AS MAQ_DIAS,
           SUM(PMD.KG)                                   AS KG_REAL,
           SUM(TEO.TEORICO_KG_H_100 * 24)                AS KG_TEORICO_DIA,
           MAX(TEO.EFIC_PREV_PCT)                        AS EFIC_PREV_PCT,
           MAX(TEO.TEORICO_KG_H_100)                     AS TEORICO_KG_H_100
      FROM PRODUCAO_MAQ_DIA PMD
      JOIN MAQ_DIA_UNICO U
        ON U.NUMERO_MAQUINA = PMD.NUMERO_MAQUINA
       AND U.DIA = PMD.DIA
      JOIN SGTPRD.MAQUINA M
        ON M.NUMERO_MAQUINA = PMD.NUMERO_MAQUINA
      JOIN TEO
        ON TEO.REDUZIDO = PMD.REDUZIDO
       AND TEO.GRUPO = M.GRUPO
     GROUP BY PMD.REDUZIDO, M.GRUPO
)
SELECT C.REDUZIDO,
       TRIM(IE.DESCRICAO)                                                     AS PRODUTO,
       C.GRUPO,
       C.MAQ_DIAS,
       ROUND(C.KG_REAL)                                                       AS KG_REAL,
       ROUND(C.KG_TEORICO_DIA)                                                AS KG_TEORICO_DIA,
       ROUND(C.TEORICO_KG_H_100, 2)                                           AS TEORICO_KG_H_100,
       ROUND(100 * C.KG_REAL / NULLIF(C.KG_TEORICO_DIA, 0), 1)                AS EFIC_REAL_PCT,
       C.EFIC_PREV_PCT,
       ROUND(100 * C.KG_REAL / NULLIF(C.KG_TEORICO_DIA, 0) - C.EFIC_PREV_PCT, 1) AS GAP_PTS,
       PG.PCT_PARADA_GLOBAL * 100                                             AS PCT_PARADA_GLOBAL,
       ROUND((100 * C.KG_REAL / NULLIF(C.KG_TEORICO_DIA, 0)) / NULLIF(1 - PG.PCT_PARADA_GLOBAL, 0), 1)
                                                                              AS EFIC_REAL_AJ_PCT,
       CASE
           WHEN C.MAQ_DIAS < PARAM.MIN_SINAL_DIAS THEN 'AMOSTRA_PEQUENA'
           WHEN NVL(C.KG_TEORICO_DIA, 0) = 0 OR C.EFIC_PREV_PCT IS NULL THEN 'FICHA_INCOMPLETA'
           WHEN 100 * C.KG_REAL / NULLIF(C.KG_TEORICO_DIA, 0) - C.EFIC_PREV_PCT <= -5 THEN 'REVISAR_PARA_BAIXO'
           WHEN 100 * C.KG_REAL / NULLIF(C.KG_TEORICO_DIA, 0) - C.EFIC_PREV_PCT >=  5 THEN 'REVISAR_PARA_CIMA'
           ELSE 'EQUILIBRADO'
       END                                                                    AS SINAL
  FROM COMPARADO C
  CROSS JOIN PARADA_GLOBAL PG
  LEFT JOIN SGTPRD.ITENS_ESTOQUE IE
    ON IE.CODIGO_REDUZIDO = C.REDUZIDO
 CROSS JOIN PARAM
 WHERE C.MAQ_DIAS >= PARAM.MIN_MAQ_DIAS
 ORDER BY C.MAQ_DIAS DESC, C.REDUZIDO, C.GRUPO;
