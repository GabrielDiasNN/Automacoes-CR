/* =============================================================================
OBJETIVO: Monitoramento do Pulmão de Entrada das Ramas e Indicador de Autonomia em Horas
DOMÍNIO: 02_acabamento_preparacao
TIPO: Monitoramento operacional
GRÃO: RAMA + CODIGO_FASE + LOCALIZACAO_FISICA_WIP (uma linha por rama, fase de rama e localização do WIP)
PARÂMETROS / BINDS: Nenhum (busca dinamicamente ordens ativas pendentes nas ramas)
TABELAS PRINCIPAIS: SGTPRD.OB_FASES, SGTPRD.MAQUINA, SGTPRD.OB_PRODUTO, SGTPRD.BD_BNF_PRODUCAO_FASE
CUIDADOS OPERACIONAIS: Somente leitura. Segrega ordens fisicamente prontas no buffer da rama daquelas ainda em trânsito no tingimento ou abridor.
  Localização do WIP, decidida só pelo status das fases 40 (tingimento) e 90 (abridor); o fluxo real é
  tingimento, conferência de cor (45), etapas intermediárias (47, 50, 60, 65) e abridor, antes da rama
  (100 = ramar úmido, 110 = ramar seco). 1 = abridor concluído (ou OB sem abridor e com tingimento
  concluído): não há fase pendente entre o abridor e a rama; 2 = tingimento concluído ou dispensado (OB sem
  fase 40) e abridor pendente, o que inclui as etapas intermediárias, não só o abridor; 3 = tingimento
  pendente, seja na fila (não iniciado, a maioria) ou em execução, e também OB que ainda nem chegou ao
  tingimento; 4 = OB sem fase de tingimento nem de abridor, que não dá para localizar. A localização é
  aproximada: não diz em qual etapa a OB está, só qual marco ela já cumpriu. Autonomia = kg programados / ritmo líquido de referência da própria rama; o ritmo sai do
  histórico (apontamentos concluídos, STATUS = 0, dos últimos 60 dias, kg / horas de MIN_REAL) em vez de
  valores fixos, e aparece em RITMO_REFERENCIA_KG_H. Sem histórico a autonomia fica nula.
============================================================================= */

