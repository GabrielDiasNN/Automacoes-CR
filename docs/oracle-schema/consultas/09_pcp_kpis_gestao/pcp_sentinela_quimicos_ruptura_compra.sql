/* =============================================================================
OBJETIVO: Sentinela de quimicos: estoque, consumo previsto, ruptura projetada e necessidade de compra por produto
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Auditoria/Sentinela
GRÃO: 1 linha por CD_REDUZIDO (produto quimico) no deposito de tinturaria (PARAMETROS.DEPOSITO).
      Entregas pendentes e receitas pendentes sao agregadas antes do join (sem
      multiplicacao de quantidades).
PARÂMETROS / BINDS: CTE PARAMETROS (valores literais; ajustar antes de executar).
TABELAS PRINCIPAIS: SGTPRD.VW_ESTO_SALDO, SGTPRD.AR_ESTOQUE_QUIMICO, SGTPRD.MOVTO_RECEITA, SGTPRD.ENTREGAS_PEDIDO_COMP, SGTPRD.ITENS_PEDIDO_COMPRA, SGTPRD.ITENS_ESTOQUE, SGTPRD.UNIDADE_MEDIDA
CUIDADOS OPERACIONAIS: Somente leitura. Regras de negocio em consultas/REGRAS_NEGOCIO.md (secao Quimicos). Mapeamento completo em docs/oracle-schema/quimicos/mapeamento_regras_consumo_quimicos.md.
FONTES (validadas em 17/10/2026):
  - VW_ESTO_SALDO            saldo fisico (QT_SALDO) e disponivel (QT_ESTOQUE_DISP) por deposito, kg
  - AR_ESTOQUE_QUIMICO       universo de quimicos do setor TINTURARIA (155 itens)
  - MOVTO_RECEITA            consumo real (QUANTIDADEPESADA, kg) e receitas emitidas nao pesadas (QUANTIDADE)
  - ENTREGAS_PEDIDO_COMP     entregas de pedidos de compra (QTDPEDIDA, QTDRECEBIDA, DATAENTREGA yyyymmdd)
  - ITENS_PEDIDO_COMPRA      liga item de compra ao insumo (CODINSREDUZIDO) e prazo (PRAZOENTREGA)
  - ITENS_ESTOQUE            descricao, unidade (IDUNIDADEMEDIDA -> UNIDADE_MEDIDA.DSSIGLA)

PARAMETROS (CTE PARAMETROS, literais): NAO SAO VALORES OPERACIONAIS APROVADOS.
  DEPOSITO         deposito do estoque de tinturaria (20 = deposito observado nos dados)
  JANELA_DIAS      janela do consumo historico real (analise, nao politica)
  HORIZONTE_DIAS   horizonte de receitas emitidas consideradas como previsto
  SEGURANCA_KG     estoque de seguranca em kg - PENDENTE, default 0
  COBERTURA_MIN_DIAS limiar de ALERTA - PENDENTE, default 0 (desabilitado)
  Enquanto SEGURANCA_KG e COBERTURA_MIN_DIAS estiverem em 0, a classificacao so usa
  ruptura antes da reposicao (CRITICO) e falta de dados (DADOS_INCOMPLETOS).

REGRAS:
  Consumo real      = SUM(QUANTIDADEPESADA) com MOVCONFIRMADO = 1 e STATUSPESAGEMRECEITA = 3
                      (pesagem confirmada), janela :JANELA_DIAS por DT_CONFIRMACAO.
  Previsto confirmado = SUM(QUANTIDADE) de receitas emitidas e confirmadas (MOVCONFIRMADO = 1)
                      ainda nao pesadas (STATUSPESAGEMRECEITA <> 3), emitidas nos ultimos
                      :HORIZONTE_DIAS. Nao e consumo confirmado: e a demanda ja emitida.
  Emitido nao confirmado = mesmo criterio com MOVCONFIRMADO = 0. Mostrado separado, NAO entra no saldo.
  Entrada futura    = QTDPEDIDA - QTDRECEBIDA (nunca negativo) de entregas com DATAENTREGA >= hoje.
  Entrada atrasada  = mesma conta com DATAENTREGA < hoje. Mostrada separada, NAO entra no saldo.
  Reservas: VW_ESTO_SALDO.QT_ESTOQUE_DISP e igual a QT_SALDO nos itens observados e
  QT_PED_ABERTO e zero - nao ha reserva descontada no saldo disponivel. Logo o previsto
  e descontado UMA vez, aqui.
  Prazo de reposicao = media de PRAZOENTREGA (dias) das linhas de compra do item. Sem prazo => DADOS_INCOMPLETOS.
  Consumo medio diario = consumo real / :JANELA_DIAS (media simples, sem sazonalidade).
  Data de ruptura   = hoje + (disponivel - previsto confirmado) / consumo medio diario
                      (ignora entradas futuras; ver coluna ENTRADA_FUTURA_KG para avaliar).
  Quantidade sugerida = max(0, consumo medio * prazo + :SEGURANCA_KG
                            + previsto confirmado - disponivel - entrada futura).
  Data-limite pedido = data de ruptura - prazo (se negativa, ja vencida = CRITICO).

ALERTAS:
  CRITICO          ruptura projetada antes de hoje + prazo, sem entrada futura cobrindo
  ALERTA           cobertura (dias) < :COBERTURA_MIN_DIAS (quando parametrizado) ou saldo
                   projetado < :SEGURANCA_KG
  NORMAL           demais casos com dados completos
  DADOS_INCOMPLETOS sem consumo historico, sem prazo de reposicao ou sem saldo
  PRAZO_PADRAO_DIAS e PENDENTE: PRAZOENTREGA e 0 em todas as linhas de compra.
============================================================================= */

