-- ================================================================================
-- OBJETIVO: Diagnóstico contábil de ordens de programação de terceirização com ambiguidade ativa de NF
-- DOMÍNIO: 08_faccao_terceirizacao
-- TIPO: Auditoria/Sentinela
-- GRÃO: Chave da Programação (NR_NF textual da programação + CD_REDUZIDO cru)
-- PARÂMETROS / BINDS: Nenhum (varredura histórica completa sem corte arbitrário de data)
-- TABELAS PRINCIPAIS: SGTPRD.OB, SGTPRD.PEDPRODUCAOOB, SGTPRD.OFORDENS, SGTPRD.OFPEDIDO,
--                     SGTPRD.ITENSPEDIDOQTDES, SGTPRD.ITENSPEDIDOGRADE, SGTPRD.ITENSPEDIDOCOMERCIAL,
--                     SGTPRD.PEDIDOCOMERCIAL, SGTPRD.OB_PRODUTO, SGTPRD.LOTE_ITENS_NOTA_ENTR,
--                     SGTPRD.GERAPECANOTAENTRADA, SGTPRD.GERAPECASPRODUTO
-- REGRAS CHAVE:
--   1. Grão estritamente único por ordem programada (1 linha por programação).
--   2. Avalia NFs candidatas considerando exclusivamente SALDO_FISICO > 0 no pátio.
--   3. Identifica programações com colisão ativa (QTD_NFS_CANDIDATAS_PROG >= 2).
--   4. Exibe a quantidade bloqueada (QT_PECA_PROG_BLOQUEADA) de forma aditivamente segura,
--      permitindo SUM() direto em ferramentas de BI e PCP sem duplicação de peças.
-- STATUS: HOMOLOGADA, BLINDADA E CONGELADA PARA PRODUÇÃO
-- ================================================================================

WITH
/*
================================================================================
1. LOTES ELEGÍVEIS DE FACÇÃO (HISTÓRICO COMPLETO)
   - Fornecedor Categoria 1, Itens Tipo 9 (Tecido Cru), Qualidade 1, Depósito 95
================================================================================
*/
lotes_elegiveis AS (
    SELECT /*+ MATERIALIZE */
        LOT.ID AS ID_LOTE,
        LOT.NUMERO_NOTA,
        LOT.SERIE_NOTA,
        LOT.IDPESSOAFJ,
        LOT.CODINSREDUZIDO,
        LOT.VOLUMES,
        LOT.STFINALIZACAO,
        MNE.DTENTRADA,
        TRIM(PES.NOMEFANTASIA) AS NM_FORNECEDOR,
        TRIM(MAX(ITE.CODIGO_ALTERNATIVO)) AS CD_ALTERNATIVO,
        TRIM(MAX(ITE.DESCRICAO)) AS DS_PRODUTO,
        COUNT(GPN.IDPECASPRODUTO) AS TOTAL_PECAS_LOTE
    FROM SGTPRD.LOTE_ITENS_NOTA_ENTR LOT
    INNER JOIN SGTPRD.ITENS_ESTOQUE ITE 
        ON ITE.CODIGO_REDUZIDO = LOT.CODINSREDUZIDO
    INNER JOIN SGTPRD.MESTRE_NOTA_ENTRADA MNE 
        ON MNE.NUMERO_NOTA = LOT.NUMERO_NOTA
       AND MNE.SERIE_NOTA = LOT.SERIE_NOTA
       AND MNE.IDPESSOAFJ_CLIENTE = LOT.IDPESSOAFJ
    INNER JOIN SGTPRD.PESSOASFJ PES 
        ON PES.IDPESSOAFJ = MNE.IDPESSOAFJ_CLIENTE
    LEFT JOIN SGTPRD.GERAPECANOTAENTRADA GPN 
        ON GPN.IDLOTEITENSNFE = LOT.ID
    LEFT JOIN SGTPRD.GERAPECASPRODUTO GPP 
        ON GPP.IDPECASPRODUTO = GPN.IDPECASPRODUTO
    WHERE PES.IDCATEGORIFORNECEDOR = 1
      AND ITE.TIPO_ITEM = 9
      AND LOT.QUALIDADE = 1
      AND EXISTS (
          SELECT 1 
          FROM SGTPRD.ITENS_NOTA_ENTRADA INE
          WHERE INE.NUMERO_NOTA = LOT.NUMERO_NOTA
            AND INE.SERIE_NOTA = LOT.SERIE_NOTA
            AND INE.IDPESSOAFJ = LOT.IDPESSOAFJ
            AND INE.CODINSREDUZIDO = LOT.CODINSREDUZIDO
            AND INE.DEPOSITO = 95
      )
    GROUP BY 
        LOT.ID, LOT.NUMERO_NOTA, LOT.SERIE_NOTA, LOT.IDPESSOAFJ, LOT.CODINSREDUZIDO,
        LOT.VOLUMES, LOT.STFINALIZACAO, MNE.DTENTRADA, TRIM(PES.NOMEFANTASIA)
),

