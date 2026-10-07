/* =============================================================================
OBJETIVO: TOP 5 Produção Mensal por média de kg/dia
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: 09_pcp_kpis_gestao/pcp_top_5_producao_mensal.sql (Query #1)
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum (janela: últimos 12 meses)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.OB
CUIDADOS OPERACIONAIS: Consulta atômica desmembrada para execução individual.
OTIMIZAÇÃO: Filtro temporal indexado de 12 meses aplicado em ambas as partes da UNION ALL,
  permitindo uso de índice de data e eliminando timeouts recorrentes.
============================================================================= */

SELECT BASE.MES_ANO,
       TO_CHAR(SUM(BASE.QT_PROD), '999G999G990D00') AS QT_PROD
  FROM (
       -- 1ª parte: PI_REC IN (302, 401)
       SELECT TO_CHAR(VPF.DATA_FIM, 'MM/YYYY') AS MES_ANO,
              SUM(VPF.KILOS) AS QT_PROD
         FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
        WHERE VPF.PI_REC IN (302, 401)
          AND VPF.TIPO_DESTINO = 0
          AND VPF.DATA_FIM >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)
        GROUP BY TO_CHAR(VPF.DATA_FIM, 'MM/YYYY')

       UNION ALL

       -- 2ª parte: Máquina RM01 na 1ª passagem de sequência (RN=1)
       SELECT MES_ANO,
              SUM(KILOS) AS QT_PROD
         FROM (
              SELECT TO_CHAR(VPF.DATA_FIM, 'MM/YYYY') AS MES_ANO,
                     VPF.KILOS,
                     ROW_NUMBER() OVER (PARTITION BY VPF.NUMERO_OB, VPF.NUMERO_MAQUINA ORDER BY VPF.SEQUENCIA) AS RN
                FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
                JOIN SGTPRD.OB OBE 
                  ON OBE.NUMERO_OB = VPF.NUMERO_OB
               WHERE TRIM(VPF.NUMERO_MAQUINA) = 'RM01'
                 AND OBE.CODIGO_FLUXO IN (204, 302, 304, 305)
                 AND OBE.TIPO_ORDEM <> 6
                 AND VPF.TIPO_DESTINO = 0
                 AND VPF.DATA_FIM >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)
              )
        WHERE RN = 1
        GROUP BY MES_ANO
       ) BASE
 GROUP BY BASE.MES_ANO
 ORDER BY SUM(BASE.QT_PROD) DESC
 FETCH FIRST 5 ROWS ONLY
