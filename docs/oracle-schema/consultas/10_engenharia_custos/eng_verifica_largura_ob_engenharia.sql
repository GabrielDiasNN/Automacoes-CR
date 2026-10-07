/* =============================================================================
OBJETIVO: Verifica largura (OB engenharia)
DOMÍNIO: 10_engenharia_custos
ARQUIVO ORIGINAL: Comandos SQL - CR\Verifica largura (OB engenharia).sql
TIPO: Engenharia e Ficha Técnica
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ENG_PRODG_ACABADO, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT DISTINCT ENG.LARGURA,
                ENG.LARGURATOTAL,
                ENG.GRAMATURA,
                --ITE.ESPECIFICACAOPRODUTO, 
                --ENG.IDESPECIFICACAO_PROD,
                ENG.COMPRIMENTO_DA_PECA
  FROM SGTPRD.ENG_PRODG_ACABADO ENG
  JOIN SGTPRD.ITENS_ESTOQUE     ITE
    ON ITE.REDUZIDO_AGRUPADOR = ENG.REDUZIDO_AGRUPADOR
 WHERE TRIM(ITE.IDMASCARATIPOINSUMO) = 'BNF'
   AND SUBSTR(ITE.CODIGO, 4, 5) = '00010'
 ORDER BY 1;
