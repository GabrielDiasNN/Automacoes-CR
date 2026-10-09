/* =============================================================================
OBJETIVO: Testes de qualidade do registro de paradas e quebras de agulha da
          malharia. Mostra quais campos e padrões podem ser usados em análise.
DOMÍNIO: 03_malharia_teares
TIPO: Auditoria/Sentinela
GRÃO: TESTE (uma linha por teste; AGULHAS_POR_EVENTO tem uma linha por ano da janela)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
TABELAS PRINCIPAIS: SGTPRD.PARADAS_MAQUINA, SGTPRD.QUEBRA_AGULHA_MALHAR,
  SGTPRD.MAQUINA, SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
SAÍDA: uma linha por teste (TESTE, RESULTADO, LEITURA), exceto AGULHAS_POR_EVENTO, que sai
  uma linha por ano. Não é série de negócio.
TESTES:
  LOTE_INICIO_TURNO   dias em que pelo menos 80% das máquinas internas têm registro
                      de início de turno (MLC07). Não compara duração.
  PARADA_OPERADOR_PADRAO  participação do operador mais frequente nas paradas.
  CAMPOS_VAZIOS_PARADA    paradas sem lote de fio e paradas com grupo de produto.
                          Observação não é testada: o campo é numérico e vem zerado
                          (REGRAS_NEGOCIO.md, 5.4).
  QUEBRA_CODIGO_CONSTANTE participação do código de quebra mais frequente.
  QUEBRA_OPERADOR_PADRAO  participação do operador mais frequente nas quebras.
  AGULHAS_POR_EVENTO      média de agulhas por registro de quebra, por ano.
CUIDADOS OPERACIONAIS:
  - Um resultado de LEITURA = "SUSPEITO" indica campo ou padrão que não deve
    ser usado como fato. Ver a documentação de cada teste.
  - Escopo: teares internos (TIPO_MAQUINA 145/146 em unidade com EH_FACCAO = 'N').
  - Consulta de leitura. Execução somente leitura.
============================================================================= */

WITH PARAM AS (
    SELECT TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12), 'YYYYMMDD')) AS D_INI,
           TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYYMMDD'))                  AS D_FIM
      FROM DUAL
),
INTERNAS AS (
    SELECT DISTINCT MQI.NUMERO_MAQUINA
      FROM SGTPRD.MAQUINA MQI
      JOIN SGTPRD.GRUPO_MAQUINAS GMQ
        ON GMQ.GRUPO = MQI.GRUPO
       AND GMQ.SETOR = MQI.SETOR
      JOIN SGTPRD.UNIDADE_FABRIL UFM
        ON UFM.CODIGO_UNIDADE_FABRI = GMQ.UNIDADE_FABRIL
     WHERE MQI.TIPO_MAQUINA IN (145, 146)
       AND UFM.EH_FACCAO = 'N'
),
PARADAS AS (
    SELECT PM.NUMERO_MAQUINA,
           PM.DATA_INICIO,
           PM.CODIGO_PARADA,
           PM.CODIGO_OPERADOR,
           PM.LOTE_FIO_PRODUTO,
           PM.GRUPO_PRODUTO
      FROM PARAM
      JOIN SGTPRD.PARADAS_MAQUINA PM
        ON PM.SETOR = 4
       AND PM.DATA_INICIO >= PARAM.D_INI
       AND PM.DATA_INICIO <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = PM.NUMERO_MAQUINA
     WHERE PM.DATA_TERMINO IS NOT NULL
),
QUEBRAS AS (
    SELECT SUBSTR(TO_CHAR(Q.DATA_QUEBRA), 1, 4) AS ANO,
           SUBSTR(TO_CHAR(Q.DATA_QUEBRA), 1, 6) AS MES_REF,
           Q.NUMERO_MAQUINA,
           Q.COD_QUEBRA,
           Q.OPERADOR,
           Q.QUANTIDADE_AGULHAS
      FROM PARAM
      JOIN SGTPRD.QUEBRA_AGULHA_MALHAR Q
        ON Q.DATA_QUEBRA >= PARAM.D_INI
       AND Q.DATA_QUEBRA <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = Q.NUMERO_MAQUINA
),
LOTE_DIA AS (
    SELECT DATA_INICIO AS DIA,
           COUNT(DISTINCT NUMERO_MAQUINA) AS MAQ_COM_INICIO_TURNO
      FROM PARADAS
     WHERE CODIGO_PARADA = 'MLC07'
     GROUP BY DATA_INICIO
),
OPER_PARADA AS (
    SELECT CODIGO_OPERADOR, COUNT(*) AS N
      FROM PARADAS
     GROUP BY CODIGO_OPERADOR
),
OPER_QUEBRA AS (
    SELECT OPERADOR, COUNT(*) AS N
      FROM QUEBRAS
     GROUP BY OPERADOR
),
COD_QUEBRA AS (
    SELECT COD_QUEBRA, COUNT(*) AS N
      FROM QUEBRAS
     GROUP BY COD_QUEBRA
)
SELECT 'LOTE_INICIO_TURNO' AS TESTE,
       TO_CHAR(COUNT(*)) || ' dias com MLC07 em >= 80% das máquinas internas' AS RESULTADO,
       CASE WHEN COUNT(*) > 0 THEN 'SUSPEITO: registro em lote, não parada diária' ELSE 'OK' END AS LEITURA
  FROM LOTE_DIA
 WHERE MAQ_COM_INICIO_TURNO >= 0.8 * (SELECT COUNT(*) FROM INTERNAS)
