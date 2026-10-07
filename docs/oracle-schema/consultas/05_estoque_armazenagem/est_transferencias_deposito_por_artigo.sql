/* =============================================================================
OBJETIVO: Transfência Depósito (Por Artigo)
DOMÍNIO: 05_estoque_armazenagem
ARQUIVO ORIGINAL: Comandos SQL - CR\Transfência Depósito (Por Artigo).sql
TIPO: Estoque e Depósitos
PARÂMETROS / BINDS: :00, :01, :59, :MI, :SS
TABELAS PRINCIPAIS: SGTPRD.GERAMOVIMENTOESTOQUE, SGTPRD.ITENS_ESTOQUE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
REVISÃO (20/09/2026 - Onda 3): Header corrigido — VW_PI_CBESB01_MOV_EST removida (body já usa GERAMOVIMENTOESTOQUE diretamente desde refatoração anterior).
============================================================================= */

SELECT
    CASE
        WHEN GME.CDDEPOSITO = 90
         AND GME.TIOPERACAO  = 2   -- Saída
         AND GME.NRTIPOMOVIMENTO = 15 THEN 'MALHARIA'
        WHEN GME.CDDEPOSITO = 95
         AND GME.TIOPERACAO  = 1   -- Entrada
         AND GME.NRTIPOMOVIMENTO = 14 THEN 'MALHARIA'
        ELSE ''
    END                          AS SETOR,
    GME.CDREDUZIDO               AS REDUZ,
    TRIM(ITE.DESCRICAO)          AS DESCR_ITEM,
    SUM(CASE WHEN GME.TIOPERACAO = 2 THEN GME.QTMOVIMENTO ELSE 0 END) AS QT_KG_SAIDA_ESTOQUE_90,
    SUM(CASE WHEN GME.TIOPERACAO = 1 THEN GME.QTMOVIMENTO ELSE 0 END) AS QT_KG_ENTRADA_ESTOQUE_95
FROM SGTPRD.GERAMOVIMENTOESTOQUE GME
JOIN SGTPRD.ITENS_ESTOQUE        ITE ON ITE.CODIGO_REDUZIDO = GME.CDREDUZIDO
WHERE GME.CDFILIAL              = 1
  AND GME.DTDOCUMENTO          >= TRUNC(SYSDATE - 15)
  AND GME.CDDEPOSITO           IN (90, 95)
  AND ITE.TIPO_ITEM            IN (9)            -- Fio / malha
  AND GME.TIOPERACAO           IN (1, 2)
  AND GME.NRTIPOMOVIMENTO      IN (14, 15)
  AND GME.STMOVCONFIRMADO       = 1
  AND ITE.STATUS_ENGENHARIA    <> 1              -- Item ativo
GROUP BY
    CASE
        WHEN GME.CDDEPOSITO = 90
         AND GME.TIOPERACAO  = 2
         AND GME.NRTIPOMOVIMENTO = 15 THEN 'MALHARIA'
        WHEN GME.CDDEPOSITO = 95
         AND GME.TIOPERACAO  = 1
         AND GME.NRTIPOMOVIMENTO = 14 THEN 'MALHARIA'
        ELSE ''
    END,
    GME.CDREDUZIDO,
    TRIM(ITE.DESCRICAO)
ORDER BY 4 DESC
FETCH FIRST 500 ROWS ONLY