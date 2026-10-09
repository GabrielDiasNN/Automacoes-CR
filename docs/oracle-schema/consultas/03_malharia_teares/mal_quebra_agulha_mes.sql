/* =============================================================================
OBJETIVO: Quebra de agulha em teares internos por mês e máquina, com agulhas
          por evento para detectar mudança no padrão de registro
DOMÍNIO: 03_malharia_teares
TIPO: Auditoria/Sentinela
GRÃO: MES + MAQUINA (uma linha por mês e tear)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
TABELAS PRINCIPAIS: SGTPRD.QUEBRA_AGULHA_MALHAR, SGTPRD.MAQUINA,
  SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
COLUNAS:
  MES                 AAAAMM da data da quebra.
  MAQUINA             número curto do tear (sem zeros à esquerda).
  EVENTOS             registros de quebra no mês e na máquina.
  AGULHAS             soma de QUANTIDADE_AGULHAS.
  AGULHAS_POR_EVENTO  AGULHAS / EVENTOS. Mudança abrupta indica mudança de registro.
  RANK_AGULHAS_NO_MES posição da máquina no mês (1 = mais agulhas).
CUIDADOS OPERACIONAIS:
  - COD_AGULHA identifica a agulha (referência). Não foi decodificado aqui;
    usar apenas para comparar com o cadastro de agulhas.
  - Operador e turno não são confiáveis (valores padrão). COD_QUEBRA é constante
    (MLC39) em 2026. Não usar esses campos.
  - Em 2026 a média de agulhas por evento subiu e a quantidade de eventos caiu em relação
    a 2025 (valores e janela em REGRAS_NEGOCIO.md, seção 5.5). Comparar meses com cautela.
  - Escopo: teares internos (TIPO_MAQUINA 145/146 em unidade com EH_FACCAO = 'N').
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
QUEBRAS AS (
    SELECT SUBSTR(TO_CHAR(Q.DATA_QUEBRA), 1, 6) AS MES,
           Q.NUMERO_MAQUINA,
           COUNT(*)                          AS EVENTOS,
           SUM(Q.QUANTIDADE_AGULHAS)         AS AGULHAS
      FROM PARAM
      JOIN SGTPRD.QUEBRA_AGULHA_MALHAR Q
        ON Q.DATA_QUEBRA >= PARAM.D_INI
       AND Q.DATA_QUEBRA <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = Q.NUMERO_MAQUINA
     GROUP BY SUBSTR(TO_CHAR(Q.DATA_QUEBRA), 1, 6), Q.NUMERO_MAQUINA
)
SELECT QB.MES,
       LTRIM(QB.NUMERO_MAQUINA, '0')                                  AS MAQUINA,
       TRIM(M.GRUPO)                                                  AS GRUPO,
       TRIM(M.MODELO)                                                 AS MODELO,
       QB.EVENTOS,
       QB.AGULHAS,
       ROUND(QB.AGULHAS / NULLIF(QB.EVENTOS, 0), 1)                   AS AGULHAS_POR_EVENTO,
       RANK() OVER (PARTITION BY QB.MES ORDER BY QB.AGULHAS DESC)     AS RANK_AGULHAS_NO_MES
  FROM QUEBRAS QB
  JOIN SGTPRD.MAQUINA M
    ON M.NUMERO_MAQUINA = QB.NUMERO_MAQUINA
 ORDER BY QB.MES, RANK_AGULHAS_NO_MES, MAQUINA;
