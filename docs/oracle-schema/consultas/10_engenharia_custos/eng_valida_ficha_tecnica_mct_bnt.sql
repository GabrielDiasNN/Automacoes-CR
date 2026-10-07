/* =============================================================================
OBJETIVO: Validação de Ficha Técnica Cru (MCT) e Acabado (BNT) de Clientes
DOMÍNIO: 10_engenharia_custos
ARQUIVO: sql/10_engenharia_custos/eng_valida_ficha_tecnica_mct_bnt.sql
TIPO: SELECT (Auditoria e Validação de Engenharia de Produto)
PARÂMETROS / BINDS: Nenhum (filtros diretos na query, customizáveis via WHERE)
TABELAS PRINCIPAIS: SGTPRD.ITENS_DESCENDENCIA, SGTPRD.ITENS_ESTOQUE,
                    SGTPRD.ENG_PRODG_ACABADO, SGTPRD.ENG_PRODG_CRU,
                    SGTPRD.ENGEITEMESTOARTCRU, SGTPRD.ENGEITEMARTIGOCRU,
                    SGTPRD.ENGEITEMESTONIVELGE9, SGTPRD.GRUPO_PRODUTO,
                    SGTPRD.GRUPO_FLUXO, SGTPRD.GRUPO_FLUXO_FASES,
                    SGTPRD.CADASTRO_RECEITAS, SGTPRD.ENG_PRODG_COMPOSICAO,
                    SGTPRD.COMPOSICAO_FIBRAS, SGTPRD.TIPO_ACONDICIONAMENT,
                    SGTPRD.COML_ITEMPORGRUPODEP, SGTPRD.COML_GRUPOSPRECOSITE,
                    SGTPRD.COML_PRECOSARTIGOS, SGTPRD.COML_PRECOSINSUMOS,
                    SGTPRD.COML_TABELAPRECOS
CUIDADOS OPERACIONAIS: Consulta somente leitura para auditoria cadastral de engenharia.
                       Compara parâmetros cru x acabado, identifica fases de acabamento
                       (Tubular = Hidro / Ramado = Rama), calcula o preço final da tabela
                       compondo serviço + insumo aplicado, e sinaliza flags de inconsistência.
============================================================================= */

