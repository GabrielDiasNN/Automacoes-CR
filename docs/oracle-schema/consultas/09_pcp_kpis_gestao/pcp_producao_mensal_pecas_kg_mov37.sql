/* =============================================================================
OBJETIVO: Produção Mensal por Peça e KG - Movimento 37 (Produto Acabado)
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\Produção Mensal (Produdo Acabado).sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (janela: 12 meses completos + mês corrente, por SYSDATE)
TABELAS PRINCIPAIS: SGTPRD.BD_PRD_MOVPROD
CUIDADOS OPERACIONAIS: Consulta agregada mensal por competência de produção (movimento 37, códigos 1 e 8).
OTIMIZAÇÃO: Estruturada em CTE para desacoplar agregação de apresentação.
  Formatação de data unificada via TO_CHAR com máscara Fill Mode (FM) e texto literal.
  Cálculo de média protegido por NULLIF contra divisão por zero.
  Ordenação cronológica explícita por DATA_REFERENCIA.
  Janela de 12 meses + mês corrente (07/10/2026): sem ela a consulta agregava o
  histórico inteiro de BD_PRD_MOVPROD (~56 mi linhas) e estourava a janela de
  rede (~4-6 s); com ela usa o índice (CODIGO, PRODUCAO_DATA) e roda em < 1 s.
  Para outro período, altere o limite inferior de PRODUCAO_DATA.
============================================================================= */

WITH agregacao AS (
    SELECT
        TRUNC(PRODUCAO_DATA, 'MM') AS DATA_REFERENCIA,
        COUNT(IDPECASPRODUTO)      AS QT_PECAS,
        SUM(QUANTIDADE_REAL)       AS QT_KG
    FROM SGTPRD.BD_PRD_MOVPROD
    WHERE NUM_TIPO_MOVIMENTO = 37
      AND CODIGO IN (1, 8)
      AND PRODUCAO_DATA >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)
    GROUP BY TRUNC(PRODUCAO_DATA, 'MM')
)
SELECT
    DATA_REFERENCIA,
    TO_CHAR(
        DATA_REFERENCIA,
        'FMMonth "de" YYYY',
        'nls_date_language=PORTUGUESE'
    ) AS DESCRICAO_MES_ANO,
    QT_PECAS,
    QT_KG,
    ROUND(QT_KG / NULLIF(QT_PECAS, 0), 2) AS MEDIA_PC
FROM agregacao
ORDER BY DATA_REFERENCIA
