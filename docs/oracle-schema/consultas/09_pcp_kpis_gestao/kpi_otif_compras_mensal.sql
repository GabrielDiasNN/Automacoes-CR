/* =============================================================================
OBJETIVO: OTIF de compras por mês de entrega programada (12 meses + mês aberto): no prazo e completo.
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Painel/KPI
GRANULARIDADE: uma linha por mês de entrega programada
FONTES: SGTPRD.ENTREGAS_PEDIDO_COMP (linha de entrega: data programada, quantidade pedida e recebida),
        SGTPRD.ITENS_NOTA_ENTRADA + SGTPRD.MESTRE_NOTA_ENTRADA (data de entrada da nota, pela chave PEDIDO + SEQUENCIA_PEDIDO).
REGRA: uma linha é avaliável quando tem nota de entrada vinculada.
  No prazo: a última entrada (DATA_DA_ENTRADA) é até a data programada (DATAENTREGA).
  Completa: QTDRECEBIDA >= QTDPEDIDA.
  OTIF: no prazo e completa.
FATOS CONFIRMADOS NO ORACLE (17/10/2026, pedidos de 01/01/2025 em diante):
  - 32.122 linhas de entrega. 31.034 com nota vinculada (96,6%).
  - 32.121 com data programada válida (entre 2020 e 2030). A linha com data inválida fica de fora.
  - A junção pela nota segue o mesmo caminho de VW_CR_PED_COMP.
LIMITES:
  - Linhas sem nota vinculada não são avaliáveis. Aparecem na coluna SEM_NOTA.
  - Data de entrada é a data da nota, não a data de chegada física. Validar com o recebimento.
  - Recebimento parcial conta como não completo, mesmo que a última entrada esteja no prazo.
PARÂMETROS / BINDS: nenhum (janela automática).
============================================================================= */
WITH JAN AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS DT_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS DT_ABERTO,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE) + 1, 'YYYYMMDD'))                    AS DT_FIM
      FROM DUAL
),
LIN AS (
    SELECT EPC.NUMERO,
           EPC.SEQUENCIADIGITACAO AS SEQ,
           EPC.DATAENTREGA,
           EPC.QTDPEDIDA,
           EPC.QTDRECEBIDA
      FROM SGTPRD.ENTREGAS_PEDIDO_COMP EPC
     CROSS JOIN JAN
     WHERE EPC.DATAENTREGA BETWEEN 20200101 AND 20301231
       AND EPC.DATAENTREGA >= JAN.DT_INI
       AND EPC.DATAENTREGA <  JAN.DT_FIM
),
ENT AS (
    SELECT TRIM(INE.PEDIDO)          AS PEDIDO,
           INE.SEQUENCIA_PEDIDO      AS SEQ,
           MAX(MNE.DATA_DA_ENTRADA)  AS ULT_ENTRADA
      FROM SGTPRD.ITENS_NOTA_ENTRADA INE
      JOIN SGTPRD.MESTRE_NOTA_ENTRADA MNE
        ON MNE.NUMERO_NOTA = INE.NUMERO_NOTA
       AND MNE.IDPESSOAFJ_CLIENTE = INE.IDPESSOAFJ
     WHERE INE.PEDIDO IS NOT NULL
     GROUP BY TRIM(INE.PEDIDO), INE.SEQUENCIA_PEDIDO
)
SELECT TO_CHAR(TO_DATE(L.DATAENTREGA, 'YYYYMMDD'), 'YYYY-MM')                                       AS MES_ENTREGA,
       CASE WHEN L.DATAENTREGA >= JAN.DT_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END                  AS STATUS_MES,
       COUNT(*)                                                                                       AS LINHAS,
       SUM(CASE WHEN E.ULT_ENTRADA IS NULL THEN 1 ELSE 0 END)                                         AS SEM_NOTA,
       SUM(CASE WHEN E.ULT_ENTRADA IS NOT NULL THEN 1 ELSE 0 END)                                     AS AVALIAVEIS,
       SUM(CASE WHEN E.ULT_ENTRADA IS NOT NULL AND L.QTDRECEBIDA >= L.QTDPEDIDA THEN 1 ELSE 0 END)    AS COMPLETAS,
       SUM(CASE WHEN E.ULT_ENTRADA IS NOT NULL AND E.ULT_ENTRADA <= L.DATAENTREGA THEN 1 ELSE 0 END)  AS NO_PRAZO,
       SUM(CASE WHEN E.ULT_ENTRADA IS NOT NULL AND E.ULT_ENTRADA <= L.DATAENTREGA
                 AND L.QTDRECEBIDA >= L.QTDPEDIDA THEN 1 ELSE 0 END)                                 AS OTIF,
       ROUND(100 * SUM(CASE WHEN E.ULT_ENTRADA IS NOT NULL AND E.ULT_ENTRADA <= L.DATAENTREGA
                 AND L.QTDRECEBIDA >= L.QTDPEDIDA THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN E.ULT_ENTRADA IS NOT NULL THEN 1 ELSE 0 END), 0), 2)              AS PERC_OTIF
  FROM LIN L
  LEFT JOIN ENT E
         ON E.PEDIDO = TRIM(TO_CHAR(L.NUMERO))
        AND E.SEQ = L.SEQ
 CROSS JOIN JAN
 GROUP BY TO_CHAR(TO_DATE(L.DATAENTREGA, 'YYYYMMDD'), 'YYYY-MM'),
          CASE WHEN L.DATAENTREGA >= JAN.DT_ABERTO THEN 'EM ABERTO' ELSE 'FECHADO' END
 ORDER BY 1