WITH COMPOSICAO_AGRUPADOR AS (
    SELECT /*+ MATERIALIZE */
           ENC.REDUZIDO_AGRUPADOR,
           LISTAGG(TRIM(TO_CHAR(ENC.COMPOSICAO, 'FM990')) || '% ' || TRIM(CFB.DESCRICAO), ' / ' ON OVERFLOW TRUNCATE)
             WITHIN GROUP (ORDER BY ENC.COMPOSICAO DESC) AS COMPOSICAO
      FROM SGTPRD.ENG_PRODG_COMPOSICAO ENC
      JOIN SGTPRD.COMPOSICAO_FIBRAS CFB
        ON CFB.CODIGO = ENC.CODIGO
     GROUP BY ENC.REDUZIDO_AGRUPADOR
)
SELECT /*+ FIRST_ROWS(100) */
    -- 1. IDENTIFICAÇÃO E HIERARQUIA DO PRODUTO (ACABADO X CRU)
    ACA.CODIGO_REDUZIDO                                            AS REDUZIDO_ACABADO,
    TRIM(ACA.CODIGO)                                               AS CODIGO_ACABADO,
    TRIM(ACA.DESCRICAO)                                            AS PRODUTO_ACABADO,
    CASE
        WHEN TRIM(NGE9.CDNIVELGENERICO) = 'T' OR SUBSTR(ACA.CODIGO, 9, 1) = 'T' THEN 'TUBULAR'
        WHEN TRIM(NGE9.CDNIVELGENERICO) = 'R' OR SUBSTR(ACA.CODIGO, 9, 1) = 'R' THEN 'RAMADO'
        ELSE 'OUTRO'
    END                                                            AS TIPO_ESTRUTURA,
    CRU.CODIGO_REDUZIDO                                            AS REDUZIDO_CRU,
    TRIM(CRU.CODIGO)                                               AS CODIGO_CRU,
    TRIM(CRU.DESCRICAO)                                            AS PRODUTO_CRU,

    -- 2. DADOS TÉCNICOS: LARGURA E GRAMATURA
    EPA.LARGURA                                                    AS LARGURA_UTIL_ACABADO,
    EPA.LARGURATOTAL                                               AS LARGURA_TOTAL_ACABADO,
    EPA.GRAMATURA                                                  AS GRAMATURA_ACABADO,
    EPC.LARGURA                                                    AS LARGURA_CRU,
    EPC.GRAMATURA                                                  AS GRAMATURA_CRU,

    -- 3. DADOS DE ARTIGO
    TRIM(COALESCE(ENG_A.CDARTIGOCRU, ENG_C.CDARTIGOCRU))           AS CODIGO_ARTIGO,
    TRIM(COALESCE(ART_A.DSITEMARTIGOCRU, ART_C.DSITEMARTIGOCRU))   AS NOME_ARTIGO,

    -- 4. GRUPO DE PROGRAMAÇÃO
    ACA.NUMERO_GRUPO_PROGRAM                                       AS NGP,
    TRIM(GPR.CODIGO_GRUPO_PROGRAM)                                 AS COD_GRUPO_PROGRAMACAO,
    TRIM(GPR.DESCRICAO)                                            AS DESCR_GRUPO_PROGRAMACAO,

    -- 5. GRUPO DE FLUXO CADASTRADO
    IDE.IDGRUPOFLUXO                                               AS ID_GRUPO_FLUXO,
    GFL.CODIGO_FLUXO                                               AS CODIGO_FLUXO,
    TRIM(GFL.DSENGENHARIA)                                         AS DESCR_FLUXO_ENGENHARIA,

    -- 6. RECEITA DE ACABAMENTO (TUBULAR = FASE HIDRO / RAMADO = FASE RAMA)
    REC.CODIGO_FASE                                                AS CODIGO_FASE_ACABAMENTO,
    REC.DESCRICAO_FASE                                             AS FASE_ACABAMENTO,
    REC.RECEITA_PROCESSO                                           AS RECEITA_ACABAMENTO,
    REC.DESCR_RECEITA                                              AS DESCR_RECEITA_ACABAMENTO,

    -- 7. COMPOSIÇÃO TÊXTIL
    COALESCE(
        CMP.COMPOSICAO,
        TRIM(ACA.NOME_DETALHADO1),
        TRIM(CRU.NOME_DETALHADO1)
    )                                                              AS COMPOSICAO,

    -- 8. ACONDICIONAMENTO
    TRIM(TAC_A.DESCRICAO)                                          AS ACONDICIONAMENTO_ACABADO,
    TRIM(TAC_C.DESCRICAO)                                          AS ACONDICIONAMENTO_CRU,

    -- 9. TABELA DE PREÇO E VALOR FINAL (SERVIÇO + INSUMO APLICADO)
    TAB.TABELAPRECO                                                AS COD_TABELA_PRECO,
    TAB.NOME_TABELA                                                AS NOME_TABELA_PRECO,
    TAB.PRECO_SERVICO                                              AS VALOR_PRECO_SERVICO,
    TAB.PRECO_INSUMO                                               AS VALOR_PRECO_INSUMO,
    TAB.PRECO_FINAL_TABELA                                         AS VALOR_PRECO_FINAL,
    CRU.PRECO_PEDIDO                                               AS VALOR_INSUMO_CRU,
    TAB.UM_PRECO                                                   AS UNIDADE_PRECO,

    -- 10. STATUS CADASTRAL
    ACA.INSUMO_COM_MOVIMENTO                                       AS ATIVO_ACABADO,
    CRU.INSUMO_COM_MOVIMENTO                                       AS ATIVO_CRU,

    -- 11. FLAGS DE AUDITORIA DE ENGENHARIA (IDENTIFICAÇÃO DE GAPS CADASTRAIS)
    CASE
        WHEN NVL(EPA.LARGURA, 0) <= 0 OR NVL(EPA.GRAMATURA, 0) <= 0 THEN 'PENDENTE DIMENSÃO ACABADO'
        WHEN NVL(EPC.LARGURA, 0) <= 0 OR NVL(EPC.GRAMATURA, 0) <= 0 THEN 'PENDENTE DIMENSÃO CRU'
        WHEN REC.RECEITA_PROCESSO IS NULL THEN 'SEM RECEITA ACABAMENTO'
        WHEN ACA.NUMERO_GRUPO_PROGRAM IS NULL THEN 'SEM GRUPO PROGRAMAÇÃO'
        WHEN IDE.IDGRUPOFLUXO IS NULL THEN 'SEM GRUPO FLUXO'
        WHEN TAB.PRECO_FINAL_TABELA IS NULL THEN 'SEM PREÇO CADASTRADO'
        ELSE 'OK'
    END                                                            AS STATUS_AUDITORIA_ENG

