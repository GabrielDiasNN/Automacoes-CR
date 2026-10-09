/* =============================================================================
OBJETIVO: Eventos de parada longa (acima de 8 horas) em teares internos, nos
          últimos 12 meses, para priorizar reparo e verificar a causa
DOMÍNIO: 03_malharia_teares
TIPO: Monitoramento operacional
GRÃO: NUMERO_PARADA (uma linha por parada longa)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
  Limite de duração na CTE PARAM (LIMITE_MIN = 480).
TABELAS PRINCIPAIS: SGTPRD.PARADAS_MAQUINA, SGTPRD.MOTIVOS_PARADAS,
  SGTPRD.MAQUINA, SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL,
  SGTPRD.GERAPECAORDEMMALHA, SGTPRD.GERAPECASPRODUTO, SGTPRD.ORDEM_PRODUCAO_MALHA
COLUNAS:
  DIA_INICIO, DIA_FIM          início e fim do evento (data e hora).
  DURACAO_MIN                  minutos do evento.
  DURACAO_DIAS                 DURACAO_MIN / 1440.
  KG_NO_DIA_ANTERIOR           kg no dia anterior ao início (contexto, não é alerta).
  KG_NOS_DIAS_DO_FIM           kg no dia do fim e no seguinte (contexto, não é alerta).
  KG_DIAS_INTERNOS             kg com data de pesagem dentro da parada (exclui início
                               e fim). Não é prova de produção durante a parada.
  ALERTA_REGISTRO              PESAGEM_EM_PARADA quando há peso com data de pesagem em
                               dia inteiro dentro de parada de 1 dia ou mais. Esperado:
                               as peças são pesadas depois de produzidas (REGRAS_NEGOCIO.md,
                               seção 5.2). Só informativo.
  Paradas MLC02 (preventiva) somam muitos eventos longos e são planejadas: separá-las
  da análise de falha. Ver CODIGO_PARADA.
CUIDADOS OPERACIONAIS:
  - Parada registrada de vários dias não prova indisponibilidade real: o registro não
    distingue máquina parada de máquina sem pedido (REGRAS_NEGOCIO.md, 5.7). A produção
    aparece pela data de pesagem, defasada. Usar como lista de candidatos a investigar.
  - Causa: só CODIGO_PARADA está disponível. Ordens de manutenção não estão
    vinculadas (NUMERO_PARADA_MAQUIN = 0).
  - PRODUCAO_DIA lê pesagens a partir de 3 dias antes da janela (defasagem) e sem
    limite superior, para não cortar pesagens de paradas que terminam no mês corrente.
  - Escopo: teares internos (TIPO_MAQUINA 145/146 em unidade com EH_FACCAO = 'N').
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12) - 3, 'YYYYMMDD')) AS D_INI_PESAGEM,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM,
           480                                                                   AS LIMITE_MIN
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
EVENTOS AS (
    SELECT PM.NUMERO_PARADA,
           PM.NUMERO_MAQUINA,
           PM.CODIGO_PARADA,
           TO_DATE(TO_CHAR(PM.DATA_INICIO),  'YYYYMMDD') + PM.HORA_INICIO  / 1440 AS DIA_INICIO,
           TO_DATE(TO_CHAR(PM.DATA_TERMINO), 'YYYYMMDD') + PM.HORA_TERMINO / 1440 AS DIA_FIM,
           ROUND(GREATEST(0,
               ((TO_DATE(TO_CHAR(PM.DATA_TERMINO), 'YYYYMMDD') + PM.HORA_TERMINO / 1440)
              - (TO_DATE(TO_CHAR(PM.DATA_INICIO),  'YYYYMMDD') + PM.HORA_INICIO  / 1440)) * 1440
           ), 0) AS DURACAO_MIN
      FROM PARAM
      JOIN SGTPRD.PARADAS_MAQUINA PM
        ON PM.SETOR = 4
       AND PM.DATA_INICIO >= PARAM.D_INI
       AND PM.DATA_INICIO <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = PM.NUMERO_MAQUINA
     WHERE PM.DATA_TERMINO IS NOT NULL
),
LONGOS AS (
    SELECT E.*
      FROM EVENTOS E
      CROSS JOIN PARAM
     WHERE E.DURACAO_MIN > PARAM.LIMITE_MIN
),
PRODUCAO_DIA AS (
    SELECT ORD.NUMERO_MAQUINA,
           P.DATA_DA_ENTRADA_PECA AS DIA,
           ROUND(SUM(P.QTLIQUIDA), 0) AS KG
      FROM PARAM
      JOIN SGTPRD.GERAPECASPRODUTO P
        ON P.DATA_DA_ENTRADA_PECA >= PARAM.D_INI_PESAGEM
       AND P.STPECAPRODUTO <> 12
      JOIN SGTPRD.GERAPECAORDEMMALHA GM
        ON GM.IDPECASPRODUTO = P.IDPECASPRODUTO
      JOIN SGTPRD.ORDEM_PRODUCAO_MALHA ORD
        ON ORD.NUMERO_ORDEM = GM.NUMERO_ORDEM_MALHA
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = ORD.NUMERO_MAQUINA
     GROUP BY ORD.NUMERO_MAQUINA, P.DATA_DA_ENTRADA_PECA
)
SELECT LTRIM(L.NUMERO_MAQUINA, '0')                       AS MAQUINA,
       TRIM(M.GRUPO)                                      AS GRUPO,
       TRIM(M.MODELO)                                     AS MODELO,
       L.NUMERO_PARADA,
       L.CODIGO_PARADA,
       TRIM(MP.DESCRICAO)                                 AS DESCRICAO_PARADA,
       L.DIA_INICIO,
       L.DIA_FIM,
       L.DURACAO_MIN,
       ROUND(L.DURACAO_MIN / 1440, 1)                     AS DURACAO_DIAS,
       NVL((SELECT PD.KG
              FROM PRODUCAO_DIA PD
             WHERE PD.NUMERO_MAQUINA = L.NUMERO_MAQUINA
               AND PD.DIA = TO_NUMBER(TO_CHAR(TRUNC(L.DIA_INICIO) - 1, 'YYYYMMDD'))), 0)
                                                          AS KG_NO_DIA_ANTERIOR,
       NVL((SELECT SUM(PD.KG)
              FROM PRODUCAO_DIA PD
             WHERE PD.NUMERO_MAQUINA = L.NUMERO_MAQUINA
               AND PD.DIA IN (TO_NUMBER(TO_CHAR(TRUNC(L.DIA_FIM), 'YYYYMMDD')),
                              TO_NUMBER(TO_CHAR(TRUNC(L.DIA_FIM) + 1, 'YYYYMMDD')))), 0)
                                                          AS KG_NOS_DIAS_DO_FIM,
       NVL((SELECT SUM(PD.KG)
              FROM PRODUCAO_DIA PD
             WHERE PD.NUMERO_MAQUINA = L.NUMERO_MAQUINA
               AND PD.DIA >  TO_NUMBER(TO_CHAR(TRUNC(L.DIA_INICIO), 'YYYYMMDD'))
               AND PD.DIA <  TO_NUMBER(TO_CHAR(TRUNC(L.DIA_FIM), 'YYYYMMDD'))), 0)
                                                          AS KG_DIAS_INTERNOS,
       CASE WHEN L.DURACAO_MIN >= 1440
             AND NVL((SELECT SUM(PD.KG)
                        FROM PRODUCAO_DIA PD
                       WHERE PD.NUMERO_MAQUINA = L.NUMERO_MAQUINA
                         AND PD.DIA >  TO_NUMBER(TO_CHAR(TRUNC(L.DIA_INICIO), 'YYYYMMDD'))
                         AND PD.DIA <  TO_NUMBER(TO_CHAR(TRUNC(L.DIA_FIM), 'YYYYMMDD'))), 0) > 0
            THEN 'PESAGEM_EM_PARADA'
            ELSE 'OK'
       END                                                AS ALERTA_REGISTRO
  FROM LONGOS L
  JOIN SGTPRD.MAQUINA M
    ON M.NUMERO_MAQUINA = L.NUMERO_MAQUINA
  LEFT JOIN SGTPRD.MOTIVOS_PARADAS MP
    ON MP.CODIGO_PARADA = L.CODIGO_PARADA
   AND MP.SETOR = 4
 ORDER BY L.DURACAO_MIN DESC, MAQUINA;
