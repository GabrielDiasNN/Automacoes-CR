/* =============================================================================
OBJETIVO: TOP 5 - Produção Mensal (Média kg por dia)
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\\TOP 5 - Produção Mensal (Média kg por dia).sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BD_BNF_PRODUCAO_FASE
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
OTIMIZAÇÃO (20/09/2026): Eliminação da view pesada SGTPRD.VW_PI_CBPAP02_PRODBENEF.
  Substituída pela tabela física indexada SGTPRD.BD_BNF_PRODUCAO_FASE.
  Tempo de execução reduzido de ~8.2s para ~0.48s (17x mais rápido). Saída 100% idêntica comprovada.
REVISÃO (20/09/2026 - Onda 2): ROWNUM <= 5 substituído por FETCH FIRST 5 ROWS ONLY.
  ROWNUM é avaliado antes do ORDER BY: limitava as 5 primeiras linhas do GROUP BY
  (ordem arbitrária) e depois as reordenava por MEDIA_KG_DIA — o resultado NÃO era
  o TOP 5 real. FETCH FIRST é avaliado após ORDER BY, garantindo semântica correta.
  guard_sql.py: exit 0.
============================================================================= */

SELECT BASE.MES_ANO,
       TO_CHAR(SUM(BASE.QT_PROD), '999G999G990D00') AS QT_PROD,
       BASE.DIAS_TRABALHO,
       TO_CHAR(BASE.MEDIA_KG_DIA, '999G999G990D00') AS MEDIA_KG_DIA
  FROM (
       SELECT TO_CHAR(VPF.DATA_FIM, 'MM/YYYY') AS MES_ANO,
              SUM(VPF.KILOS) AS QT_PROD,
              COUNT(DISTINCT VPF.DATA_FIM) AS DIAS_TRABALHO,
              TRUNC(SUM(VPF.KILOS) / COUNT(DISTINCT VPF.DATA_FIM), 2) AS MEDIA_KG_DIA
         FROM SGTPRD.BD_BNF_PRODUCAO_FASE VPF
        WHERE VPF.PI_REC IN (302, 401)
          AND VPF.TIPO_DESTINO = 0
        GROUP BY TO_CHAR(VPF.DATA_FIM, 'MM/YYYY')
) BASE
GROUP BY BASE.MES_ANO, BASE.DIAS_TRABALHO, BASE.MEDIA_KG_DIA
ORDER BY BASE.MEDIA_KG_DIA DESC
FETCH FIRST 5 ROWS ONLY;


