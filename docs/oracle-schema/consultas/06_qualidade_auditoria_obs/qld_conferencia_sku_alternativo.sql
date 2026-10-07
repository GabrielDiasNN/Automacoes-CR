/* =============================================================================
OBJETIVO: Conferência de SKU TOTVS por código alternativo
DOMÍNIO: 06_qualidade_auditoria_obs
ARQUIVO ORIGINAL: 06_qualidade_auditoria_obs/qld_conferencia_sku_totvs.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum
TABELAS PRINCIPAIS: SGTPRD.ENGEITEMESTONIVELGE9, SGTPRD.ITENS_ESTOQUE, SGTPRD.TB_ESP_TABPRECO_TOTVS, SGTPRD.TCLI_ITENS_TOTVS
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
REVISÃO (20/09/2026 - Onda 4): (+) de SKU migrado para LEFT JOIN ANSI.
  guard_sql.py: exit 0.
============================================================================= */

SELECT TRIM(ITE.CODIGO_ALTERNATIVO)                  ALTERNATIVO,
       ITE.CODIGO_REDUZIDO                           REDUZIDO,
       
       (SELECT T.PRECO_TOTVS
          FROM SGTPRD.TB_ESP_TABPRECO_TOTVS T
         WHERE T.SKU_TOTVS = SKU.SKU_TOTVS
           AND T.TABELA_TOTVS = 1003)                PREO,
           
       SKU.SKU_TOTVS                                 SKU_TOTVS,
       ENG.CDNIVELGENERICO                           FLUXO,
       TO_DATE(ITE.DATA_CADASTRAMENTO, 'YYYY/MM/DD') DATA_CADASTRO
  FROM SGTPRD.ITENS_ESTOQUE        ITE
  JOIN SGTPRD.ENGEITEMESTONIVELGE9 ENG ON ENG.CDREDUZIDO    = ITE.CODIGO_REDUZIDO
  LEFT JOIN SGTPRD.TCLI_ITENS_TOTVS SKU ON SKU.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
 WHERE ITE.IDPESSOAFJPROPRIETAR    = 2
 ORDER BY 2 DESC;
