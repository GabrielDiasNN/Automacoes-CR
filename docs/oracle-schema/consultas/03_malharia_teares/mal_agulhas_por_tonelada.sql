/* =============================================================================
OBJETIVO: Consumo de agulhas por tonelada produzida e por máquina-dia, por tear
          interno (12 meses). Mede a condição das agulhas pela produção, não pelo volume
DOMÍNIO: 03_malharia_teares
TIPO: Painel/KPI
GRÃO: MAQUINA (uma linha por tear interno)
PARÂMETROS / BINDS: Nenhum. Janela = 12 meses fechados anteriores ao mês corrente.
TABELAS PRINCIPAIS: SGTPRD.QUEBRA_AGULHA_MALHAR, SGTPRD.GERAPECASPRODUTO,
  SGTPRD.GERAPECAORDEMMALHA, SGTPRD.ORDEM_PRODUCAO_MALHA, SGTPRD.MAQUINA,
  SGTPRD.GRUPO_MAQUINAS, SGTPRD.UNIDADE_FABRIL
COLUNAS:
  AGULHAS             soma de QUANTIDADE_AGULHAS no período.
  KG_PRODUZIDOS       kg de malha pela data de pesagem (ver CUIDADOS).
  DIAS_PRODUCAO       dias com peso da máquina.
  AGULHAS_POR_TON     AGULHAS / (KG_PRODUZIDOS / 1000).
  AGULHAS_POR_MAQ_DIA AGULHAS / DIAS_PRODUCAO.
  RANK_AGULHAS_TON    posição por agulhas por tonelada (1 = pior).
CUIDADOS OPERACIONAIS:
  - Pesagem defasada: kg e dias são pela data de pesagem (REGRAS_NEGOCIO.md, seção 5.2).
    O total do período é válido; o resultado por dia não é.
  - Em 2026 o registro de quebra mudou (mais agulhas por evento, menos eventos).
    Comparar agulhas entre anos com cautela. Ver mal_qualidade_registro_paradas.sql.
  - COD_AGULHA não é decodificado aqui; para análise por modelo, ver o cadastro.
  - Máquinas com produção e sem quebra de agulha entram com AGULHAS = 0 (antes ficavam
    de fora, e o kg total do período ficava 0,12% menor que o da malharia).
  - Verificado no SGTPRD (08/10/2026): a soma de AGULHAS bate com o total de quebras da
    janela e a soma de KG_PRODUZIDOS bate com o total de peças de malha interna.
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
AGULHAS AS (
    SELECT Q.NUMERO_MAQUINA,
           SUM(Q.QUANTIDADE_AGULHAS) AS AGULHAS
      FROM PARAM
      JOIN SGTPRD.QUEBRA_AGULHA_MALHAR Q
        ON Q.DATA_QUEBRA >= PARAM.D_INI
       AND Q.DATA_QUEBRA <  PARAM.D_FIM
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = Q.NUMERO_MAQUINA
     GROUP BY Q.NUMERO_MAQUINA
),
PRODUCAO AS (
    SELECT ORD.NUMERO_MAQUINA,
           COUNT(DISTINCT P.DATA_DA_ENTRADA_PECA) AS DIAS_PRODUCAO,
           ROUND(SUM(P.QTLIQUIDA), 0)             AS KG_PRODUZIDOS
      FROM PARAM
      JOIN SGTPRD.GERAPECASPRODUTO P
        ON P.DATA_DA_ENTRADA_PECA >= PARAM.D_INI
       AND P.DATA_DA_ENTRADA_PECA <  PARAM.D_FIM
       AND P.STPECAPRODUTO <> 12
      JOIN SGTPRD.GERAPECAORDEMMALHA GM
        ON GM.IDPECASPRODUTO = P.IDPECASPRODUTO
      JOIN SGTPRD.ORDEM_PRODUCAO_MALHA ORD
        ON ORD.NUMERO_ORDEM = GM.NUMERO_ORDEM_MALHA
      JOIN INTERNAS INTE
        ON INTE.NUMERO_MAQUINA = ORD.NUMERO_MAQUINA
     GROUP BY ORD.NUMERO_MAQUINA
),
UNIVERSO AS (
    SELECT NUMERO_MAQUINA FROM AGULHAS
    UNION
    SELECT NUMERO_MAQUINA FROM PRODUCAO
)
SELECT LTRIM(U.NUMERO_MAQUINA, '0')                                             AS MAQUINA,
       TRIM(M.GRUPO)                                                            AS GRUPO,
       TRIM(M.MODELO)                                                           AS MODELO,
       NVL(A.AGULHAS, 0)                                                        AS AGULHAS,
       NVL(PR.KG_PRODUZIDOS, 0)                                                 AS KG_PRODUZIDOS,
       NVL(PR.DIAS_PRODUCAO, 0)                                                 AS DIAS_PRODUCAO,
       ROUND(NVL(A.AGULHAS, 0) / NULLIF(PR.KG_PRODUZIDOS / 1000, 0), 1)         AS AGULHAS_POR_TON,
       ROUND(NVL(A.AGULHAS, 0) / NULLIF(PR.DIAS_PRODUCAO, 0), 1)                AS AGULHAS_POR_MAQ_DIA,
       RANK() OVER (ORDER BY NVL(A.AGULHAS, 0) / NULLIF(PR.KG_PRODUZIDOS / 1000, 0) DESC NULLS LAST)
                                                                                AS RANK_AGULHAS_TON
  FROM UNIVERSO U
  LEFT JOIN AGULHAS A
    ON A.NUMERO_MAQUINA = U.NUMERO_MAQUINA
  LEFT JOIN PRODUCAO PR
    ON PR.NUMERO_MAQUINA = U.NUMERO_MAQUINA
  JOIN SGTPRD.MAQUINA M
    ON M.NUMERO_MAQUINA = U.NUMERO_MAQUINA
 ORDER BY RANK_AGULHAS_TON, MAQUINA;