FROM SGTPRD.ITENS_DESCENDENCIA IDE
JOIN SGTPRD.ITENS_ESTOQUE ACA
  ON ACA.CODIGO_REDUZIDO = IDE.CODIGO_REDUZIDO
JOIN SGTPRD.ITENS_ESTOQUE CRU
  ON CRU.CODIGO_REDUZIDO = IDE.CODIGO_REDUZIDO_DESC

-- Decodificação Estrutural: Tubular (T) x Ramado (R)
LEFT JOIN SGTPRD.ENGEITEMESTONIVELGE9 NGE9
  ON NGE9.CDREDUZIDO = ACA.CODIGO_REDUZIDO

-- Parâmetros Dimensionais do Acabado
LEFT JOIN SGTPRD.ENG_PRODG_ACABADO EPA
  ON EPA.REDUZIDO_AGRUPADOR = ACA.REDUZIDO_AGRUPADOR
LEFT JOIN COMPOSICAO_AGRUPADOR CMP
  ON CMP.REDUZIDO_AGRUPADOR = ACA.REDUZIDO_AGRUPADOR
LEFT JOIN SGTPRD.TIPO_ACONDICIONAMENT TAC_A
  ON TAC_A.IDACONDICIONAMENTO = NVL(EPA.IDACONDICIONAMENTO, ACA.COD_ACONDICIONAMENTO)

-- Parâmetros Dimensionais do Cru
LEFT JOIN SGTPRD.ENG_PRODG_CRU EPC
  ON EPC.REDUZIDO_AGRUPADOR = CRU.REDUZIDO_AGRUPADOR
LEFT JOIN SGTPRD.TIPO_ACONDICIONAMENT TAC_C
  ON TAC_C.IDACONDICIONAMENTO = NVL(EPC.IDACONDICIONAMENTO, CRU.COD_ACONDICIONAMENTO)

-- Associação de Artigo (Acabado e Cru)
LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ENG_A
  ON ENG_A.CDREDUZIDO = ACA.CODIGO_REDUZIDO
LEFT JOIN SGTPRD.ENGEITEMARTIGOCRU ART_A
  ON ART_A.CDITEMARTIGOCRU = ENG_A.CDARTIGOCRU
LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ENG_C
  ON ENG_C.CDREDUZIDO = CRU.CODIGO_REDUZIDO
LEFT JOIN SGTPRD.ENGEITEMARTIGOCRU ART_C
  ON ART_C.CDITEMARTIGOCRU = ENG_C.CDARTIGOCRU

-- Associação de Grupo de Programação
LEFT JOIN SGTPRD.GRUPO_PRODUTO GPR
  ON GPR.NUMERO_GRUPO_PROGRAM = ACA.NUMERO_GRUPO_PROGRAM

-- Associação de Grupo de Fluxo
LEFT JOIN SGTPRD.GRUPO_FLUXO GFL
  ON GFL.IDGRUPOFLUXO = IDE.IDGRUPOFLUXO

-- Resolução da Receita da Fase de Acabamento (Tubular = Hidro / Ramado = Rama)
LEFT JOIN (
    SELECT
        GFF.IDGRUPOFLUXO,
        GFF.CODIGO_FASE,
        TRIM(FFL.DESCRICAO_FASE) AS DESCRICAO_FASE,
        TRIM(GFF.PROCESSO)       AS RECEITA_PROCESSO,
        TRIM(CRE.DESCOR)         AS DESCR_RECEITA,
        ROW_NUMBER() OVER(
            PARTITION BY GFF.IDGRUPOFLUXO,
                         CASE WHEN GFF.CODIGO_FASE IN (100, 110) THEN 'R' ELSE 'T' END
            ORDER BY CASE WHEN GFF.CODIGO_FASE IN (50, 100) THEN 1 ELSE 2 END, GFF.SEQUENCIA
        ) AS RN_FASE
    FROM SGTPRD.GRUPO_FLUXO_FASES GFF
    JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = GFF.CODIGO_FASE
    LEFT JOIN SGTPRD.CADASTRO_RECEITAS CRE ON TRIM(CRE.CODCOR) = TRIM(GFF.PROCESSO)
    WHERE GFF.CODIGO_FASE IN (50, 55, 100, 110)
      AND GFF.PROCESSO IS NOT NULL
) REC ON REC.IDGRUPOFLUXO = IDE.IDGRUPOFLUXO
     AND REC.RN_FASE = 1
     AND REC.CODIGO_FASE = CASE
                             WHEN TRIM(NGE9.CDNIVELGENERICO) = 'R' OR SUBSTR(ACA.CODIGO, 9, 1) = 'R' THEN
                                  CASE WHEN REC.CODIGO_FASE IN (100, 110) THEN REC.CODIGO_FASE ELSE 100 END
                             ELSE
                                  CASE WHEN REC.CODIGO_FASE IN (50, 55) THEN REC.CODIGO_FASE ELSE 50 END
                           END

