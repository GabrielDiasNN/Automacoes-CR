/* =============================================================================
OBJETIVO: Identificação de Produtos com Maior Desvio de Tempo entre o Real e o Previsto pela Engenharia, com Minutos por Tonelada
DOMÍNIO: 02_acabamento_preparacao
TIPO: Painel/KPI
GRÃO: CODPRO_REDUZIDO + RAMA (uma linha por artigo e rama, só com pelo menos 400 kg na janela)
PARÂMETROS / BINDS: Nenhum (janela dinâmica de 60 dias de produção)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE, SGTPRD.ITENS_ESTOQUE, SGTPRD.MAQUINA
CUIDADOS OPERACIONAIS: Somente leitura. Compara minutos reais com minutos previstos cadastrados na engenharia.
  Só entra apontamento concluído (STATUS = 0): linhas em execução ou na fila (STATUS 1 e 3) são programação
  e entravam como produção. As ramas vêm de MAQUINA (GRUPO RM001, SETOR 5). Não há custo em moeda nesta
  consulta: MINUTOS_POR_TONELADA mede tempo de máquina por tonelada. A velocidade é média ponderada pelo
  tempo real (SUM(VELOCIDADE * MIN_REAL) / SUM(MIN_REAL)), não a média simples das linhas.
  Ranking: as 50 maiores HORAS_PERDIDAS_DESVIO; o desvio pode ser negativo (mais rápido que a engenharia).
============================================================================= */

SELECT
    PR.CODPRO_REDUZIDO,
    SUBSTR(TRIM(ITE.DESCRICAO), 1, 38) AS ARTIGO,
    LTRIM(PR.NUMERO_MAQUINA, '0') AS RAMA,
    COUNT(DISTINCT PR.NUMERO_OB) AS TOTAL_LOTES,
    ROUND(SUM(PR.KILOS), 1) AS KG_TOTAL,
    ROUND(SUM(PR.METROS), 1) AS METROS_TOTAL,
    ROUND(SUM(PR.VELOCIDADE * PR.MIN_REAL) / NULLIF(SUM(PR.MIN_REAL), 0), 1) AS VELOCIDADE_REAL_M_MIN,
    ROUND(SUM(PR.MIN_REAL) / 60, 2) AS HORAS_CONSUMIDAS_REAIS,
    ROUND(SUM(PR.MIN_PREV) / 60, 2) AS HORAS_PREVISTAS_ENGENHARIA,
    -- Desvio absoluto de capacidade em horas
    ROUND((SUM(PR.MIN_REAL) - SUM(PR.MIN_PREV)) / 60, 2) AS HORAS_PERDIDAS_DESVIO,
    -- Consumo específico: minutos de máquina por tonelada de tecido
    ROUND(SUM(PR.MIN_REAL) / NULLIF(SUM(PR.KILOS) / 1000, 0), 1) AS MINUTOS_POR_TONELADA
FROM SGTPRD.BD_BNF_PRODUCAO_FASE PR
JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = PR.CODPRO_REDUZIDO
WHERE PR.NUMERO_MAQUINA IN (
          SELECT MAQ.NUMERO_MAQUINA
          FROM SGTPRD.MAQUINA MAQ
          WHERE MAQ.GRUPO = 'RM001'
            AND MAQ.SETOR = 5
      )
  AND PR.STATUS = 0
  AND PR.DATA_FIM >= TRUNC(SYSDATE) - 60
  AND PR.DATA_FIM <= TRUNC(SYSDATE)
  AND PR.KILOS > 0
  AND PR.MIN_REAL > 1
GROUP BY PR.CODPRO_REDUZIDO, ITE.DESCRICAO, PR.NUMERO_MAQUINA
HAVING SUM(PR.KILOS) >= 400
ORDER BY HORAS_PERDIDAS_DESVIO DESC
FETCH FIRST 50 ROWS ONLY;