/*
================================================================================
2. CONSOLIDAÇÃO DO GRÃO POR NOTA / ITEM E CÁLCULO DE QT_PECA_NF LOTE A LOTE
================================================================================
*/
itens_lote_resumo AS (
    SELECT
        LE.NUMERO_NOTA,
        LE.SERIE_NOTA,
        LE.IDPESSOAFJ,
        LE.CODINSREDUZIDO,
        MAX(LE.DTENTRADA) AS DTENTRADA,
        MAX(LE.NM_FORNECEDOR) AS NM_FORNECEDOR,
        MAX(LE.CD_ALTERNATIVO) AS CD_ALTERNATIVO,
        MAX(LE.DS_PRODUTO) AS DS_PRODUTO,
        TO_CHAR(LE.NUMERO_NOTA) AS NUMERO_NOTA_STR,
        SUM(CASE 
            WHEN LE.STFINALIZACAO = 2 AND LE.TOTAL_PECAS_LOTE > 0 THEN LE.TOTAL_PECAS_LOTE
            ELSE LE.VOLUMES
        END) AS QT_PECA_NF
    FROM lotes_elegiveis LE
    GROUP BY LE.NUMERO_NOTA, LE.SERIE_NOTA, LE.IDPESSOAFJ, LE.CODINSREDUZIDO
),

/*
================================================================================
3. PEÇAS FÍSICAS ELEGÍVEIS E VÍNCULO COM OB (EXISTS BLINDADO)
================================================================================
*/
pecas_elegiveis AS (
    SELECT /*+ MATERIALIZE */
        GPN.NUMERO_NOTA,
        GPN.SERIE_NOTA,
        GPN.IDPESSOAFJ,
        GPN.CODINSREDUZIDO,
        GPN.IDPECASPRODUTO,
        GPP.STPECAPRODUTO,
        GPP.PADRAO_QUALIDADE_SIN,
        CASE WHEN EXISTS (
            SELECT 1 
            FROM SGTPRD.GERAPECAORIGEMOB ORI 
            WHERE ORI.IDPECASPRODUTO = GPN.IDPECASPRODUTO
        ) THEN 1 ELSE 0 END AS TEM_OB
    FROM SGTPRD.GERAPECANOTAENTRADA GPN
    INNER JOIN lotes_elegiveis LE 
        ON LE.ID_LOTE = GPN.IDLOTEITENSNFE
    INNER JOIN SGTPRD.GERAPECASPRODUTO GPP 
        ON GPP.IDPECASPRODUTO = GPN.IDPECASPRODUTO
),

