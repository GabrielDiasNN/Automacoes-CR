/* =============================================================================
OBJETIVO: Posição Acumulada de Estoque / Fluxo Diário (Entradas vs Acabamento)
          com Segregação por Fluxo (T - Tubular e R - Ramado) e Três Origens de Entrada:
          1. Malharia Própria (Tear Circular Próprio)
          2. Facção (Prestação de Serviço de Tecelagem para a Costa Rica)
          3. Clientes (Terceiros que enviam malha crua para beneficiamento)
DOMÍNIO: 05_estoque_armazenagem
ARQUIVO ORIGINAL: Comandos SQL - CR\Acumulado (ESTOQUE TOTAL).sql
TIPO: SELECT (Consulta Analítica / Operacional)
PARÂMETROS / PERÍODO:
  - Mês corrente até o dia anterior (último dia completo fechado):
    TRUNC(SYSDATE, 'MM') até TRUNC(SYSDATE) - 1.
TABELAS PRINCIPAIS: 
  - SGTPRD.BD_PRD_MOVPROD (Entrada de Malharia Crua Própria)
  - SGTPRD.GERAPECASPRODUTO (Entrada de Facção e Clientes)
  - SGTPRD.BD_BNF_PRODUCAO_FASE (Saída de Acabamento - Calandra ou Rama)
  - SGTPRD.GERAPECAORIGEMOB / SGTPRD.GERAPECADESTINOOB (Linhagem de OBs e Peças)
  - SGTPRD.ENGEITEMESTONIVELGE / SGTPRD.ENGEITEMESTONIVELGE9 (Nível Genérico T/R e Máscara Insumo)
  - SGTPRD.TABELA_DATAS (Calendário Fabril Contínuo)
CUIDADOS OPERACIONAIS & DIRETRIZES DE ENGENHARIA ORACLE:
  - Trava Anti-Duplicidade de Acabamento (Prevenção de Furo de Estoque):
      1. Primeira passada única por OB (RN_OB = 1 com PR.KILOS > 0 e ordenação segura
         NVL(PR.DATA_HORA_FIM, PR.DATA_FIM), PR.SEQUENCIA).
      2. Blindagem Trans-Mensal: Exclusão de OBs cuja primeira passada física de acabamento
         ocorreu antes do início do mês corrente (NOT EXISTS em BD_BNF_PRODUCAO_FASE prévio),
         impedindo que reprocessos na virada do mês sejam contados novamente como saída.
      3. Mapeamento de Linhagem (OB Mãe x OB Filha): Se as peças da OB atual (GERAPECAORIGEMOB)
         já passaram por acabamento em uma OB de origem anterior (GERAPECADESTINOOB), a OB filha
         NÃO é contabilizada como nova saída de rolo, evitando dupla contagem de malha reprocessada/desmembrada.
  - Segregação Blindada de Entradas:
      * Malharia Própria: BD_PRD_MOVPROD (TIPO_ITEM = 9, QUALIDADE = 1, MOVIMENTO = 37).
      * Facção: GERAPECASPRODUTO (TIDOCUMENTOENTRADA = 8 e Máscara 'MCP' ou 'MCR').
      * Clientes: GERAPECASPRODUTO (Máscara 'MCT' - Malha Crua Terceiros).
  - Semântica de Saldo Acumulado:
      * A métrica ACUMULADO representa o DELTA ACUMULADO DO MÊS (Entradas do Mês - Saídas do Mês).
        Para obter o saldo estático total em galpão, deve-se somar o Estoque Inicial fechado do mês anterior.
  - Execução sub-segundo garantida via filtros temporais indexados diretos e hint LEADING/MATERIALIZE.
============================================================================= */

