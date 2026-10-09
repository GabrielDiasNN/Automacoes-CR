/* =============================================================================
OBJETIVO: Desempenho x Qualidade nos dias produtivos, por grupo de máquinas (12 meses),
          com disponibilidade e fração de dias produtivos como colunas informativas.
          NÃO é OEE completo: ver DEFINIÇÕES.
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: GRUPO (uma linha por grupo de máquinas)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
  HORAS_DIA = 24 (CTE PARAM), igual à base da meta.
TABELAS PRINCIPAIS: SGTPRD.GERAPECASPRODUTO, SGTPRD.GERAPECAORDEMMALHA,
  SGTPRD.ORDEM_PRODUCAO_MALHA, SGTPRD.FICHA_MALHA, SGTPRD.FIOS_FICHA_MALHARIA_,
  SGTPRD.ITENS_COMPLEMENTO_FI, SGTPRD.PARADAS_MAQUINA, SGTPRD.MAQUINA,
  SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
DEFINIÇÕES:
  A (Disponibilidade)  1 - horas paradas / (máquinas do setor 4 do grupo x dias x 24 h).
                       Informativa.
                       Paradas registradas não distinguem máquina parada de máquina sem
                       pedido, então A não é disponibilidade real.
  DIAS_PRODUTIVOS_PCT  máquina-dias com qualquer peça / (máquinas x dias da janela).
                       Informativa, pelo mesmo motivo de A.
  P (Desempenho)       kg realizado / kg teórico nos dias com um único produto por
                       máquina-dia (teórico = kg/h a 100% da ficha x 24 h). Produto conta
                       só com linha real (STPECAPRODUTO <> 12): estorno não faz um dia
                       parecer de dois produtos. Dias sem ficha para o produto ficam fora
                       do numerador e do denominador. Dias com teórico NULL (ver CUIDADOS)
                       também ficam fora.
  Q (Qualidade)        PROXY: 1 - kg estornados / kg total de malha. Refugo não está
                       no banco; estorno (STPECAPRODUTO = 12) é o único sinal disponível.
                       Validado em 08/10/2026: estorno = 0 kg nas peças de malha interna,
                       então Q = 100% em todas as linhas. Não é medição.
  DESEMPENHO_X_QUALIDADE_PCT  P x Q. É a única métrica de eficiência desta consulta.
  OEE completo         NÃO calculado. Exige horas programadas por máquina, que o banco
                       não entrega de forma confiável.
  Histórico (08/10/2026): duas versões anteriores foram descartadas. Na primeira, A se
                       cancelava na conta (P já era dividido por A). Na segunda, kg
                       realizados / kg planejados chegou a 110% num grupo, porque o teórico
                       planejado usava a média dos dias de produto único e o realizado
                       incluía todos os dias.
COLUNAS: GRUPO, MAQUINAS, A_PCT, DIAS_PRODUTIVOS_PCT, P_PCT, Q_PCT_PROXY,
  DESEMPENHO_X_QUALIDADE_PCT, KG_REAL, KG_ESTORNO, KG_TEORICO_DIA_PROD.
CUIDADOS OPERACIONAIS:
  - Q é proxy e vale 100%: não compare com OEE de fábricas que medem refugo.
  - Pesagem defasada: kg e dias pela data de pesagem. O agregado do período é válido.
  - P usa só máquina-dia com um produto (evita trocas no mesmo dia), como em
    mal_eficiencia_teorico_vs_realizado.sql.
  - A usa 24 h, confirmado por TABELA_PRD_TURNOS (T1 e T2 de 8 h 29 min e T3 de 6 h 59 min; os intervalos somam 23 h 57 min, com transições de 1 min arredondadas). Ver REGRAS_NEGOCIO.md, seção 5.1.
  - Escopo: teares internos 145/146 (EH_FACCAO = 'N'). A produção usa os dois setores
    (decisão pendente, REGRAS_NEGOCIO.md 5.11). Paradas e máquinas do denominador de A usam
    só SETOR = 4 (REGRAS 5.1): os 3 teares tipo 146 do setor 7 não têm parada registrada na
    janela e entrariam com 100% de disponibilidade falsa (corrigido em 09/10/2026).
  - Teórico NULL (ficha sem fibra ou com fibra inválida) não entra em P: o JOIN com TEO exige
    TEORICO_KG_H_100 IS NOT NULL, então numerador e denominador cobrem os mesmos dias. Regra
    igual à de mal_eficiencia_teorico_vs_realizado.sql (TEO), desde 09/10/2026:
    Fibra com AGULHAS, PONTOS_GRAMA_RAPORT, CONES ou TITULO nulo ou <= 0 torna o teórico do produto NULL; RPM nulo ou <= 0 também.
    Antes, TITULO NULL/0 virava divisor 0,00001 (teórico cerca de 100.000 vezes maior, P caía),
    a fibra incompleta tinha a parcela descartada pelo SUM (teórico menor, P subia) e zero em
    AGULHAS, PONTOS, CONES ou RPM gerava parcela 0 (teórico não nulo). Produtos com ficha
    completa mantêm o mesmo valor.
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM,
           TRUNC(SYSDATE, 'MM') - ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)          AS DIAS_JANELA,
           24                                                                    AS HORAS_DIA
      FROM DUAL
),
INTERNAS AS (
    SELECT DISTINCT MQI.NUMERO_MAQUINA, TRIM(MQI.GRUPO) AS GRUPO, MQI.SETOR
      FROM SGTPRD.MAQUINA MQI
      JOIN SGTPRD.GRUPO_MAQUINAS GMQ
        ON GMQ.GRUPO = MQI.GRUPO
       AND GMQ.SETOR = MQI.SETOR
      JOIN SGTPRD.UNIDADE_FABRIL UFM
        ON UFM.CODIGO_UNIDADE_FABRI = GMQ.UNIDADE_FABRIL
     WHERE MQI.TIPO_MAQUINA IN (145, 146)
       AND UFM.EH_FACCAO = 'N'
),
/* Uma parcela por fibra da ficha. Parcela NULL (fibra com AGULHAS, PONTOS_GRAMA_RAPORT, CONES ou
   TITULO nulo ou <= 0, ou ficha sem fibra) deixa o produto com teórico NULL; RPM nulo ou <= 0
   faz o mesmo. Mesma regra de mal_eficiencia_teorico_vs_realizado.sql (TEO). */
