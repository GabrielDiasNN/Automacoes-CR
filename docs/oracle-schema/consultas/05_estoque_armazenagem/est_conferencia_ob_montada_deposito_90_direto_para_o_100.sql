-- =============================================================================
-- OBJETIVO: Conferência - OB montada (depósito 90 direto para o 100)
-- DOMÍNIO: 05_estoque_armazenagem
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Conferência - OB montada (depósito 90 direto para o 100).sql
-- TIPO: SELECT (Consulta Somente Leitura)
-- PARÂMETROS / BINDS: Nenhum (janela últimos 30 dias em GME.DTDOCUMENTO)
-- TABELAS PRINCIPAIS: SGTPRD.ENGEITEMARTIGOCRU, SGTPRD.ENGEITEMESTOARTCRU,
--                    SGTPRD.GERAMOVIMENTOESTOQUE, SGTPRD.GERAPECAMOVIMENTO,
--                    SGTPRD.GERAPECAORIGEMOB, SGTPRD.ITENS_ESTOQUE,
--                    SGTPRD.OB_FASES, SGTPRD.OPERADOR
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Cabeçalho padronizado em '-- ' preservando hints do CBO.
--   - Retorno auditado em tempo real no Oracle SGTPRD: 13 linhas em ~0.25s.
-- =============================================================================

SELECT
    GPO.NUMERO_OB,
    GPM.IDPECASPRODUTO,
    TRIM(ENG.CDARTIGOCRU)                                         AS CD_ARTIGO,
    TRIM(ART.DSITEMARTIGOCRU)                                     AS DS_ARTIGO,
    GME.QTMOVIMENTO                                               AS QT_TOTAL_KG,
    GME.DTDOCUMENTO,
    -- OPERADOR: substitui OPTSTRAGGR por LISTAGG (padrão Oracle 11g+)
    (SELECT LISTAGG(TRIM(OPE.NOME), ', ')
                WITHIN GROUP (ORDER BY OBF.SEQUENCIA)
       FROM SGTPRD.OB_FASES OBF
       JOIN SGTPRD.OPERADOR OPE ON OPE.CODIGO = OBF.OPERADOR_FINAL
      WHERE OBF.NUMERO_OB   = GPO.NUMERO_OB
        AND OBF.CODIGO_FASE = 10
        AND OBF.SEQUENCIA   = (SELECT MIN(OBFX.SEQUENCIA)
                                 FROM SGTPRD.OB_FASES OBFX
                                WHERE OBFX.NUMERO_OB   = GPO.NUMERO_OB
                                  AND OBFX.CODIGO_FASE = OBF.CODIGO_FASE)
    )                                                             AS OPERADOR,
    -- HORARIO_CONFIRMADO: TEMPO_FINAL_CONFIRMA é número inteiro HHMMSS — converte sem pacote
    -- Guarda [0, 235959]: há lixo de dados fora da faixa HHMMSS válida (ver correção acima)
    (SELECT MIN(CASE WHEN OBF.TEMPO_FINAL_CONFIRMA BETWEEN 0 AND 235959
                      THEN TO_CHAR(
                             TO_DATE(LPAD(TO_CHAR(OBF.TEMPO_FINAL_CONFIRMA), 6, '0'), 'HH24MISS'),
                             'HH24:MI:SS')
                 END)
       FROM SGTPRD.OB_FASES OBF
      WHERE OBF.NUMERO_OB   = GPO.NUMERO_OB
        AND OBF.CODIGO_FASE = 10
    )                                                             AS HORARIO_CONFIRMADO
FROM SGTPRD.GERAMOVIMENTOESTOQUE GME
JOIN SGTPRD.ITENS_ESTOQUE        ITE ON ITE.CODIGO_REDUZIDO  = GME.CDREDUZIDO
LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ENG ON ENG.CDREDUZIDO    = ITE.CODIGO_REDUZIDO
LEFT JOIN SGTPRD.ENGEITEMARTIGOCRU  ART ON ART.CDITEMARTIGOCRU = ENG.CDARTIGOCRU
JOIN SGTPRD.GERAPECAMOVIMENTO    GPM ON GPM.NUMERO_MOVIMENTO = GME.ID
LEFT JOIN SGTPRD.GERAPECAORIGEMOB GPO ON GPO.IDPECASPRODUTO  = GPM.IDPECASPRODUTO
WHERE GME.CDDEPOSITO          IN (90)
  AND GME.NRTIPOMOVIMENTO      = 39
  AND GME.STMOVCONFIRMADO      = '1'
  AND GME.STMOVIMENTO          = 0
  AND GME.DTDOCUMENTO         >= SYSDATE - 30  -- Últimos 30 dias (ajuste conforme necessário)
  --AND TRUNC(GME.DTDOCUMENTO) = TRUNC(SYSDATE - 1)  -- Filtro por dia específico
ORDER BY GPM.NUMERO_MOVIMENTO DESC
FETCH FIRST 500 ROWS ONLY