/*
================================================================================
4. ÚLTIMO MOVIMENTO CAUSAL RELEVANTE POR PEÇA (FILTRO OTIMIZADO)
================================================================================
*/
movimentos_causais AS (
    SELECT /*+ LEADING(PE GPM GME TPM) USE_NL(GPM GME TPM) */
        PE.IDPECASPRODUTO,
        MAX(GME.NRTIPOMOVIMENTO) KEEP (DENSE_RANK LAST ORDER BY GME.DTDOCUMENTO, GME.ID) AS ULTIMO_MOV,
        MAX(TPM.MOVIMENTONOTAFISCAL) KEEP (DENSE_RANK LAST ORDER BY GME.DTDOCUMENTO, GME.ID) AS MOV_NF
    FROM pecas_elegiveis PE
    INNER JOIN SGTPRD.GERAPECAMOVIMENTO GPM 
        ON GPM.IDPECASPRODUTO = PE.IDPECASPRODUTO
    INNER JOIN SGTPRD.GERAMOVIMENTOESTOQUE GME 
        ON GME.ID = GPM.NUMERO_MOVIMENTO
    INNER JOIN SGTPRD.TIPO_MOVIMENTO TPM 
        ON TPM.NUM_TIPO_MOVIMENTO = GME.NRTIPOMOVIMENTO
    WHERE PE.TEM_OB = 0 
      AND PE.STPECAPRODUTO <> 0
      AND GME.TIOPERACAO = 2 
      AND GME.STGERAESTOBLOQ = '0'
      AND (
          GME.NRTIPOMOVIMENTO IN (145, 670, 945, 695, 55)
          OR (GME.NRTIPOMOVIMENTO IN (23, 50, 157) AND TPM.MOVIMENTONOTAFISCAL = 1)
      )
    GROUP BY PE.IDPECASPRODUTO
),

/*
================================================================================
5. CLASSIFICAÇÃO FÍSICA MUTUAMENTE EXCLUSIVA DE CADA PEÇA
================================================================================
*/
classificacao_pecas AS (
    SELECT 
        PE.NUMERO_NOTA,
        PE.SERIE_NOTA,
        PE.IDPESSOAFJ,
        PE.CODINSREDUZIDO,
        PE.IDPECASPRODUTO,
        CASE 
            WHEN PE.TEM_OB = 1 THEN 'UTIL_OB'
            WHEN PE.STPECAPRODUTO = 0 AND PE.PADRAO_QUALIDADE_SIN = 1 THEN 'SALDO_DISPONIVEL'
            WHEN MC.ULTIMO_MOV IN (145, 670, 945) THEN 'SAIDA_INV'
            WHEN MC.ULTIMO_MOV = 157 AND MC.MOV_NF = 1 THEN 'REM_INDUS'
            WHEN MC.ULTIMO_MOV = 50 AND MC.MOV_NF = 1 THEN 'TRANSF_FILIAL'
            WHEN MC.ULTIMO_MOV = 695 THEN 'TROCA_QUALIDADE'
            WHEN MC.ULTIMO_MOV = 23 AND MC.MOV_NF = 1 THEN 'FAT'
            WHEN MC.ULTIMO_MOV = 55 THEN 'TRANSF_ITEM'
            WHEN PE.PADRAO_QUALIDADE_SIN <> 1 THEN 'TROCA_QUALIDADE'
            ELSE 'OUTRAS_BAIXAS'
        END AS CATEGORIA_FISICA
    FROM pecas_elegiveis PE
    LEFT JOIN movimentos_causais MC 
        ON MC.IDPECASPRODUTO = PE.IDPECASPRODUTO
),

/*
================================================================================
6. TOTALIZADORES FÍSICOS POR ITEM DA NOTA FISCAL
================================================================================
*/
resumo_pecas_item AS (
    SELECT 
        NUMERO_NOTA,
        SERIE_NOTA,
        IDPESSOAFJ,
        CODINSREDUZIDO,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'UTIL_OB' THEN 1 END) AS QT_PECA_UTIL_OB,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'SAIDA_INV' THEN 1 END) AS QT_PECA_SAIDA_INV,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'REM_INDUS' THEN 1 END) AS QT_PECA_REM_INDUS,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'TRANSF_FILIAL' THEN 1 END) AS QT_PECA_TRANSF_FILIAL,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'TROCA_QUALIDADE' THEN 1 END) AS QT_PECA_TROCA_QUALIDADE,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'FAT' THEN 1 END) AS QT_PECA_FAT,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'TRANSF_ITEM' THEN 1 END) AS QT_PECA_TRANSF_ITEM,
        COUNT(CASE WHEN CATEGORIA_FISICA = 'OUTRAS_BAIXAS' THEN 1 END) AS QT_PECA_OUTRAS_BAIXAS
    FROM classificacao_pecas
    GROUP BY NUMERO_NOTA, SERIE_NOTA, IDPESSOAFJ, CODINSREDUZIDO
),