WITH ENTRADA_MALHARIA AS (
    SELECT /*+ MATERIALIZE */
           PRD.PRODUCAO_DATA AS DATA_MOV,
           CASE WHEN TRIM(MAS.CDNIVELGENERICO) = 'T' THEN 'T' ELSE 'R' END AS FLUXO,
           SUM(PRD.QUANTIDADE_REAL) AS QTD_MALHARIA
      FROM SGTPRD.BD_PRD_MOVPROD PRD
      JOIN SGTPRD.ENGEITEMESTONIVELGE MAS ON MAS.CDREDUZIDO = PRD.REDUZIDO_ITEM
     WHERE PRD.NUM_TIPO_MOVIMENTO = 37
       AND PRD.TIPO_ITEM = 9
       AND PRD.QUALIDADE = 1
       AND PRD.PRODUCAO_DATA >= TRUNC(SYSDATE, 'MM')
       AND PRD.PRODUCAO_DATA <  TRUNC(SYSDATE)
     GROUP BY PRD.PRODUCAO_DATA,
              CASE WHEN TRIM(MAS.CDNIVELGENERICO) = 'T' THEN 'T' ELSE 'R' END
),
ENTRADA_TERCEIROS AS (
    SELECT /*+ MATERIALIZE INDEX(E GRPCPROD_INDIDATAENTRPECA) LEADING(E) */
           TO_DATE(TO_CHAR(E.DATA_DA_ENTRADA_PECA), 'YYYYMMDD') AS DATA_MOV,
           CASE WHEN TRIM(MAS.CDNIVELGENERICO) = 'T' THEN 'T' ELSE 'R' END AS FLUXO,
           SUM(CASE WHEN TRIM(MAS.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR') AND E.TIDOCUMENTOENTRADA = 8 THEN E.QTLIQUIDA ELSE 0 END) AS QTD_FACCAO,
           SUM(CASE WHEN TRIM(MAS.IDMASCARATIPOINSUMO) IN ('MCT') THEN E.QTLIQUIDA ELSE 0 END) AS QTD_CLIENTES
      FROM SGTPRD.GERAPECASPRODUTO E
      JOIN SGTPRD.ENGEITEMESTONIVELGE MAS ON E.CODIGO_REDUZIDO_PROD = MAS.CDREDUZIDO
     WHERE E.PADRAO_QUALIDADE_SIN = 1
       AND TRIM(MAS.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR', 'MCT')
       AND (
           (E.TIDOCUMENTOENTRADA = 8 AND TRIM(MAS.IDMASCARATIPOINSUMO) IN ('MCP', 'MCR'))
           OR (TRIM(MAS.IDMASCARATIPOINSUMO) IN ('MCT'))
       )
       AND E.DATA_DA_ENTRADA_PECA >= TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))
       AND E.DATA_DA_ENTRADA_PECA <  TO_NUMBER(TO_CHAR(TRUNC(SYSDATE), 'YYYYMMDD'))
     GROUP BY TO_DATE(TO_CHAR(E.DATA_DA_ENTRADA_PECA), 'YYYYMMDD'),
              CASE WHEN TRIM(MAS.CDNIVELGENERICO) = 'T' THEN 'T' ELSE 'R' END
),
SAIDA_BRUTA AS (
    SELECT /*+ MATERIALIZE */
           PR.DATA_FIM,
           PR.NUMERO_OB,
           PR.KILOS,
           CASE WHEN TRIM(MAS.CDNIVELGENERICO) = 'T' THEN 'T' ELSE 'R' END AS FLUXO,
           ROW_NUMBER() OVER (
               PARTITION BY PR.NUMERO_OB 
               ORDER BY NVL(PR.DATA_HORA_FIM, PR.DATA_FIM), PR.SEQUENCIA
           ) AS RN_OB
      FROM SGTPRD.BD_BNF_PRODUCAO_FASE PR
      JOIN SGTPRD.ENGEITEMESTONIVELGE9 MAS ON PR.CODPRO_REDUZIDO = MAS.CDREDUZIDO
     WHERE PR.TIPO_DESTINO IN (0, 1) -- 0: Produção Normal, 1: Reprocesso
       AND PR.PI_REC IN (701, 801, 1001, 1101)
       AND PR.KILOS > 0
       AND PR.DATA_FIM >= TRUNC(SYSDATE, 'MM')
       AND PR.DATA_FIM <  TRUNC(SYSDATE)
       -- Blindagem de virada de mês: exclui OBs cuja primeira passada de acabamento ocorreu no mês anterior
       AND NOT EXISTS (
           SELECT 1 
             FROM SGTPRD.BD_BNF_PRODUCAO_FASE ANT
            WHERE ANT.NUMERO_OB = PR.NUMERO_OB
              AND ANT.PI_REC IN (701, 801, 1001, 1101)
              AND ANT.KILOS > 0
              AND ANT.DATA_FIM < TRUNC(SYSDATE, 'MM')
       )
),
PRIMEIRA_PASSADA_OB AS (
    SELECT DATA_FIM, NUMERO_OB, KILOS, FLUXO, RN_OB
      FROM SAIDA_BRUTA
     WHERE RN_OB = 1
),
PARES_FILHA_MAE AS (
    -- Linhagem só das OBs do mês: peças da OB atual (origem) que têm destino em
    -- outra OB (mãe). Desempenho: antes o EXISTS abaixo era avaliado por par
    -- contra BD_BNF_PRODUCAO_FASE, que não tem índice por NUMERO_OB, e a consulta
    -- estourava a janela de rede; agora a checagem roda uma vez para o conjunto.
    SELECT /*+ MATERIALIZE */
           DISTINCT ori.numero_ob AS ob_filha,
           dest.numero_ob AS ob_mae
      FROM PRIMEIRA_PASSADA_OB p
      JOIN SGTPRD.GERAPECAORIGEMOB ori ON ori.numero_ob = p.numero_ob
      JOIN SGTPRD.GERAPECADESTINOOB dest ON dest.idpecasproduto = ori.idpecasproduto
     WHERE dest.numero_ob <> ori.numero_ob
),
MAES_ACABADAS AS (
    SELECT /*+ MATERIALIZE */
           DISTINCT m.numero_ob
      FROM SGTPRD.BD_BNF_PRODUCAO_FASE m
     WHERE m.PI_REC IN (701, 801, 1001, 1101)
       AND m.KILOS > 0
       AND m.numero_ob IN (SELECT ob_mae FROM PARES_FILHA_MAE)
),
OBS_FILHAS_COM_MAE_ACABADA AS (
    -- Mapeia linhagem: OBs filhas cujas peças já passaram em acabamento na OB mãe/origem
    SELECT DISTINCT pf.ob_filha
      FROM PARES_FILHA_MAE pf
      JOIN MAES_ACABADAS ma ON ma.numero_ob = pf.ob_mae
),
SAIDA_ACABAMENTO_AGG AS (
    SELECT p.DATA_FIM AS DATA_MOV,
           p.FLUXO,
           SUM(p.KILOS) AS QTD_ACABAMENTO
      FROM PRIMEIRA_PASSADA_OB p
      LEFT JOIN OBS_FILHAS_COM_MAE_ACABADA mae ON mae.ob_filha = p.NUMERO_OB
     WHERE mae.ob_filha IS NULL -- Exclui peças que já foram saída de acabamento na OB mãe
     GROUP BY p.DATA_FIM, p.FLUXO
),
CALENDARIO_FLUXO AS (
    SELECT DAT.DATA,
           DAT.DIA_SEM,
           F.FLUXO,
           F.ORDEM_FLUXO
      FROM SGTPRD.TABELA_DATAS DAT
      CROSS JOIN (
          SELECT 'T' AS FLUXO, 1 AS ORDEM_FLUXO FROM DUAL 
          UNION ALL 
          SELECT 'R', 2 FROM DUAL
      ) F
     WHERE DAT.DATA >= TRUNC(SYSDATE, 'MM')
       AND DAT.DATA <  TRUNC(SYSDATE)
)
SELECT CF.DATA AS DATA_PRODUCAO,
       CF.DIA_SEM AS DIA_SEMANA,
       CF.FLUXO,
       ROUND(NVL(EM.QTD_MALHARIA, 0), 2) AS TOTAL_MALHARIA,
       ROUND(NVL(ET.QTD_FACCAO, 0), 2)   AS TOTAL_FACCAO,
       ROUND(NVL(ET.QTD_CLIENTES, 0), 2) AS TOTAL_CLIENTES,
       ROUND(NVL(EM.QTD_MALHARIA, 0) + NVL(ET.QTD_FACCAO, 0) + NVL(ET.QTD_CLIENTES, 0), 2) AS TOTAL_ENTRADAS,
       ROUND(NVL(SA.QTD_ACABAMENTO, 0), 2) AS TOTAL_ACABAMENTO,
       ROUND(NVL(EM.QTD_MALHARIA, 0) + NVL(ET.QTD_FACCAO, 0) + NVL(ET.QTD_CLIENTES, 0) - NVL(SA.QTD_ACABAMENTO, 0), 2) AS DIFERENCA,
       ROUND(
           SUM(NVL(EM.QTD_MALHARIA, 0) + NVL(ET.QTD_FACCAO, 0) + NVL(ET.QTD_CLIENTES, 0) - NVL(SA.QTD_ACABAMENTO, 0))
           OVER(PARTITION BY CF.FLUXO ORDER BY CF.DATA ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
           2
       ) AS ACUMULADO
  FROM CALENDARIO_FLUXO CF
  LEFT JOIN ENTRADA_MALHARIA EM     ON EM.DATA_MOV = CF.DATA AND EM.FLUXO = CF.FLUXO
  LEFT JOIN ENTRADA_TERCEIROS ET    ON ET.DATA_MOV = CF.DATA AND ET.FLUXO = CF.FLUXO
  LEFT JOIN SAIDA_ACABAMENTO_AGG SA ON SA.DATA_MOV = CF.DATA AND SA.FLUXO = CF.FLUXO
 ORDER BY CF.DATA, CF.ORDEM_FLUXO
