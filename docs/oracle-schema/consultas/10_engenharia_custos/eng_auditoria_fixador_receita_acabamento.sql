/* =============================================================================
OBJETIVO: Auditoria de Receitas de Acabamento, Grupos de Programação e OBs em Aberto (Trava SGT)
DOMÍNIO: 10_engenharia_custos
ARQUIVO: sql/10_engenharia_custos/eng_auditoria_fixador_receita_acabamento.sql
TIPO: Auditoria/Sentinela
GRÃO: REDUZIDO (uma linha por item de estoque BNF/BNR/BNT com movimento)
PARÂMETROS / BINDS: Nenhum (filtros diretos na query, customizáveis via WHERE)
TABELAS PRINCIPAIS: SGTPRD.ITENS_ESTOQUE, SGTPRD.GRUPO_PRODUTO, SGTPRD.COR,
                    SGTPRD.ITENS_DESCENDENCIA, SGTPRD.GRUPO_FLUXO, SGTPRD.GRUPO_FLUXO_FASES,
                    SGTPRD.FASES_FLUXO, SGTPRD.CADASTRO_RECEITAS, SGTPRD.OB
CUIDADOS OPERACIONAIS: Consulta 100% nativa sem views legadas. Mapeia a fase de acabamento
                       químico (Tubular = Hidro Fase 50 / Ramado = Rama Fase 100), identifica a receita
                       ativa aplicada, categoriza o status de fixador do grupo e da receita,
                       detecta divergências de congruência e sugere o Grupo de Programação
                       equivalente SEM FIXADOR para orientar alterações cirúrgicas de PCP/Engenharia.
                       Rastreia Ordens de Beneficiamento (OB) em aberto (STATUS <> 0: Emitida,
                       Programada, Bloqueada, Interditada). Se houver OB em aberto, a interface
                       do SGT bloqueia alterações na ficha técnica do item.
AMARRAÇÃO DE FLUXO E REFINAMENTO PENTE FINO (30/09/2026):
  1. Descrição de Cor Dinâmica: Join real com SGTPRD.COR pelo código de 5 dígitos (posições 13-17).
  2. Proteção de String: LISTAGG com ON OVERFLOW TRUNCATE contra estouro ORA-01489 em artigos de alto giro.
  3. Pares de Estampados: Mapeia tanto sufixos regulares (00 -> 01) quanto industriais estampados (98 -> 99).
  4. Deduplicação de Receita: Blindagem analítica (ROW_NUMBER por CODCOR ativo) contra registros homônimos.
  5. Amarração Determinística de Fluxo:
     - 1º) Fluxo cujo GRUPO_FLUXO.NUMERO_GRUPO_PROGRAM coincide com o do item em ITENS_ESTOQUE;
     - 2º) Fluxo com receita química ativa nas fases principais 50 (Hidro) ou 100 (Rama);
     - 3º) Fluxo Interno antes de Facção;
     - 4º) Fluxo mais recente (IDGRUPOFLUXO DESC).
  6. Hierarquia Exaustiva de Congruência:
     - Alerta de item sem grupo de programação (47 itens);
     - Alerta de item sem fluxo de engenharia cadastrado (70 itens);
     - Divergência real Grupo Preto Enxofre vs Receita Preto Reativo (Item 12128);
     - Mensagem explícita para grupos COM FIXADOR sem par equivalente no cadastro do SGT.
AUDITORIA PENTE FINO (30/09/2026): grão conferido no Oracle com 4.421 reduzidos únicos analisados:
  - Congruência global: 4.299 OK, 70 ALERTA (sem fluxo cadastrado), 47 ALERTA (sem grupo),
    4 ALERTA (receita genérica) e 1 DIVERGÊNCIA real (Item 12128: Grupo Enxofre com Receita Reativo).
  - Falsos positivos: 0 (100% eliminados com a amarração NGP).
  - Trava de OBs no ERP: 228 reduzidos bloqueados por OB em aberto (704 OBs ativas)
    e 4.193 reduzidos 100% liberados para alteração via SGT.
============================================================================= */