/*
================================================================================
7. PROGRAMAÇÃO DE OBS FUTURAS (NÃO APONTADAS)
================================================================================
*/
obs_candidatas AS (
    SELECT 
        OBE.NUMERO_OB, 
        OBE.CODIGO_REDUZIDO_CRU
    FROM SGTPRD.OB OBE
    WHERE OBE.STATUS <> 0 
      AND OBE.TIPO_ORDEM IN (0, 6) 
      AND OBE.CODIGO_REDUZIDO_CRU IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 
          FROM SGTPRD.GERAPECAORIGEMOB ORI 
          WHERE ORI.NUMERO_OB = OBE.NUMERO_OB
      )
),

pedidos_producao AS (
    SELECT DISTINCT
        OC.NUMERO_OB, 
        OC.CODIGO_REDUZIDO_CRU, 
        IPC.CD_DESENHO_CLIENTE
    FROM obs_candidatas OC
    INNER JOIN SGTPRD.PEDPRODUCAOOB PPOB 
        ON PPOB.NUMEROOB = OC.NUMERO_OB
    INNER JOIN SGTPRD.OFORDENS OFO 
        ON OFO.NUMEROPEDPRODUCAO = PPOB.NUMERO 
       AND OFO.REDUZIDO = PPOB.REDUZIDO
    INNER JOIN SGTPRD.OFPEDIDO OFP 
        ON OFP.NUMEROOF = OFO.NUMEROOF 
       AND OFP.NIVEL = OFO.NIVEL 
       AND OFP.REDUZIDO = OFO.REDUZIDO
    INNER JOIN SGTPRD.ITENSPEDIDOQTDES IPQ 
        ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
    INNER JOIN SGTPRD.ITENSPEDIDOGRADE IPG 
        ON IPG.IDITENSPEDIDOGRADE = IPQ.IDITEMPEDGRADE
    INNER JOIN SGTPRD.ITENSPEDIDOCOMERCIAL IPC 
        ON IPC.PEDIDO = IPG.PEDIDO 
       AND IPC.ITEMPEDIDO = IPG.ITEMPEDIDO
    INNER JOIN SGTPRD.PEDIDOCOMERCIAL PED 
        ON PED.PEDIDO = IPG.PEDIDO
    WHERE OFP.QUANTIDADE_ATUAL <> 0 
      AND PED.PEDIDOCLIENTE LIKE '%T' 
      AND REGEXP_LIKE(IPC.CD_DESENHO_CLIENTE, '^[0-9]+$')
),

obs_programacao AS (
    SELECT 
        PP.CD_DESENHO_CLIENTE,
        PP.CODIGO_REDUZIDO_CRU,
        SUM(OBP.TOTAL_PECAS) AS QT_PECA_PROG
    FROM pedidos_producao PP
    INNER JOIN SGTPRD.OB_PRODUTO OBP 
        ON OBP.NUMERO_OB = PP.NUMERO_OB
    GROUP BY PP.CD_DESENHO_CLIENTE, PP.CODIGO_REDUZIDO_CRU
),

