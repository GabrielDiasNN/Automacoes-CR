/* =============================================================================
OBJETIVO: Paradas de teares internos por categoria e mês, com o lançamento em
          lote de início de turno (MLC07) separado
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: MES + CATEGORIA (uma linha por mês e categoria)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
TABELAS PRINCIPAIS: SGTPRD.PARADAS_MAQUINA, SGTPRD.MOTIVOS_PARADAS,
  SGTPRD.MAQUINA, SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
COLUNAS:
  CATEGORIA   agrupamento proposto dos códigos MLC (ver CASE). Não existe no sistema.
              0_MANUTENCAO_PREVENTIVA é só MLC02 (planejada, separada da falha).
  MIN         minutos de parada (DATA/HORA de início e término).
  EVT         número de eventos.
  MAQ         máquinas com ao menos um evento na categoria no mês.
  PCT_MIN_MES participação da categoria nos minutos do mês.
CUIDADOS OPERACIONAIS:
  - MLC07 (início de turno) é lançado em lote: em 2025 foram 44 dias em que quase todas
    as máquinas receberam o mesmo registro (cerca de 59 min cada; REGRAS_NEGOCIO.md, 5.4).
    Por isso aparece em categoria própria (5_INICIO_TURNO_LOTE). Ver
    mal_qualidade_registro_paradas.sql.
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
PARADAS_DUR AS (
    SELECT SUBSTR(TO_CHAR(PM.DATA_INICIO), 1, 6) AS MES,
           PM.NUMERO_MAQUINA,
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
CLASSIFICADAS AS (
    SELECT MES,
           NUMERO_MAQUINA,
           MIN_PARADA,
           CASE
               WHEN CODIGO_PARADA = 'MLC07' THEN '5_INICIO_TURNO_LOTE'
               WHEN CODIGO_PARADA = 'MLC02' THEN '0_MANUTENCAO_PREVENTIVA'
               WHEN CODIGO_PARADA IN ('MLC03','MLC04','MLC22','MLC23','MLC25') THEN '1_MANUTENCAO_DEFEITO'
               WHEN CODIGO_PARADA IN ('MLC12','MLC19','MLC20','MLC26','MLC27','MLC28','MLC29','MLC30',
                                      'MLC31','MLC32','MLC33','MLC34','MLC35','MLC36','MLC38','MLC39','MLC41')
                    THEN '2_FIO_PROCESSO_PANO'
               WHEN CODIGO_PARADA IN ('MLC01','MLC08','MLC11','MLC13','MLC14','MLC15','MLC16','MLC17',
                                      'MLC18','MLC37')
                    THEN '3_TROCA_LIMPEZA_AJUSTE'
               WHEN CODIGO_PARADA IN ('MLC24','MLC40','MLC42','MLC43') THEN '4_SUPRIMENTO_OPERADOR'
               WHEN CODIGO_PARADA IN ('MLC05','MLC09','MLC10','MLC21') THEN '6_TURNO_REUNIAO_INTERVALO'
               ELSE '7_OUTRAS'
           END AS CATEGORIA
      FROM PARADAS_DUR
),
MES_CAT AS (
    SELECT MES,
           CATEGORIA,
           ROUND(SUM(MIN_PARADA), 0) AS MIN,
           COUNT(*)                  AS EVT,
           COUNT(DISTINCT NUMERO_MAQUINA) AS MAQ
      FROM CLASSIFICADAS
     GROUP BY MES, CATEGORIA
)
SELECT MC.MES,
       MC.CATEGORIA,
       MC.MIN,
       MC.EVT,
       MC.MAQ,
       ROUND(100 * MC.MIN / NULLIF(SUM(MC.MIN) OVER (PARTITION BY MC.MES), 0), 1) AS PCT_MIN_MES
  FROM MES_CAT MC
 ORDER BY MC.MES, MC.CATEGORIA;
