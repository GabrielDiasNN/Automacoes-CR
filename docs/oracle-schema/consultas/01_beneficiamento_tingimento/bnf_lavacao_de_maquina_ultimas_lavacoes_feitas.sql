/* =============================================================================
OBJETIVO: Lavação de Máquina - (Últimas lavações feitas)
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\Lavação de Máquina - (Últimas lavações feitas).sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO, SGTPRD.PARADAS_MAQUINA, SGTPRD.UNIDADE_PROGR_PROD
CUIDADOS OPERACIONAIS: Consulta 100% nativa sem views, filtrada pelo motivo BNF13 e tipo de máquina 19.
AUDITORIA (29/09/2026): DIAS_SEM_LAVAR tinha o sinal invertido (MAX(início) - SYSDATE, sempre
  negativo); agora SYSDATE - MAX(início) = dias desde o início da última lavação.
============================================================================= */

SELECT LTRIM(UPR.NUMERO_MAQUINA, '0')             AS MQ,
       MAX(UPR.DTTEMPOINICONFIRMADO)              AS DATA_HORA_INICIO,
       MAX(UPR.DTTEMPOFINALCONFIRMA)              AS DATA_HORA_FIM,
       ROUND(SYSDATE - MAX(UPR.DTTEMPOINICONFIRMADO), 2) AS DIAS_SEM_LAVAR
  FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
  JOIN SGTPRD.UP_ORDEM_MVTO       UMO ON UMO.NUMEROUP = UPR.NUMEROUP
  JOIN SGTPRD.PARADAS_MAQUINA     PMA ON PMA.NUMERO_PARADA = UMO.NUMEROORDEMREAL
  JOIN SGTPRD.UNIDADE_PROGR_PROD  UPP ON UPP.NUMEROUP = UPR.NUMEROUP
 WHERE UPP.TIPO_MAQUINA = 19
   AND PMA.CODIGO_PARADA = 'BNF13'
   AND UMO.CODIGOMOVIMENTO = 2
   AND UPR.EXCLUIDA = 0
   AND UPR.SETOR = 5
 GROUP BY LTRIM(UPR.NUMERO_MAQUINA, '0')
 ORDER BY MQ;
