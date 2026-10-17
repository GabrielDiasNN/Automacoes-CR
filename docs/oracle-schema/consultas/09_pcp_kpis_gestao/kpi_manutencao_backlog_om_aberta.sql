/* =============================================================================
OBJETIVO: Backlog de OMs de manutenção mecânica ainda não executadas, por família e faixa de idade.
DOMÍNIO: 09_pcp_kpis_gestao
TIPO: Painel/KPI (fotografia do momento, sem recorte mensal)
GRANULARIDADE: uma linha por família e faixa de idade
FONTE: SGTPRD.ORDEMMANUTENCAO (SITUACAO = 0, sem datas reais de execução).
FATOS CONFIRMADOS NO ORACLE (17/10/2026):
  - SITUACAO = 0 são as OMs não executadas: 194 nas OMs de TIPO_MANUTENCAO 'NT-%' solicitadas
    desde o início do mês de 12 meses atrás (17/10/2026), sem DTINICIO_REAL e sem DTTERMINO_REAL.
  - Dessas, 41 têm mais de 180 dias desde a solicitação.
  - A idade é a diferença entre hoje e DTSOLICITACAO, em dias.
LIMITES:
  - Só cobre OMs solicitadas nos últimos 12 meses. OMs mais antigas com SITUACAO = 0 ficam
    de fora; antes de ampliar a janela, confirmar com a manutenção se existem.
  - O significado da SITUACAO 4 (250 OMs com confirmação e sem datas reais) não está confirmado,
    então não entra no backlog.
PARÂMETROS / BINDS: nenhum (janela automática).
============================================================================= */
WITH OM_ABERTA AS (
    SELECT REGEXP_SUBSTR(OM.TIPO_MANUTENCAO, '^NT-[^ ]+')                AS TIPO_NT,
           TRUNC(SYSDATE) - TRUNC(OM.DTSOLICITACAO)                       AS IDADE_DIAS
      FROM SGTPRD.ORDEMMANUTENCAO OM
     WHERE OM.SITUACAO = 0
       AND OM.DTSOLICITACAO >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)
       AND OM.DTSOLICITACAO <  TRUNC(SYSDATE) + 1
       AND OM.TIPO_MANUTENCAO LIKE 'NT-%'
)
SELECT REPLACE(TIPO_NT, 'NT-', '')                                       AS FAMILIA,
       CASE WHEN IDADE_DIAS <= 30  THEN '01 ATÉ 30 DIAS'
            WHEN IDADE_DIAS <= 90  THEN '02 31 A 90 DIAS'
            WHEN IDADE_DIAS <= 180 THEN '03 91 A 180 DIAS'
            ELSE '04 MAIS DE 180 DIAS' END                                AS FAIXA_IDADE,
       COUNT(*)                                                          AS OM_ABERTAS,
       ROUND(AVG(IDADE_DIAS), 1)                                         AS IDADE_MEDIA_DIAS,
       MAX(IDADE_DIAS)                                                   AS IDADE_MAX_DIAS
  FROM OM_ABERTA
 GROUP BY REPLACE(TIPO_NT, 'NT-', ''),
          CASE WHEN IDADE_DIAS <= 30  THEN '01 ATÉ 30 DIAS'
               WHEN IDADE_DIAS <= 90  THEN '02 31 A 90 DIAS'
               WHEN IDADE_DIAS <= 180 THEN '03 91 A 180 DIAS'
               ELSE '04 MAIS DE 180 DIAS' END
 ORDER BY FAMILIA, FAIXA_IDADE