WITH PARAMETROS AS (
    SELECT 20   AS DEPOSITO,
           90   AS JANELA_DIAS,
           30   AS HORIZONTE_DIAS,
           0    AS SEGURANCA_KG,
           0    AS COBERTURA_MIN_DIAS,
           CAST(NULL AS NUMBER) AS PRAZO_PADRAO_DIAS,  -- PENDENTE: prazo de reposicao real nao existe no banco (ver mapeamento)
           TRUNC(SYSDATE) AS HOJE
      FROM DUAL
),
UNIVERSO AS (
    -- Uniao: todo quimico do setor OU consumido na janela. Nenhum produto some em silencio.
    SELECT CD_REDUZIDO FROM SGTPRD.AR_ESTOQUE_QUIMICO
    UNION
    SELECT R.CODINSREDUZIDO
      FROM SGTPRD.MOVTO_RECEITA R, PARAMETROS P
     WHERE R.MOVCONFIRMADO = 1
       AND R.STATUSPESAGEMRECEITA = 3
       AND R.DT_CONFIRMACAO >= P.HOJE - P.JANELA_DIAS
),
SALDO AS (
    -- Saldo fisico e disponivel no deposito. Uma linha por produto (somando lotes/qualidades).
    SELECT S.CD_REDUZIDO,
           SUM(NVL(S.QT_SALDO, 0))        AS ESTOQUE_FISICO_KG,
           SUM(NVL(S.QT_ESTOQUE_DISP, 0)) AS ESTOQUE_DISPONIVEL_KG
      FROM SGTPRD.VW_ESTO_SALDO S, PARAMETROS P
     WHERE S.CODIGO_DEPOSITO = P.DEPOSITO
     GROUP BY S.CD_REDUZIDO
),
CONSUMO_REAL AS (
    SELECT R.CODINSREDUZIDO AS CD_REDUZIDO,
           SUM(R.QUANTIDADEPESADA)                       AS CONSUMO_REAL_KG,
           COUNT(DISTINCT R.NUMEROORDEM || '-' || R.SEQUENCIAFASEOB) AS QT_PARTIDAS,
           MAX(R.DT_CONFIRMACAO)                         AS ULTIMO_CONSUMO
      FROM SGTPRD.MOVTO_RECEITA R, PARAMETROS P
     WHERE R.MOVCONFIRMADO = 1
       AND R.STATUSPESAGEMRECEITA = 3
       AND R.DT_CONFIRMACAO >= P.HOJE - P.JANELA_DIAS
       AND R.DT_CONFIRMACAO <  P.HOJE + 1
     GROUP BY R.CODINSREDUZIDO
),
PREVISTO AS (
    -- Receitas emitidas, confirmadas e ainda nao pesadas (demanda ja emitida).
    -- Emitido nao confirmado e tratado em coluna propria e nao entra no saldo.
    SELECT R.CODINSREDUZIDO AS CD_REDUZIDO,
           SUM(CASE WHEN R.MOVCONFIRMADO = 1 AND R.STATUSPESAGEMRECEITA <> 3 THEN NVL(R.QUANTIDADE, 0) ELSE 0 END) AS PREVISTO_CONFIRMADO_KG,
           SUM(CASE WHEN R.MOVCONFIRMADO = 0 THEN NVL(R.QUANTIDADE, 0) ELSE 0 END)                                  AS EMITIDO_NAO_CONFIRMADO_KG
      FROM SGTPRD.MOVTO_RECEITA R, PARAMETROS P
     WHERE R.DT_EMISSAO >= P.HOJE - P.HORIZONTE_DIAS
       AND R.STATUSPESAGEMRECEITA <> 3
     GROUP BY R.CODINSREDUZIDO
),
COMPRA_ITEM AS (
    -- Prazo medio de reposicao por insumo (dias), a partir das linhas de pedido de compra.
    SELECT I.CODINSREDUZIDO AS CD_REDUZIDO,
           ROUND(AVG(CASE WHEN I.PRAZOENTREGA > 0 THEN I.PRAZOENTREGA END), 1) AS PRAZO_COMPRA_DIAS
      FROM SGTPRD.ITENS_PEDIDO_COMPRA I
     GROUP BY I.CODINSREDUZIDO
),
ENTREGA_PENDENTE AS (
    -- Quantidade ainda nao recebida, separada por futura (confirmada pela data) e atrasada.
    SELECT I.CODINSREDUZIDO AS CD_REDUZIDO,
           SUM(CASE WHEN TO_DATE(TO_CHAR(E.DATAENTREGA), 'YYYYMMDD') >= P.HOJE
                    THEN GREATEST(NVL(E.QTDPEDIDA, 0) - NVL(E.QTDRECEBIDA, 0), 0) ELSE 0 END) AS ENTRADA_FUTURA_KG,
           SUM(CASE WHEN TO_DATE(TO_CHAR(E.DATAENTREGA), 'YYYYMMDD') < P.HOJE
                    THEN GREATEST(NVL(E.QTDPEDIDA, 0) - NVL(E.QTDRECEBIDA, 0), 0) ELSE 0 END) AS ENTRADA_ATRASADA_KG,
           MIN(CASE WHEN TO_DATE(TO_CHAR(E.DATAENTREGA), 'YYYYMMDD') >= P.HOJE
                     AND NVL(E.QTDPEDIDA, 0) > NVL(E.QTDRECEBIDA, 0)
                    THEN TO_DATE(TO_CHAR(E.DATAENTREGA), 'YYYYMMDD') END) AS PROXIMA_ENTREGA
      FROM SGTPRD.ENTREGAS_PEDIDO_COMP E
      JOIN SGTPRD.ITENS_PEDIDO_COMPRA I ON I.ID = E.IDITENSPEDIDOCOMPRA
     CROSS JOIN PARAMETROS P
     WHERE NVL(E.QTDPEDIDA, 0) > NVL(E.QTDRECEBIDA, 0)
     GROUP BY I.CODINSREDUZIDO
),
BASE AS (
    SELECT U.CD_REDUZIDO,
           NVL(SAL.ESTOQUE_FISICO_KG, 0)           AS ESTOQUE_FISICO_KG,
           NVL(SAL.ESTOQUE_DISPONIVEL_KG, 0)       AS ESTOQUE_DISPONIVEL_KG,
           NVL(CR.CONSUMO_REAL_KG, 0)              AS CONSUMO_REAL_KG,
           NVL(CR.QT_PARTIDAS, 0)                  AS QT_PARTIDAS,
           CR.ULTIMO_CONSUMO,
           NVL(PR.PREVISTO_CONFIRMADO_KG, 0)       AS PREVISTO_CONFIRMADO_KG,
           NVL(PR.EMITIDO_NAO_CONFIRMADO_KG, 0)    AS EMITIDO_NAO_CONFIRMADO_KG,
           CI.PRAZO_COMPRA_DIAS,
           NVL(EP.ENTRADA_FUTURA_KG, 0)            AS ENTRADA_FUTURA_KG,
           NVL(EP.ENTRADA_ATRASADA_KG, 0)          AS ENTRADA_ATRASADA_KG,
           EP.PROXIMA_ENTREGA
      FROM UNIVERSO U
      LEFT JOIN SALDO SAL          ON SAL.CD_REDUZIDO = U.CD_REDUZIDO
      LEFT JOIN CONSUMO_REAL CR    ON CR.CD_REDUZIDO  = U.CD_REDUZIDO
      LEFT JOIN PREVISTO PR        ON PR.CD_REDUZIDO  = U.CD_REDUZIDO
      LEFT JOIN COMPRA_ITEM CI     ON CI.CD_REDUZIDO  = U.CD_REDUZIDO
      LEFT JOIN ENTREGA_PENDENTE EP ON EP.CD_REDUZIDO = U.CD_REDUZIDO
),
CALCULO AS (
    SELECT B.*,
           COALESCE(B.PRAZO_COMPRA_DIAS, P.PRAZO_PADRAO_DIAS)                  AS PRAZO_REPOSICAO_DIAS,
           ROUND(B.CONSUMO_REAL_KG / NULLIF(P.JANELA_DIAS, 0), 3)              AS CONSUMO_MEDIO_DIA_KG,
           P.HOJE                                                              AS DATA_REFERENCIA
      FROM BASE B CROSS JOIN PARAMETROS P
),
PROJECAO AS (
    SELECT C.*,
           CASE WHEN NVL(C.CONSUMO_MEDIO_DIA_KG, 0) > 0
                THEN ROUND((C.ESTOQUE_DISPONIVEL_KG - C.PREVISTO_CONFIRMADO_KG) / C.CONSUMO_MEDIO_DIA_KG, 1)
           END AS DIAS_COBERTURA,
           CASE WHEN NVL(C.CONSUMO_MEDIO_DIA_KG, 0) > 0
                THEN C.DATA_REFERENCIA + FLOOR((C.ESTOQUE_DISPONIVEL_KG - C.PREVISTO_CONFIRMADO_KG) / C.CONSUMO_MEDIO_DIA_KG)
           END AS DATA_RUPTURA_PROJETADA
      FROM CALCULO C
)
SELECT PJ.CD_REDUZIDO,
       ITE.DESCRICAO,
       UM.DSSIGLA                                              AS UNIDADE_ESTOQUE,
       PJ.ESTOQUE_FISICO_KG,
       PJ.ESTOQUE_DISPONIVEL_KG,
       PJ.PREVISTO_CONFIRMADO_KG,
       PJ.EMITIDO_NAO_CONFIRMADO_KG,
       PJ.CONSUMO_REAL_KG,
       PJ.QT_PARTIDAS,
       PJ.CONSUMO_MEDIO_DIA_KG,
       PJ.PRAZO_REPOSICAO_DIAS,
       PJ.ENTRADA_FUTURA_KG,
       PJ.ENTRADA_ATRASADA_KG,
       PJ.PROXIMA_ENTREGA,
       PJ.DIAS_COBERTURA,
       PJ.DATA_RUPTURA_PROJETADA,
       CASE WHEN PJ.PRAZO_REPOSICAO_DIAS IS NOT NULL
            THEN PJ.DATA_RUPTURA_PROJETADA - CEIL(PJ.PRAZO_REPOSICAO_DIAS)
       END                                                     AS DATA_LIMITE_PEDIDO,
       CASE WHEN PJ.CONSUMO_MEDIO_DIA_KG IS NULL OR PJ.PRAZO_REPOSICAO_DIAS IS NULL
            THEN NULL
            ELSE ROUND(GREATEST(PJ.CONSUMO_MEDIO_DIA_KG * PJ.PRAZO_REPOSICAO_DIAS
                                + P.SEGURANCA_KG + PJ.PREVISTO_CONFIRMADO_KG
                                - PJ.ESTOQUE_DISPONIVEL_KG - PJ.ENTRADA_FUTURA_KG, 0), 1)
       END                                                     AS QTD_SUGERIDA_COMPRA_KG,
       CASE
           -- Saldo disponivel nao cobre a demanda ja emitida e nao ha entrada futura: ruptura certa,
           -- independe de haver prazo cadastrado.
           WHEN PJ.CONSUMO_MEDIO_DIA_KG > 0
                AND PJ.ESTOQUE_DISPONIVEL_KG - PJ.PREVISTO_CONFIRMADO_KG <= 0
                AND PJ.ENTRADA_FUTURA_KG = 0
                THEN 'CRITICO'
           WHEN PJ.CONSUMO_MEDIO_DIA_KG IS NULL OR PJ.PRAZO_REPOSICAO_DIAS IS NULL
                THEN 'DADOS_INCOMPLETOS'
           WHEN PJ.DATA_RUPTURA_PROJETADA - CEIL(PJ.PRAZO_REPOSICAO_DIAS) < P.HOJE
                AND PJ.ENTRADA_FUTURA_KG = 0
                THEN 'CRITICO'
           WHEN PJ.DATA_RUPTURA_PROJETADA - CEIL(PJ.PRAZO_REPOSICAO_DIAS) < P.HOJE
                THEN 'ALERTA'
           WHEN PJ.DIAS_COBERTURA < P.COBERTURA_MIN_DIAS
                THEN 'ALERTA'
           WHEN PJ.ESTOQUE_DISPONIVEL_KG - PJ.PREVISTO_CONFIRMADO_KG < P.SEGURANCA_KG
                THEN 'ALERTA'
           ELSE 'NORMAL'
       END                                                     AS SITUACAO_ALERTA,
       CASE
           WHEN PJ.CONSUMO_MEDIO_DIA_KG IS NULL OR PJ.CONSUMO_MEDIO_DIA_KG = 0 THEN 'Sem consumo real na janela: sem base de previsao'
           WHEN PJ.PRAZO_REPOSICAO_DIAS IS NULL THEN 'Sem prazo de reposicao cadastrado em compras'
           WHEN PJ.ENTRADA_ATRASADA_KG > 0      THEN 'Entrega atrasada pendente: validar com compras'
           ELSE 'Dados suficientes'
       END                                                     AS OBSERVACAO_DADOS
  FROM PROJECAO PJ
  CROSS JOIN PARAMETROS P
  LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = PJ.CD_REDUZIDO
  LEFT JOIN SGTPRD.UNIDADE_MEDIDA UM ON UM.IDUNIDADEMEDIDA = ITE.IDUNIDADEMEDIDA
 ORDER BY CASE
              WHEN PJ.CONSUMO_MEDIO_DIA_KG > 0 AND PJ.ESTOQUE_DISPONIVEL_KG - PJ.PREVISTO_CONFIRMADO_KG <= 0 AND PJ.ENTRADA_FUTURA_KG = 0 THEN 1
              WHEN PJ.CONSUMO_MEDIO_DIA_KG IS NULL OR PJ.PRAZO_REPOSICAO_DIAS IS NULL THEN 4
              WHEN PJ.DATA_RUPTURA_PROJETADA - CEIL(PJ.PRAZO_REPOSICAO_DIAS) < P.HOJE AND PJ.ENTRADA_FUTURA_KG = 0 THEN 1
              WHEN PJ.DATA_RUPTURA_PROJETADA - CEIL(PJ.PRAZO_REPOSICAO_DIAS) < P.HOJE THEN 2
              ELSE 3
          END,
          PJ.DIAS_COBERTURA NULLS LAST,
          PJ.CD_REDUZIDO
