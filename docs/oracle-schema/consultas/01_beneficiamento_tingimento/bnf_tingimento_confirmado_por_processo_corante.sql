/* =============================================================================
OBJETIVO: OB_s com tingimento confirmado de determinado processo ou corante
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s com tingimento confirmado de determinado processo ou corante.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.COML_TIPOSCOR, SGTPRD.COR, SGTPRD.ENGEITEMESTOCOR, SGTPRD.ITENS_ESTOQUE, SGTPRD.MOVTO_RECEITA, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.PKGUTIL0001
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. 100% nativa sem views. Execução somente leitura salvo se DML restrito.
AUDITORIA (29/09/2026): os químicos 54 e 14381 são uma sonda pontual; último uso em
  MOVTO_RECEITA: 54 = 2024-04-19, 14381 = 2023-06-13. Em janelas menores a consulta fica
  vazia por ausência de uso, não por defeito.
============================================================================= */

SELECT BASE.NR_ORDEM,
       BASE.COD_ARTIGO,
       BASE.COD_COR,
       BASE.DESCR_TIPOCOR,
       BASE.DESCR_PRODUTO,
       SUM(BASE.QT_OB_CRU) QT_KG,
       SUM(BASE.QUIMICO_USADO) QUIMICO_USADO,
       BASE.DURACAO
  FROM (
        SELECT OBS.*,
               CASE WHEN R.SEQUENCIAFASEOB = 0 THEN (OBS.RELACAOCONSUMOGRUPO * R.QUANTIDADEPESADA)
                 ELSE R.QUANTIDADEPESADA
                   END QUIMICO_USADO, 
               R.CODINSREDUZIDO,
               (SELECT TRIM(ITE.DESCRICAO) FROM SGTPRD.ITENS_ESTOQUE ITE WHERE ITE.CODIGO_REDUZIDO = R.CODINSREDUZIDO) DESCR_ITEM
          FROM (
                SELECT SUBSTR(ITE.CODIGO, 4, 5) AS COD_ARTIGO,
                       SUBSTR(ITE.CODIGO, 13, 5) AS COD_COR,
                       TRIM(TCO.DESCRICAO) AS DESCR_TIPOCOR,
                       TRIM(ITE.DESCRICAO) AS DESCR_PRODUTO,
                       OBF.NUMERO_OB,
                       OBF.CODIGO_GRUPO,
                       OBF.NUMEROORDEMMOVIMENTO NR_ORDEM,
                       OBF.SEQUENCIAORDEMMOVIME SEQ_TING,
                       OBF.RELACAOCONSUMOGRUPO,
                       ROUND(SUM(OBP.KILOS),2) QT_OB_CRU,
                       DATE '1996-01-01' + OBF.TEMPO_INICIAL_CONFIR / 1440 HORA_TING_INICIADO,
                       DATE '1996-01-01' + OBF.TEMPO_FINAL_CONFIRMA / 1440 HORA_TING_CONFIRMADO,
                       ROUND((OBF.TEMPO_FINAL_CONFIRMA - OBF.TEMPO_INICIAL_CONFIR) / 60, 2) DURACAO
                  FROM SGTPRD.OB_FASES       OBF
                  JOIN SGTPRD.OB_PRODUTO     OBP ON OBP.NUMERO_OB = OBF.NUMERO_OB
                  JOIN SGTPRD.ITENS_ESTOQUE  ITE ON ITE.CODIGO_REDUZIDO = OBP.CODPRO_REDUZIDO
                  LEFT JOIN SGTPRD.ENGEITEMESTOCOR EGC ON EGC.CDREDUZIDO = ITE.CODIGO_REDUZIDO
                  LEFT JOIN SGTPRD.COR             COO ON COO.CODIGO_COR = EGC.CDCOR
                  LEFT JOIN SGTPRD.COML_TIPOSCOR   TCO ON TCO.TIPOCOR = COO.TIPOCOR
                 WHERE OBF.CODIGO_FASE = 40
                 GROUP BY SUBSTR(ITE.CODIGO, 4, 5),
                          SUBSTR(ITE.CODIGO, 13, 5),
                          TRIM(TCO.DESCRICAO),
                          TRIM(ITE.DESCRICAO),
                          OBF.NUMEROORDEMMOVIMENTO,
                          OBF.SEQUENCIAORDEMMOVIME,
                          OBF.RELACAOCONSUMOGRUPO,
                          OBF.NUMERO_OB,
                          OBF.CODIGO_GRUPO,
                          OBF.TEMPO_INICIAL_CONFIR,
                          OBF.TEMPO_FINAL_CONFIRMA
               ) OBS,
               SGTPRD.MOVTO_RECEITA R
         WHERE R.NUMEROORDEM = OBS.NR_ORDEM
           AND R.SEQUENCIAFASEOB = OBS.SEQ_TING
           -- Janela: últimos 3 anos (antes: desde 01/08/2022, sem fim)
           AND OBS.HORA_TING_CONFIRMADO >= TRUNC(SYSDATE) - 1095
           AND R.CODINSREDUZIDO IN (54, 14381) -- PRODUTO QUIMICO ESPECIFICO
         ORDER BY R.QUANTIDADEPESADA DESC
        ) BASE
 GROUP BY BASE.NR_ORDEM,
          BASE.COD_ARTIGO,
          BASE.COD_COR,
          BASE.DESCR_TIPOCOR,
          BASE.DESCR_PRODUTO,
          BASE.DURACAO
 ORDER BY 4 DESC;