FIBRA_TEO AS (
    SELECT FMA.CODPROREDUZIDO AS REDUZIDO,
           FMA.GRUPO,
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
TEO AS (
    SELECT REDUZIDO,
           GRUPO,
           CASE WHEN COUNT(*) = COUNT(PARCELA) AND MAX(RPM) > 0
                THEN ROUND(SUM(PARCELA) * MAX(RPM) * 60 / 1000, 2)
           END AS TEORICO_KG_H_100
      FROM FIBRA_TEO
     GROUP BY REDUZIDO, GRUPO
),
PECAS AS (
    SELECT /*+ MATERIALIZE */ ORD.NUMERO_MAQUINA,
           P.DATA_DA_ENTRADA_PECA AS DIA,
           ORD.CODIGO_REDUZIDO_PROD AS REDUZIDO,
           SUM(CASE WHEN P.STPECAPRODUTO <> 12 THEN P.QTLIQUIDA ELSE 0 END) AS KG_REAL,
           SUM(CASE WHEN P.STPECAPRODUTO =  12 THEN P.QTLIQUIDA ELSE 0 END) AS KG_ESTORNO,
           SUM(CASE WHEN P.STPECAPRODUTO <> 12 THEN 1 ELSE 0 END)           AS LINHAS_REAIS
      FROM PARAM
      JOIN SGTPRD.GERAPECASPRODUTO P
        ON P.DATA_DA_ENTRADA_PECA >= PARAM.D_INI
       AND P.DATA_DA_ENTRADA_PECA <  PARAM.D_FIM
      JOIN SGTPRD.GERAPECAORDEMMALHA GM
        ON GM.IDPECASPRODUTO = P.IDPECASPRODUTO
      JOIN SGTPRD.ORDEM_PRODUCAO_MALHA ORD
        ON ORD.NUMERO_ORDEM = GM.NUMERO_ORDEM_MALHA
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = ORD.NUMERO_MAQUINA
     GROUP BY ORD.NUMERO_MAQUINA, P.DATA_DA_ENTRADA_PECA, ORD.CODIGO_REDUZIDO_PROD
),
/* Uma linha por máquina-dia (uma leitura de PECAS): dias com produção, produto único e kg.
   NRED e RED1 contam só produto com linha real (STPECAPRODUTO <> 12, como em
   mal_eficiencia_teorico_vs_realizado.sql). O estorno entra só em KG_ESTORNO (Q). O dia com
   só estorno continua contado em DIAS_GRUPO, como diz DEFINIÇÕES. */
DIA_MAQ AS (
    SELECT /*+ MATERIALIZE */ NUMERO_MAQUINA,
           DIA,
           COUNT(CASE WHEN LINHAS_REAIS > 0 THEN 1 END)      AS NRED,
           MIN(CASE WHEN LINHAS_REAIS > 0 THEN REDUZIDO END) AS RED1,
           SUM(KG_REAL)    AS KG_REAL,
           SUM(KG_ESTORNO) AS KG_ESTORNO
      FROM PECAS
     GROUP BY NUMERO_MAQUINA, DIA
),
TEO_DIA AS (
    SELECT I.GRUPO,
           SUM(T.TEORICO_KG_H_100 * PARAM.HORAS_DIA) AS KG_TEORICO_DIA,
           SUM(D.KG_REAL)                            AS KG_REAL_TEO
      FROM DIA_MAQ D
      JOIN INTERNAS I
        ON I.NUMERO_MAQUINA = D.NUMERO_MAQUINA
      JOIN TEO T
        ON T.REDUZIDO = D.RED1
       AND T.GRUPO = I.GRUPO
       AND T.TEORICO_KG_H_100 IS NOT NULL   -- teórico NULL fica fora de numerador e denominador
      CROSS JOIN PARAM
     WHERE D.NRED = 1
     GROUP BY I.GRUPO
),
PRODUCAO_GRUPO AS (
    SELECT I.GRUPO,
           SUM(D.KG_REAL)     AS KG_REAL,
           SUM(D.KG_ESTORNO)  AS KG_ESTORNO
      FROM DIA_MAQ D
      JOIN INTERNAS I
        ON I.NUMERO_MAQUINA = D.NUMERO_MAQUINA
     GROUP BY I.GRUPO
),
PARADAS_GRUPO AS (
    SELECT I.GRUPO,
           SUM(GREATEST(0,
               ((TO_DATE(TO_CHAR(PM.DATA_TERMINO), 'YYYYMMDD') + PM.HORA_TERMINO / 1440)
              - (TO_DATE(TO_CHAR(PM.DATA_INICIO),  'YYYYMMDD') + PM.HORA_INICIO  / 1440)) * 1440)) / 60 AS HORAS_PARADAS
      FROM PARAM
      JOIN SGTPRD.PARADAS_MAQUINA PM
        ON PM.SETOR = 4
       AND PM.DATA_INICIO >= PARAM.D_INI
       AND PM.DATA_INICIO <  PARAM.D_FIM
      JOIN INTERNAS I
        ON I.NUMERO_MAQUINA = PM.NUMERO_MAQUINA
       AND I.SETOR = 4
     WHERE PM.DATA_TERMINO IS NOT NULL
     GROUP BY I.GRUPO
),
MAQ_GRUPO AS (
    SELECT GRUPO, COUNT(DISTINCT NUMERO_MAQUINA) AS MAQUINAS
      FROM INTERNAS
     GROUP BY GRUPO
),
MAQ_SETOR4_GRUPO AS (
    SELECT GRUPO, COUNT(DISTINCT NUMERO_MAQUINA) AS MAQUINAS_SETOR4
      FROM INTERNAS
     WHERE SETOR = 4
     GROUP BY GRUPO
),
DIAS_GRUPO AS (
    SELECT I.GRUPO, COUNT(*) AS MAQ_DIAS_PRODUTIVOS
      FROM DIA_MAQ D
      JOIN INTERNAS I
        ON I.NUMERO_MAQUINA = D.NUMERO_MAQUINA
     GROUP BY I.GRUPO
),
BASE AS (
    SELECT MG.GRUPO,
           MG.MAQUINAS,
           (1 - NVL(PG.HORAS_PARADAS, 0) / NULLIF(MS.MAQUINAS_SETOR4 * P.DIAS_JANELA * P.HORAS_DIA, 0)) AS A_FRAC,
           NVL(DG.MAQ_DIAS_PRODUTIVOS, 0) / NULLIF(MG.MAQUINAS * P.DIAS_JANELA, 0)              AS DIAS_FRAC,
           TD.KG_REAL_TEO,
           TD.KG_TEORICO_DIA,
           PR.KG_REAL,
           PR.KG_ESTORNO
      FROM MAQ_GRUPO MG
      CROSS JOIN PARAM P
      LEFT JOIN PARADAS_GRUPO PG ON PG.GRUPO = MG.GRUPO
      LEFT JOIN PRODUCAO_GRUPO PR ON PR.GRUPO = MG.GRUPO
      LEFT JOIN TEO_DIA TD ON TD.GRUPO = MG.GRUPO
      LEFT JOIN DIAS_GRUPO DG ON DG.GRUPO = MG.GRUPO
      LEFT JOIN MAQ_SETOR4_GRUPO MS ON MS.GRUPO = MG.GRUPO
)
SELECT GRUPO,
       MAQUINAS,
       ROUND(100 * A_FRAC, 1)                                              AS A_PCT,
       ROUND(100 * DIAS_FRAC, 1)                                           AS DIAS_PRODUTIVOS_PCT,
       -- Desempenho nos dias com produção (um produto por máquina-dia), já em base de 24 h.
       ROUND(100 * KG_REAL_TEO / NULLIF(KG_TEORICO_DIA, 0), 1)             AS P_PCT,
       ROUND(100 * (1 - KG_ESTORNO / NULLIF(KG_REAL + KG_ESTORNO, 0)), 1)  AS Q_PCT_PROXY,
       -- Sem disponibilidade: ver DEFINIÇÕES (OEE completo exige horas programadas).
       ROUND(100 * (KG_REAL_TEO / NULLIF(KG_TEORICO_DIA, 0))
             * (1 - KG_ESTORNO / NULLIF(KG_REAL + KG_ESTORNO, 0)), 1)      AS DESEMPENHO_X_QUALIDADE_PCT,
       ROUND(KG_REAL)                                                      AS KG_REAL,
       ROUND(KG_ESTORNO)                                                   AS KG_ESTORNO,
       ROUND(KG_TEORICO_DIA)                                               AS KG_TEORICO_DIA_PROD
  FROM BASE
 ORDER BY DESEMPENHO_X_QUALIDADE_PCT DESC NULLS LAST, GRUPO;