WITH FASES_RAMA_PENDENTES AS (
    SELECT /*+ MATERIALIZE */
        OBF.NUMERO_OB,
        OBF.CODIGO_FASE,
        OBF.STATUS,
        OBF.NUMERO_MAQUINA
    FROM SGTPRD.OB_FASES OBF
    JOIN SGTPRD.MAQUINA MAQ ON MAQ.NUMERO_MAQUINA = OBF.NUMERO_MAQUINA
    WHERE OBF.STATUS <> 4
      AND OBF.CODIGO_FASE IN (100, 110)
      AND MAQ.GRUPO = 'RM001'
      AND MAQ.SETOR = 5
),
STATUS_PROCESSO_ANTERIOR AS (
    SELECT /*+ MATERIALIZE */
        FO.NUMERO_OB,
        MAX(CASE WHEN OBF_ANT.CODIGO_FASE = 90 THEN 1 ELSE 0 END) AS TEM_ABRIDOR,
        MAX(CASE WHEN OBF_ANT.CODIGO_FASE = 90 AND OBF_ANT.STATUS = 4 THEN 1 ELSE 0 END) AS ABRIDOR_CONCLUIDO,
        MAX(CASE WHEN OBF_ANT.CODIGO_FASE = 40 THEN 1 ELSE 0 END) AS TEM_TINGIMENTO,
        MAX(CASE WHEN OBF_ANT.CODIGO_FASE = 40 AND OBF_ANT.STATUS = 4 THEN 1 ELSE 0 END) AS TINGIMENTO_CONCLUIDO
    FROM FASES_RAMA_PENDENTES FO
    JOIN SGTPRD.OB_FASES OBF_ANT ON OBF_ANT.NUMERO_OB = FO.NUMERO_OB
    GROUP BY FO.NUMERO_OB
),
RITMO_REFERENCIA AS (
    SELECT /*+ MATERIALIZE */
        PR.NUMERO_MAQUINA,
        SUM(PR.KILOS) / NULLIF(SUM(PR.MIN_REAL) / 60, 0) AS KG_HORA_LIQUIDA
    FROM SGTPRD.BD_BNF_PRODUCAO_FASE PR
    WHERE PR.NUMERO_MAQUINA IN (SELECT FP.NUMERO_MAQUINA FROM FASES_RAMA_PENDENTES FP)
      AND PR.STATUS = 0
      AND PR.KILOS > 0
      AND PR.MIN_REAL > 1
      AND PR.DATA_FIM >= TRUNC(SYSDATE) - 60
      AND PR.DATA_FIM <= TRUNC(SYSDATE)
    GROUP BY PR.NUMERO_MAQUINA
),
WIP_CLASSIFICADO AS (
    SELECT
        FO.NUMERO_OB,
        FO.NUMERO_MAQUINA,
        FO.CODIGO_FASE,
        CASE
            WHEN SPA.ABRIDOR_CONCLUIDO = 1
                 OR (SPA.TEM_ABRIDOR = 0 AND SPA.TINGIMENTO_CONCLUIDO = 1)
                THEN '1. BUFFER: ABRIDOR CONCLUÍDO (PRONTA PARA A RAMA)'
            WHEN SPA.TEM_ABRIDOR = 1
                 AND (SPA.TEM_TINGIMENTO = 0 OR SPA.TINGIMENTO_CONCLUIDO = 1)
                THEN '2. TINGIMENTO CONCLUÍDO OU DISPENSADO, ABRIDOR PENDENTE'
            WHEN SPA.TEM_TINGIMENTO = 1
                THEN '3. TINGIMENTO PENDENTE (FILA OU EM EXECUÇÃO)'
            ELSE '4. SEM FASE DE TINGIMENTO NEM DE ABRIDOR'
        END AS LOCALIZACAO_FISICA_WIP,
        NVL(OP.KILOS_PROGRAMADOS, 0) AS KG,
        NVL(OP.METROS_PROGRAMADOS, 0) AS METROS
    FROM FASES_RAMA_PENDENTES FO
    JOIN STATUS_PROCESSO_ANTERIOR SPA ON SPA.NUMERO_OB = FO.NUMERO_OB
    LEFT JOIN SGTPRD.OB_PRODUTO OP ON OP.NUMERO_OB = FO.NUMERO_OB
)
SELECT
    LTRIM(W.NUMERO_MAQUINA, '0') AS RAMA,
    W.CODIGO_FASE,
    W.LOCALIZACAO_FISICA_WIP,
    COUNT(DISTINCT W.NUMERO_OB) AS QTD_OBS,
    ROUND(SUM(W.KG), 1) AS TOTAL_KG,
    ROUND(SUM(W.METROS), 1) AS TOTAL_METROS,
    ROUND(MAX(RR.KG_HORA_LIQUIDA), 1) AS RITMO_REFERENCIA_KG_H,
    -- Autonomia em horas calculada contra o ritmo líquido histórico de cada rama
    ROUND(SUM(W.KG) / NULLIF(MAX(RR.KG_HORA_LIQUIDA), 0), 1) AS AUTONOMIA_HORAS
FROM WIP_CLASSIFICADO W
LEFT JOIN RITMO_REFERENCIA RR ON RR.NUMERO_MAQUINA = W.NUMERO_MAQUINA
GROUP BY
    W.NUMERO_MAQUINA,
    W.CODIGO_FASE,
    W.LOCALIZACAO_FISICA_WIP
ORDER BY RAMA, W.CODIGO_FASE, W.LOCALIZACAO_FISICA_WIP;