UNION ALL
SELECT 'PARADA_OPERADOR_PADRAO',
       TO_CHAR(ROUND(100 * MAX(N) / NULLIF(SUM(N), 0), 1)) || '% dos registros no operador mais frequente',
       CASE WHEN 100 * MAX(N) / NULLIF(SUM(N), 0) > 50 THEN 'SUSPEITO: operador padrão' ELSE 'OK' END
  FROM OPER_PARADA
UNION ALL
SELECT 'CAMPOS_VAZIOS_PARADA',
       TO_CHAR(SUM(CASE WHEN TRIM(LOTE_FIO_PRODUTO) IS NULL THEN 1 ELSE 0 END)) || ' sem lote de fio de '
         || TO_CHAR(COUNT(*)) || ' paradas; ' ||
       TO_CHAR(SUM(CASE WHEN GRUPO_PRODUTO > 0 THEN 1 ELSE 0 END)) || ' com grupo de produto',
       CASE WHEN SUM(CASE WHEN GRUPO_PRODUTO > 0 THEN 1 ELSE 0 END) = 0 THEN 'SUSPEITO: sem produto na parada' ELSE 'OK' END
  FROM PARADAS
UNION ALL
SELECT 'QUEBRA_CODIGO_CONSTANTE',
       TO_CHAR(ROUND(100 * MAX(N) / NULLIF(SUM(N), 0), 1)) || '% no código mais frequente',
       CASE WHEN 100 * MAX(N) / NULLIF(SUM(N), 0) > 90 THEN 'SUSPEITO: código de quebra constante' ELSE 'OK' END
  FROM COD_QUEBRA
UNION ALL
SELECT 'QUEBRA_OPERADOR_PADRAO',
       TO_CHAR(ROUND(100 * MAX(N) / NULLIF(SUM(N), 0), 1)) || '% dos registros no operador mais frequente',
       CASE WHEN 100 * MAX(N) / NULLIF(SUM(N), 0) > 50 THEN 'SUSPEITO: operador padrão' ELSE 'OK' END
  FROM OPER_QUEBRA
UNION ALL
SELECT 'AGULHAS_POR_EVENTO_' || ANO || '_' || TO_CHAR(COUNT(DISTINCT MES_REF)) || 'M',
       TO_CHAR(ROUND(SUM(QUANTIDADE_AGULHAS) / NULLIF(COUNT(*), 0), 1)) || ' agulhas por registro ('
         || TO_CHAR(COUNT(*)) || ' registros em ' || TO_CHAR(COUNT(DISTINCT MES_REF)) || ' meses)',
       'Comparar só anos com meses equivalentes; mudança de registro possível'
  FROM QUEBRAS
 GROUP BY ANO
 ORDER BY 1;
