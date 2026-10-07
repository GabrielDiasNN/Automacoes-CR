/* =============================================================================
OBJETIVO: Peso padrão (cru e acabado)
DOMÍNIO: 10_engenharia_custos
ARQUIVO ORIGINAL: Comandos SQL - CR\Peso padrão (cru e acabado).sql
TIPO: Engenharia e Ficha Técnica
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ENGEITEMESTOARTCRU, SGTPRD.ENG_PRODG_ACABADO, SGTPRD.ITENS_ESTOQUE, SGTPRD.PESO_PADRAO_PECA
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

    SELECT  
        BASE.ARTIGO, 
        ART.CDREDUZIDO AS REDUZIDO, 
        BASE.PESO_PADRAO AS PESO_PADRAO
    FROM (
        SELECT  
            ART.CDARTIGOCRU AS ARTIGO,
            PCR.PESO_METROS_PECA AS PESO_PADRAO,
            ART.CDREDUZIDO AS REDUZIDO
        FROM 
            SGTPRD.PESO_PADRAO_PECA PCR
        JOIN 
            SGTPRD.ENGEITEMESTOARTCRU ART ON ART.CDREDUZIDO = PCR.CODIGO_REDUZIDO_PROD

        UNION ALL

        SELECT  
            ART.CDARTIGOCRU AS ARTIGO,
            PAC.VLPESO_METROS_PECA AS PESO_PADRAO,
            AGR.CODIGO_REDUZIDO AS REDUZIDO
        FROM 
            SGTPRD.ENG_PRODG_ACABADO PAC
        JOIN 
            SGTPRD.ITENS_ESTOQUE AGR ON AGR.REDUZIDO_AGRUPADOR = PAC.REDUZIDO_AGRUPADOR
        JOIN 
            SGTPRD.ENGEITEMESTOARTCRU ART ON ART.CDREDUZIDO = AGR.CODIGO_REDUZIDO
    ) BASE
    LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ART ON ART.CDARTIGOCRU = BASE.ARTIGO
    GROUP BY BASE.ARTIGO, ART.CDREDUZIDO, BASE.PESO_PADRAO
