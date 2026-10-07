/* =============================================================================
OBJETIVO: Verifica composição dos itens
DOMÍNIO: 10_engenharia_custos
ARQUIVO ORIGINAL: Comandos SQL - CR\Verifica composição dos itens.sql
TIPO: Engenharia e Ficha Técnica
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ENG_PRODG_COMPOSICAO, SGTPRD.ESPECIFICACAO_PRODUT, SGTPRD.ITENS_DESCENDENCIA, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT ITE.CODIGO_REDUZIDO                                         REDUZIDO,
       TRIM(ITE.DESCRICAO)                                         DESCRICAO_ITEM,
       ITE.CODIGO                                                  CODIGO_INDUSTRIAL,
       TRIM(ITE.CODIGO_ALTERNATIVO)                                ALTERNATIVO,
       TRIM(ITE.NOME_DETALHADO1)                                   COMP_ITEM,
       LISTAGG(TRIM(ENC.COMPOSICAO), ',' ON OVERFLOW TRUNCATE)
           WITHIN GROUP (ORDER BY TRIM(ENC.COMPOSICAO))             COMP_ENG,
       ITE.ESPECIFICACAOPRODUTO                                    EP,
       
       (SELECT TRIM(EP.DESCRICAO)
          FROM SGTPRD.ESPECIFICACAO_PRODUT EP
         WHERE EP.ESPECIFICACAOPRODUTO = ITE.ESPECIFICACAOPRODUTO) DESCR_EP,
         
       (SELECT LISTAGG(TO_CHAR(ITD.CODIGO_REDUZIDO_DESC), ',' ON OVERFLOW TRUNCATE)
                   WITHIN GROUP (ORDER BY ITD.CODIGO_REDUZIDO_DESC)
          FROM SGTPRD.ITENS_DESCENDENCIA ITD
         WHERE ITD.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO)          REDZ_DESCE
         
  FROM SGTPRD.ITENS_ESTOQUE ITE, SGTPRD.ENG_PRODG_COMPOSICAO ENC
 WHERE ENC.REDUZIDO_AGRUPADOR = ITE.REDUZIDO_AGRUPADOR
   AND SUBSTR(ITE.CODIGO, 6, 3) = '056'
   AND ITE.ESPECIFICACAOPRODUTO = 11 -- Inspeção de descendência mantida fora do SQL executável.
 GROUP BY ITE.CODIGO_REDUZIDO,
          ITE.DESCRICAO,
          ITE.CODIGO,
          ITE.CODIGO_ALTERNATIVO,
          ITE.NOME_DETALHADO1,
          ITE.ESPECIFICACAOPRODUTO
 ORDER BY REDZ_DESCE, ITE.CODIGO
