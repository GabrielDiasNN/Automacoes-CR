/* =============================================================================
OBJETIVO: First-pass yield do tingimento por cor nos últimos 90 dias: percentual de fases de tingimento concluídas sem reprocesso, em quantidade e em kg
DOMÍNIO: 06_qualidade_auditoria_obs
TIPO: Painel/KPI
GRÃO: COR (uma linha por código de cor com tingimento confirmado na janela)
PARÂMETROS / BINDS: Nenhum (janela: fases de tingimento confirmadas nos últimos 90 dias)
TABELAS PRINCIPAIS: SGTPRD.OB_FASES, SGTPRD.DESTINO, SGTPRD.GRUPO_DESTINO
CUIDADOS OPERACIONAIS: Somente leitura. Mesma definição de reprocesso do runner de produção
  (bnf_producao_beneficiamento_detalhado.sql, coluna REPROCESSO): a fase é reprocesso quando o
  destino da receita (OB_FASES.DESTINO_RECEITA) pertence a um grupo com
  GRUPO_DESTINO.TIPO_DESTINO = 1 (REPROCESSOS e REPROCESSOS RECLASSIFICAR). Assim o indicador
  não contradiz o painel do Dashboard.
  Conferido no Oracle (5.942 fases em 90 dias): as outras marcas de "não foi de primeira" são
  subconjunto desse critério: as 451 fases cadastradas em OB_REPROCESSO e as 29 com
  OB_FASES.SEQUENCIA > 30 têm todas destino de reprocesso (466 no total). Por isso só o destino
  entra aqui.
  NÃO usa MOVTO_RECEITA.SEQUENCIA_AJUSTE (ajuste de cor): a coluna tem só 20 linhas em 1,3
  milhão, todas antigas; usá-la daria 100% de acerto artificial.
  Universo: OB_FASES.CODIGO_FASE = 40 e STATUS = 4 com TEMPO_FINAL_CONFIRMA (minutos desde
  1996-01-01) na janela. Unidade de contagem é a fase de OB, como no runner (uma partida de
  várias OBs conta várias fases). KG = OB_FASES.KILOS_PRODUZIDOS.
  AMOSTRA = 'PEQUENA' abaixo de 20 fases (mesmo corte do Dashboard): não compare cores
  com amostra pequena.
============================================================================= */

WITH FASES AS (
    SELECT TRIM(OBF.CODIGO_COR_DESENHO)                        AS COR,
           NVL(OBF.KILOS_PRODUZIDOS, 0)                        AS KG,
           CASE WHEN NVL(GDX.TIPO_DESTINO, 0) = 1 THEN 1 ELSE 0 END AS REPROCESSO
      FROM SGTPRD.OB_FASES OBF
      LEFT JOIN SGTPRD.DESTINO DEX ON DEX.DESTINO = OBF.DESTINO_RECEITA
      LEFT JOIN SGTPRD.GRUPO_DESTINO GDX ON GDX.CODIGO_GRUPO = DEX.CODIGO_GRUPO
     WHERE OBF.CODIGO_FASE = 40
       AND OBF.STATUS = 4
       AND OBF.TEMPO_FINAL_CONFIRMA >= (TRUNC(SYSDATE) - 90 - DATE '1996-01-01') * 1440
       AND OBF.TEMPO_FINAL_CONFIRMA <  (TRUNC(SYSDATE) + 1 - DATE '1996-01-01') * 1440
)
SELECT FAS.COR,
       COUNT(*)                                                AS QT_FASES,
       SUM(FAS.REPROCESSO)                                     AS QT_REPROCESSO,
       ROUND(SUM(FAS.KG))                                      AS KG_TOTAL,
       ROUND(SUM(CASE WHEN FAS.REPROCESSO = 1 THEN FAS.KG ELSE 0 END)) AS KG_REPROCESSO,
       ROUND((1 - SUM(FAS.REPROCESSO) / COUNT(*)) * 100, 1)    AS PERC_PRIMEIRA_PASSADA_QT,
       ROUND((1 - SUM(CASE WHEN FAS.REPROCESSO = 1 THEN FAS.KG ELSE 0 END)
                  / NULLIF(SUM(FAS.KG), 0)) * 100, 1)          AS PERC_PRIMEIRA_PASSADA_KG,
       CASE WHEN COUNT(*) < 20 THEN 'PEQUENA' ELSE 'OK' END    AS AMOSTRA
  FROM FASES FAS
 GROUP BY FAS.COR
 ORDER BY QT_FASES DESC, FAS.COR