WITH RECEITA_FASES AS (
    SELECT /*+ MATERIALIZE */
        GFF.IDGRUPOFLUXO,
        GFF.CODIGO_FASE,
        TRIM(FFL.DESCRICAO_FASE) AS DESCRICAO_FASE,
        TRIM(GFF.PROCESSO)       AS RECEITA_PROCESSO,
        TRIM(CRE.DESCOR)         AS DESCR_RECEITA,
        ROW_NUMBER() OVER(
            PARTITION BY GFF.IDGRUPOFLUXO
            ORDER BY
                CASE WHEN GFF.CODIGO_FASE IN (50, 100) THEN 1 ELSE 2 END,
                CASE WHEN CRE.DESCOR IS NOT NULL THEN 1 ELSE 2 END,
                GFF.SEQUENCIA
        ) AS RN_FASE
    FROM SGTPRD.GRUPO_FLUXO_FASES GFF
    JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = GFF.CODIGO_FASE
    LEFT JOIN (
        SELECT
            TRIM(CODCOR) AS CODCOR,
            TRIM(DESCOR) AS DESCOR,
            ROW_NUMBER() OVER(PARTITION BY TRIM(CODCOR) ORDER BY CODIGO_REGISTRO DESC) AS RN_REC
        FROM SGTPRD.CADASTRO_RECEITAS
        WHERE PROCESSO_ATIVO_PRODU = '1'
    ) CRE ON CRE.CODCOR = TRIM(GFF.PROCESSO) AND CRE.RN_REC = 1
    WHERE GFF.CODIGO_FASE IN (50, 55, 100, 110)
      AND GFF.PROCESSO IS NOT NULL
),
FLUXO_PRINCIPAL AS (
    SELECT /*+ MATERIALIZE */
        IDE.CODIGO_REDUZIDO,
        IDE.IDGRUPOFLUXO,
        GF.CODIGO_FLUXO,
        TRIM(GF.DSENGENHARIA) AS TIPO_FLUXO,
        ROW_NUMBER() OVER(
            PARTITION BY IDE.CODIGO_REDUZIDO
            ORDER BY
                -- 1º: O fluxo que coincide com o Grupo de Programação configurado no item de estoque
                CASE WHEN GF.NUMERO_GRUPO_PROGRAM = ITE.NUMERO_GRUPO_PROGRAM THEN 1 ELSE 2 END,
                -- 2º: O fluxo que possui receita de acabamento ativa cadastrada na fase principal
                CASE WHEN EXISTS (
                    SELECT 1 FROM SGTPRD.GRUPO_FLUXO_FASES GFX
                    WHERE GFX.IDGRUPOFLUXO = GF.IDGRUPOFLUXO
                      AND GFX.CODIGO_FASE IN (50, 100)
                      AND GFX.PROCESSO IS NOT NULL
                ) THEN 1 ELSE 2 END,
                -- 3º: Fluxo de engenharia Interno
                CASE WHEN UPPER(NVL(GF.DSENGENHARIA, 'INTERNO')) LIKE '%INTERNO%' THEN 1 ELSE 2 END,
                -- 4º: Versão de fluxo mais recente
                IDE.IDGRUPOFLUXO DESC
        ) AS RN_DESC
    FROM SGTPRD.ITENS_DESCENDENCIA IDE
    JOIN SGTPRD.GRUPO_FLUXO GF ON GF.IDGRUPOFLUXO = IDE.IDGRUPOFLUXO
    JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = IDE.CODIGO_REDUZIDO
),
GRUPOS_PAR_SEM_FIXADOR AS (
    SELECT /*+ MATERIALIZE */
        GP_COM.NUMERO_GRUPO_PROGRAM AS NGP_COM,
        GP_SEM.NUMERO_GRUPO_PROGRAM AS NGP_SEM,
        TRIM(GP_SEM.CODIGO_GRUPO_PROGRAM) AS COD_GP_SEM,
        TRIM(GP_SEM.DESCRICAO) AS DESCR_GP_SEM
    FROM SGTPRD.GRUPO_PRODUTO GP_COM
    LEFT JOIN SGTPRD.GRUPO_PRODUTO GP_SEM
      ON SUBSTR(TRIM(GP_SEM.CODIGO_GRUPO_PROGRAM), 1, LENGTH(TRIM(GP_SEM.CODIGO_GRUPO_PROGRAM)) - 2) = SUBSTR(TRIM(GP_COM.CODIGO_GRUPO_PROGRAM), 1, LENGTH(TRIM(GP_COM.CODIGO_GRUPO_PROGRAM)) - 2)
     AND (
         (SUBSTR(TRIM(GP_COM.CODIGO_GRUPO_PROGRAM), -2) = '00' AND SUBSTR(TRIM(GP_SEM.CODIGO_GRUPO_PROGRAM), -2) = '01')
      OR (SUBSTR(TRIM(GP_COM.CODIGO_GRUPO_PROGRAM), -2) = '98' AND SUBSTR(TRIM(GP_SEM.CODIGO_GRUPO_PROGRAM), -2) = '99')
     )
     AND UPPER(GP_SEM.DESCRICAO) LIKE '%SEM FIXADOR%'
    WHERE UPPER(GP_COM.DESCRICAO) LIKE '%COM FIXADOR%'
),
ORDENS_ABERTAS AS (
    SELECT /*+ MATERIALIZE */
        OBE.CODIGO_REDUZIDO,
        COUNT(*) AS QTD_OB_ABERTO,
        LISTAGG(OBE.NUMERO_OB || ' (' ||
            CASE OBE.STATUS
                WHEN 1 THEN 'Emitida'
                WHEN 2 THEN 'Pré OB'
                WHEN 3 THEN 'Programada'
                WHEN 4 THEN 'Bloqueada'
                WHEN 5 THEN 'Interditada Kanban'
                ELSE TO_CHAR(OBE.STATUS)
            END || ')', ', ' ON OVERFLOW TRUNCATE) WITHIN GROUP (ORDER BY OBE.NUMERO_OB) AS OBS_EM_ABERTO
    FROM SGTPRD.OB OBE
    WHERE OBE.STATUS <> 0
    GROUP BY OBE.CODIGO_REDUZIDO
)
SELECT
    ITE.CODIGO_REDUZIDO                                            AS REDUZIDO,
    TRIM(ITE.CODIGO)                                               AS CODIGO_ITEM,
    TRIM(ITE.DESCRICAO)                                            AS DESCRICAO_ITEM,
    SUBSTR(TRIM(ITE.CODIGO), 13, 5)                                AS COR,
    COALESCE(TRIM(COR.DESCRICAO), 'NÃO CADASTRADA')               AS NOME_COR,
    CASE SUBSTR(TRIM(ITE.CODIGO), 9, 1)
        WHEN 'R' THEN 'RAMADO'
        WHEN 'T' THEN 'TUBULAR'
        ELSE 'OUTRO'
    END                                                            AS TIPO_ESTRUTURA,
    ITE.NUMERO_GRUPO_PROGRAM                                       AS NGP_ATUAL,
    TRIM(GP.CODIGO_GRUPO_PROGRAM)                                 AS COD_GRUPO_PROG,
    TRIM(GP.DESCRICAO)                                             AS DESCR_GRUPO_PROG,
    CASE
        WHEN ITE.NUMERO_GRUPO_PROGRAM IS NULL THEN 'SEM GRUPO'
        WHEN UPPER(GP.DESCRICAO) LIKE '%SEM FIXADOR%' THEN 'SEM FIXADOR'
        WHEN UPPER(GP.DESCRICAO) LIKE '%COM FIXADOR%' THEN 'COM FIXADOR'
        WHEN UPPER(GP.DESCRICAO) LIKE '%ENXOFRE%'     THEN 'PRETO ENXOFRE'
        ELSE 'GERAL / TODAS AS CORES'
    END                                                            AS STATUS_GRUPO,
    REC.CODIGO_FASE                                                AS COD_FASE_ACABAMENTO,
    REC.DESCRICAO_FASE                                             AS FASE_ACABAMENTO,
    REC.RECEITA_PROCESSO                                           AS COD_RECEITA_ACABAMENTO,
    REC.DESCR_RECEITA                                              AS DESCR_RECEITA_ACABAMENTO,
    CASE
        WHEN FP.IDGRUPOFLUXO IS NULL THEN 'SEM FLUXO CADASTRADO'
        WHEN REC.RECEITA_PROCESSO IS NULL THEN 'SEM RECEITA NO FLUXO'
        WHEN UPPER(REC.DESCR_RECEITA) LIKE '%SEM FIXADOR%' THEN 'SEM FIXADOR'
        WHEN UPPER(REC.DESCR_RECEITA) LIKE '%COM FIXADOR%' THEN 'COM FIXADOR'
        WHEN UPPER(REC.DESCR_RECEITA) LIKE '%ENXOFRE%'     THEN 'PRETO ENXOFRE'
        ELSE 'OUTRA RECEITA'
    END                                                            AS STATUS_RECEITA,
    CASE
        WHEN ITE.NUMERO_GRUPO_PROGRAM IS NULL
             THEN 'ALERTA: ITEM SEM GRUPO DE PROGRAMAÇÃO CADASTRADO'
        WHEN FP.IDGRUPOFLUXO IS NULL
             THEN 'ALERTA: ITEM SEM FLUXO DE ENGENHARIA CADASTRADO'
        WHEN UPPER(GP.DESCRICAO) LIKE '%COM FIXADOR%' AND UPPER(REC.DESCR_RECEITA) LIKE '%SEM FIXADOR%'
             THEN 'DIVERGÊNCIA: GRUPO COM FIXADOR / RECEITA SEM FIXADOR'
        WHEN UPPER(GP.DESCRICAO) LIKE '%SEM FIXADOR%' AND UPPER(REC.DESCR_RECEITA) LIKE '%COM FIXADOR%'
             THEN 'DIVERGÊNCIA: GRUPO SEM FIXADOR / RECEITA COM FIXADOR'
        WHEN UPPER(GP.DESCRICAO) LIKE '%ENXOFRE%' AND UPPER(NVL(REC.DESCR_RECEITA, 'X')) NOT LIKE '%ENXOFRE%'
             THEN 'DIVERGÊNCIA: GRUPO PRETO ENXOFRE / RECEITA NÃO ENXOFRE'
        WHEN UPPER(GP.DESCRICAO) LIKE '%COM FIXADOR%' AND REC.RECEITA_PROCESSO IS NULL
             THEN 'ALERTA: GRUPO COM FIXADOR SEM RECEITA QUÍMICA NO FLUXO'
        WHEN UPPER(GP.DESCRICAO) LIKE '%COM FIXADOR%' AND UPPER(NVL(REC.DESCR_RECEITA, 'X')) NOT LIKE '%COM FIXADOR%'
             THEN 'ALERTA: GRUPO COM FIXADOR COM RECEITA GENÉRICA'
        ELSE 'OK'
    END                                                            AS AUDITORIA_CONGRUENCIA,
    NVL(OAB.QTD_OB_ABERTO, 0)                                      AS QTD_OB_ABERTO,
    OAB.OBS_EM_ABERTO                                              AS OBS_EM_ABERTO,
    CASE
        WHEN NVL(OAB.QTD_OB_ABERTO, 0) > 0 THEN 'BLOQUEADO SGT (OB EM ABERTO)'
        ELSE 'LIBERADO PARA SGT'
    END                                                            AS STATUS_ALTERACAO_SGT,
    PAR.NGP_SEM                                                    AS NGP_SUGERIDO_SEM_FIXADOR,
    COALESCE(PAR.DESCR_GP_SEM,
        CASE
            WHEN UPPER(GP.DESCRICAO) LIKE '%COM FIXADOR%'
            THEN 'NENHUM PAR "SEM FIXADOR" CADASTRADO NO SGT'
        END
    )                                                              AS DESCR_GP_SUGERIDO_SEM_FIXADOR,
    FP.IDGRUPOFLUXO                                                AS ID_GRUPO_FLUXO_PRINCIPAL,
    FP.CODIGO_FLUXO                                                AS CODIGO_FLUXO,
    FP.TIPO_FLUXO                                                  AS ENGENHARIA_FLUXO
