/* =============================================================================
OBJETIVO: Consumo de produtos químicos por kg de tecido tingido, por partida de tingimento confirmada nos últimos 30 dias (g/kg), com cor, artigo e máquina para agregação
DOMÍNIO: 01_beneficiamento_tingimento
TIPO: Painel/KPI
GRÃO: NR_PARTIDA + SEQ_PARTIDA (uma linha por partida de tingimento: NUMEROORDEMMOVIMENTO + SEQUENCIAORDEMMOVIME de OB_FASES)
PARÂMETROS / BINDS: Nenhum (janela: partidas com tingimento confirmado nos últimos 30 dias)
TABELAS PRINCIPAIS: SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.MOVTO_RECEITA
CUIDADOS OPERACIONAIS: Somente leitura. Substitui a leitura absoluta de
  bnf_tingimento_confirmado_consumo_produtos.sql por uma medida normalizada pelo peso tingido.
  Partida = conjunto de OBs tingidas juntas na mesma carga. A receita é gravada em
  MOVTO_RECEITA com NUMEROORDEM/SEQUENCIAFASEOB iguais a OB_FASES.NUMEROORDEMMOVIMENTO/
  SEQUENCIAORDEMMOVIME (chave canônica; a consulta antiga reconstrói isso com DECODE do grupo).
  Universo: fase de tingimento (CODIGO_FASE = 40) confirmada (STATUS = 4) com
  TEMPO_FINAL_CONFIRMA (minutos desde 1996-01-01) nos últimos 30 dias.
  KG_TECIDO = soma de OB_FASES.KILOS_PRODUZIDOS das OBs da partida (igual a OB_PRODUTO.KILOS
  nas partidas conferidas).
  KG_QUIMICO = soma de MOVTO_RECEITA.QUANTIDADEPESADA em kg, de TODOS os produtos da receita
  (corantes e auxiliares, incluindo sal e barrilha, que dominam o peso em cores escuras).
  G_POR_KG = KG_QUIMICO * 1000 / KG_TECIDO; NULL se a partida não tem peso de tecido.
  Partida sem nenhuma linha de receita pesada aparece com KG_QUIMICO = 0 (não é omitida).
  Para cor, máquina ou artigo agregados, some KG_QUIMICO e KG_TECIDO e divida depois; não
  faça média de G_POR_KG. QT_ARTIGOS > 1 indica partida com artigos misturados (ARTIGO
  mostra o menor código).
  NÃO inclui custo por kg: não há fonte de custo do químico validada neste acervo (a consulta
  bnf_quimico_valor_media_comparado_ao_preco_de_faturamento.sql compara com preço de venda).
============================================================================= */

WITH PARTIDA AS (
    SELECT /*+ MATERIALIZE */
           OBF.NUMEROORDEMMOVIMENTO                    AS NR_PARTIDA,
           OBF.SEQUENCIAORDEMMOVIME                    AS SEQ_PARTIDA,
           COUNT(*)                                    AS QT_OBS,
           SUM(NVL(OBF.KILOS_PRODUZIDOS, 0))           AS KG_TECIDO,
           MIN(SUBSTR(OBF.NUMERO_MAQUINA, 7, 4))       AS MQ,
           MIN(TRIM(OBF.CODIGO_COR_DESENHO))           AS COR,
           MAX(OBF.TEMPO_FINAL_CONFIRMA)               AS TEMPO_FINAL,
           MIN(OBF.NUMERO_OB)                          AS OB_REFERENCIA
      FROM SGTPRD.OB_FASES OBF
     WHERE OBF.CODIGO_FASE = 40
       AND OBF.STATUS = 4
       AND OBF.TEMPO_FINAL_CONFIRMA >= (TRUNC(SYSDATE) - 30 - DATE '1996-01-01') * 1440
       AND OBF.TEMPO_FINAL_CONFIRMA <  (TRUNC(SYSDATE) + 1 - DATE '1996-01-01') * 1440
     GROUP BY OBF.NUMEROORDEMMOVIMENTO, OBF.SEQUENCIAORDEMMOVIME
),
ARTIGO AS (
    SELECT OBF.NUMEROORDEMMOVIMENTO                    AS NR_PARTIDA,
           OBF.SEQUENCIAORDEMMOVIME                    AS SEQ_PARTIDA,
           COUNT(DISTINCT OBP.CODPRO_REDUZIDO)         AS QT_ARTIGOS,
           MIN(ITE.CODIGO_ALTERNATIVO)                 AS ARTIGO
      FROM SGTPRD.OB_FASES OBF
      JOIN PARTIDA PAR ON PAR.NR_PARTIDA = OBF.NUMEROORDEMMOVIMENTO
                      AND PAR.SEQ_PARTIDA = OBF.SEQUENCIAORDEMMOVIME
      JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = OBF.NUMERO_OB
      JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = OBP.CODPRO_REDUZIDO
     WHERE OBF.CODIGO_FASE = 40
     GROUP BY OBF.NUMEROORDEMMOVIMENTO, OBF.SEQUENCIAORDEMMOVIME
),
QUIMICO AS (
    SELECT REC.NUMEROORDEM                             AS NR_PARTIDA,
           REC.SEQUENCIAFASEOB                         AS SEQ_PARTIDA,
           SUM(REC.QUANTIDADEPESADA)                   AS KG_QUIMICO,
           COUNT(DISTINCT REC.CODINSREDUZIDO)          AS QT_PRODUTOS
      FROM SGTPRD.MOVTO_RECEITA REC
      JOIN PARTIDA PAR ON PAR.NR_PARTIDA = REC.NUMEROORDEM
                      AND PAR.SEQ_PARTIDA = REC.SEQUENCIAFASEOB
     GROUP BY REC.NUMEROORDEM, REC.SEQUENCIAFASEOB
)
SELECT PAR.NR_PARTIDA,
       PAR.SEQ_PARTIDA,
       DATE '1996-01-01' + PAR.TEMPO_FINAL / 1440      AS DT_TINGIMENTO_CONFIRMADO,
       PAR.MQ,
       PAR.COR,
       ART.ARTIGO,
       ART.QT_ARTIGOS,
       PAR.QT_OBS,
       ROUND(PAR.KG_TECIDO, 1)                         AS KG_TECIDO,
       ROUND(NVL(QUI.KG_QUIMICO, 0), 2)                AS KG_QUIMICO,
       NVL(QUI.QT_PRODUTOS, 0)                         AS QT_PRODUTOS,
       ROUND(NVL(QUI.KG_QUIMICO, 0) * 1000 / NULLIF(PAR.KG_TECIDO, 0), 1) AS G_POR_KG
  FROM PARTIDA PAR
  LEFT JOIN ARTIGO ART ON ART.NR_PARTIDA = PAR.NR_PARTIDA
                      AND ART.SEQ_PARTIDA = PAR.SEQ_PARTIDA
  LEFT JOIN QUIMICO QUI ON QUI.NR_PARTIDA = PAR.NR_PARTIDA
                       AND QUI.SEQ_PARTIDA = PAR.SEQ_PARTIDA
 ORDER BY PAR.TEMPO_FINAL DESC, PAR.NR_PARTIDA