-- Resolução de Tabela de Preço com Insumo Incluso (Serviço + Insumo Aplicado)
LEFT JOIN (
    SELECT 
        IGP.ITEM                                                         AS CODIGO_REDUZIDO,
        TP.TABELAPRECO,
        TRIM(TP.NOME)                                                    AS NOME_TABELA,
        PA.PRECO                                                         AS PRECO_SERVICO,
        NVL((SELECT SUM(PI.PRECO) 
               FROM SGTPRD.COML_PRECOSINSUMOS PI 
              WHERE PI.TABELAPRECO = PA.TABELAPRECO 
                AND PI.GRUPOPRECOSITEM = PA.GRUPOPRECOSITEM), 0)         AS PRECO_INSUMO,
        PA.PRECO + NVL((SELECT SUM(PI.PRECO) 
                          FROM SGTPRD.COML_PRECOSINSUMOS PI 
                         WHERE PI.TABELAPRECO = PA.TABELAPRECO 
                           AND PI.GRUPOPRECOSITEM = PA.GRUPOPRECOSITEM), 0) AS PRECO_FINAL_TABELA,
        TRIM(UND.DSSIGLA)                                                AS UM_PRECO,
        ROW_NUMBER() OVER(PARTITION BY IGP.ITEM ORDER BY TP.TABELAPRECO) AS RN
    FROM SGTPRD.COML_ITEMPORGRUPODEP IGP
    JOIN SGTPRD.COML_GRUPOSPRECOSITE GPI ON GPI.GRUPOPRECOSITEM = IGP.GRUPOPRECOSITEM
    JOIN SGTPRD.COML_PRECOSARTIGOS PA    ON PA.GRUPOPRECOSITEM  = GPI.GRUPOPRECOSITEM
    JOIN SGTPRD.COML_TABELAPRECOS TP     ON TP.TABELAPRECO      = PA.TABELAPRECO
    LEFT JOIN SGTPRD.UNIDADE_MEDIDA UND  ON UND.IDUNIDADEMEDIDA = PA.IDUNIDADEMEDIDA
) TAB ON TAB.CODIGO_REDUZIDO = ACA.CODIGO_REDUZIDO AND TAB.RN = 1

WHERE ACA.IDMASCARATIPOINSUMO = 'BNT  '
  AND CRU.IDMASCARATIPOINSUMO = 'MCT  '
  AND ACA.INSUMO_COM_MOVIMENTO = '1'

  -- Filtros opcionais para refinamento do Engenheiro:
  -- AND (TRIM(NGE9.CDNIVELGENERICO) = 'R' OR SUBSTR(ACA.CODIGO, 9, 1) = 'R') -- Somente Ramados
  -- AND (TRIM(NGE9.CDNIVELGENERICO) = 'T' OR SUBSTR(ACA.CODIGO, 9, 1) = 'T') -- Somente Tubulares
  -- AND (UPPER(ACA.DESCRICAO) LIKE '%EDJU%' OR UPPER(ART_C.DSITEMARTIGOCRU) LIKE '%EDJU%') -- Cliente 33733 (EDJU MALHAS)
  AND (
      ACA.CODIGO_REDUZIDO IN (25694, 25695, 25696, 25697, 25698, 25699, 25700) -- Cliente 29 (SUL BRASIL) - Artigos A242 e A243
      -- OR CRU.CODIGO_REDUZIDO IN (25692, 25693)
  )
  -- AND STATUS_AUDITORIA_ENG <> 'OK'                                        -- Somente Inconsistências

ORDER BY ACA.CODIGO_REDUZIDO