/*
================================================================================
8. DADOS FÍSICOS REAIS DA NOTA FISCAL (CÁLCULO INDEPENDENTE DE PROGRAMAÇÃO)
================================================================================
*/
dados_fisicos AS (
    SELECT 
        ILR.NUMERO_NOTA AS NR_NF,
        ILR.CODINSREDUZIDO AS CD_REDUZIDO,
        ILR.QT_PECA_NF - (
            NVL(RPI.QT_PECA_UTIL_OB, 0) + NVL(RPI.QT_PECA_SAIDA_INV, 0) + 
            NVL(RPI.QT_PECA_REM_INDUS, 0) + NVL(RPI.QT_PECA_TRANSF_FILIAL, 0) + 
            NVL(RPI.QT_PECA_TROCA_QUALIDADE, 0) + NVL(RPI.QT_PECA_FAT, 0) + 
            NVL(RPI.QT_PECA_TRANSF_ITEM, 0) + NVL(RPI.QT_PECA_OUTRAS_BAIXAS, 0)
        ) AS SALDO_FISICO
    FROM itens_lote_resumo ILR
    LEFT JOIN resumo_pecas_item RPI 
        ON RPI.NUMERO_NOTA = ILR.NUMERO_NOTA
       AND RPI.SERIE_NOTA = ILR.SERIE_NOTA
       AND RPI.IDPESSOAFJ = ILR.IDPESSOAFJ
       AND RPI.CODINSREDUZIDO = ILR.CODINSREDUZIDO
),

/*
================================================================================
9. RESOLUÇÃO DEFENSIVA DE CANDIDATOS ATIVOS PARA PROGRAMAÇÃO
   - Avalia candidatos considerando estritamente NFs com SALDO_FISICO > 0.
================================================================================
*/
candidatos_programacao AS (
    SELECT 
        NR_NF,
        CD_REDUZIDO,
        COUNT(*) AS QTD_NFS_CANDIDATAS_PROG
    FROM dados_fisicos
    WHERE SALDO_FISICO > 0
    GROUP BY NR_NF, CD_REDUZIDO
),

/*
================================================================================
10. DIAGNÓSTICO CONTÁBIL DE PROGRAMAÇÃO (GRÃO: CHAVE DE PROGRAMAÇÃO)
    - Grão único por ordem programada: NR_NF_STR + CD_REDUZIDO
    - Assegura que SUM(QT_PECA_PROG_BLOQUEADA) totalize exatamente a quantidade
      real bloqueada, sem a duplicação provocada pelo grão de múltiplas NFs.
================================================================================
*/
diagnostico_programacao_ambigua AS (
    SELECT 
        OP.CD_DESENHO_CLIENTE AS NR_NF_STR,
        OP.CODIGO_REDUZIDO_CRU AS CD_REDUZIDO,
        OP.QT_PECA_PROG AS QT_PROGRAMACAO_ORIGINAL,
        NVL(CP.QTD_NFS_CANDIDATAS_PROG, 0) AS QTD_NFS_CANDIDATAS_PROG,
        CASE 
            WHEN NVL(CP.QTD_NFS_CANDIDATAS_PROG, 0) >= 2 THEN 1 
            ELSE 0 
        END AS TEM_AMBIGUIDADE,
        CASE 
            WHEN NVL(CP.QTD_NFS_CANDIDATAS_PROG, 0) >= 2 THEN OP.QT_PECA_PROG 
            ELSE 0 
        END AS QT_PECA_PROG_BLOQUEADA
    FROM obs_programacao OP
    LEFT JOIN candidatos_programacao CP
        ON TO_CHAR(CP.NR_NF) = OP.CD_DESENHO_CLIENTE
       AND CP.CD_REDUZIDO = OP.CODIGO_REDUZIDO_CRU
    WHERE OP.QT_PECA_PROG > 0
)

/*
===============================================================================
11. RELATÓRIO DIAGNÓSTICO DE PROGRAMAÇÕES AMBÍGUAS (PCP / BI)
    - Retorna exclusivamente as ordens com colisão ativa de notas no pátio
===============================================================================
*/
SELECT 
    NR_NF_STR,
    CD_REDUZIDO,
    QT_PROGRAMACAO_ORIGINAL,
    QTD_NFS_CANDIDATAS_PROG,
    QT_PECA_PROG_BLOQUEADA
FROM diagnostico_programacao_ambigua
WHERE TEM_AMBIGUIDADE = 1
ORDER BY NR_NF_STR, CD_REDUZIDO
