/* =============================================================================
OBJETIVO: Update Engenharia (grupos de programação)
DOMÍNIO: 12_manutencao_dml_restrito
ARQUIVO ORIGINAL: Comandos SQL - CR\Update Engenharia (grupos de programação).sql
TIPO: DML - Atualização Controlada
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.VW_PI_CENGA04_CARGAMAQ
CUIDADOS OPERACIONAIS: ESTE ARQUIVO CONTÉM DML (UPDATE) e NÃO é somente leitura. Execução apenas
  manual, por operador autorizado: rode antes o SELECT de conferência, valide as linhas afetadas e
  só então execute o UPDATE, com COMMIT consciente (ou ROLLBACK se o rowcount divergir). Ver AVISO_SEGURANCA.md.
============================================================================= */

-- Conferência do UPDATE abaixo (mesmo WHERE: artigo 00483, PI 1101)
SELECT VPI.IDGRUPOFLUXOMAQ, VPI.VELOCIDADE, VPI.CODPROG, VPI.TOTAL_ITENS, VPI.*
FROM   SGTPRD.VW_PI_CENGA04_CARGAMAQ VPI
WHERE  TRIM(VPI.ARTIGO)='00483'
AND    VPI.PI=1101;

UPDATE GRUPO_FLUXO_MAQUINAS GFM
SET    GFM.VELOCIDADE = 32
WHERE  GFM.IDGRUPOFLUXOMAQ IN (
                                 SELECT VPI.IDGRUPOFLUXOMAQ
                                 FROM   VW_PI_CENGA04_CARGAMAQ VPI
                                 WHERE  TRIM(VPI.ARTIGO)='00483'
                                 AND    VPI.PI=1101
                              );
                              
--CONFERIR VELOCIDADE DA RAMA NOS GRUPOS DE PROGRAMAES
SELECT VPI.VELOCIDADE,
       VPI.NGP,
       VPI.CODPROG,
       VPI.DESCR_GRUPO_PROGR,
       VPI.FLUXO,
       VPI.FASE,
       VPI.DESCR_FASE,
       VPI.RECEITA,
       VPI.DESCR_RECEITA
  FROM SGTPRD.VW_PI_CENGA04_CARGAMAQ VPI
 WHERE 1 = 1
   AND TRIM(VPI.ARTIGO) = '00207'
   AND TRIM(VPI.NUMERO_MAQUINA) = 'RM01'
   AND VPI.FASE = 100
 GROUP BY VPI.VELOCIDADE,
          VPI.NGP,
          VPI.CODPROG,
          VPI.DESCR_GRUPO_PROGR,
          VPI.FLUXO,
          VPI.FASE,
          VPI.DESCR_FASE,
          VPI.RECEITA,
          VPI.DESCR_RECEITA
 ORDER BY VPI.CODPROG;
