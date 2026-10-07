/* =============================================================================
OBJETIVO: TOP 5 - Produção Diária Fiação
DOMÍNIO: 04_fiacao_fios
ARQUIVO ORIGINAL: Comandos SQL - CR\TOP 5 - Produção Diária Fiação.sql
TIPO: Fiação e Fios
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ITENS_ESTOQUE, SGTPRD.LPM_TECELAGEM, SGTPRD.MAQUINA
CUIDADOS OPERACIONAIS: Consulta somente leitura; a data numérica DATLPM é
                        convertida com máscara explícita YYYYMMDD.
REVISÃO (21/09/2026 - frente cirúrgica): cadeia de produção inlinada em
  tabelas/CTE; projeção de duas colunas mantida.
REVISÃO (29/09/2026 - auditoria): removido o JOIN com GRUPO_MAQUINAS. A tabela não
  alimenta nenhuma coluna e `LPM_TECELAGEM.GRUPO` está vazio nas ~300 mil linhas do
  setor 2, então o join eliminava todas as linhas (a consulta retornava 0 linhas
  sempre, não por ausência de produção). ATENÇÃO: a soma diária da LPM (~34 mil/dia,
  84 linhas por dia) não bate com BD_PRD_MOVPROD (fia_producao_fiacao.sql, kg reais
  de 10 a 58 mil/dia); tratar `PRODUCAO_MTROS_TURNO` como apontamento de LPM, não como
  kg produzidos, até a área confirmar a semântica.
  Outlier conhecido: 2024-10-01 aparece em 1º com ~7,0 milhões porque uma única linha da
  LPM traz 354.451; é dado de origem, não erro da consulta.
============================================================================= */

WITH PROD_FIACAO AS (
    SELECT
        TO_DATE(
            TO_CHAR(DECODE(LPM.DATLPM, 0, 18991231, LPM.DATLPM), 'FM00000000'),
            'YYYYMMDD'
        ) AS DT_PRODUCAO,
        LPM.PRODUCAO_MTROS_TURNO AS QT_PRODUZIDA
    FROM SGTPRD.LPM_TECELAGEM LPM
    JOIN SGTPRD.MAQUINA MAQ
      ON MAQ.SETOR = LPM.SETOR
     AND MAQ.NUMERO_MAQUINA = LPM.NUMERO_MAQUINA
    JOIN SGTPRD.ITENS_ESTOQUE ITE
      ON ITE.CODIGO_REDUZIDO = LPM.CODINSREDUZIDO
    WHERE LPM.SETOR = 2
      AND MAQ.CDFILIAL = 1
)
SELECT
    DT_PRODUCAO,
    SUM(QT_PRODUZIDA) AS QT_PRODUZIDA
FROM PROD_FIACAO
GROUP BY DT_PRODUCAO
ORDER BY QT_PRODUZIDA DESC
FETCH FIRST 5 ROWS ONLY;