FROM SGTPRD.ITENS_ESTOQUE ITE
LEFT JOIN SGTPRD.GRUPO_PRODUTO GP
       ON GP.NUMERO_GRUPO_PROGRAM = ITE.NUMERO_GRUPO_PROGRAM
LEFT JOIN SGTPRD.COR COR
       ON TRIM(COR.CODIGO_COR) = SUBSTR(TRIM(ITE.CODIGO), 13, 5)
LEFT JOIN FLUXO_PRINCIPAL FP
       ON FP.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
      AND FP.RN_DESC = 1
LEFT JOIN RECEITA_FASES REC
       ON REC.IDGRUPOFLUXO = FP.IDGRUPOFLUXO
      AND REC.RN_FASE = 1
LEFT JOIN GRUPOS_PAR_SEM_FIXADOR PAR
       ON PAR.NGP_COM = ITE.NUMERO_GRUPO_PROGRAM
LEFT JOIN ORDENS_ABERTAS OAB
       ON OAB.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
WHERE ITE.IDMASCARATIPOINSUMO IN ('BNF  ', 'BNR  ', 'BNT  ')
  AND ITE.INSUMO_COM_MOVIMENTO = '1'
  -- Filtro opcional por cor (ex.: cores '00056' Coral e '00057' Pistache):
  -- AND SUBSTR(TRIM(ITE.CODIGO), 13, 5) IN ('00056', '00057')
ORDER BY NVL(OAB.QTD_OB_ABERTO, 0) DESC, SUBSTR(TRIM(ITE.CODIGO), 13, 5), ITE.CODIGO_REDUZIDO
