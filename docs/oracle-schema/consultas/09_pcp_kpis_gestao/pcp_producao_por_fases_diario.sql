/* =============================================================================
OBJETIVO: Produção por Fases Diário
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO ORIGINAL: Comandos SQL - CR\Produção por Fases Diário.sql
TIPO: PCP e Indicadores Fabris
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO, SGTPRD.MAQUINA, SGTPRD.OB_FASES, SGTPRD.OB
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
OTIMIZAÇÃO: Conversão para ANSI JOINs, remoção de subqueries redundantes do DUAL, eliminação de junções desnecessárias.
============================================================================= */

SELECT CASE WHEN OBF.CODIGO_FASE = 10          THEN '01 - MONTAGEM'
            WHEN OBF.CODIGO_FASE = 20          THEN '02 - REVISÃO'
            WHEN OBF.CODIGO_FASE = 40          THEN '03 - TINGIMENTO'
            WHEN OBF.CODIGO_FASE IN (50, 55)   THEN '04 - HIDRO'
            WHEN OBF.CODIGO_FASE = 60          THEN '05 - SECADOR'
            WHEN OBF.CODIGO_FASE = 65          THEN '06 - FELPADEIRA'
            WHEN OBF.CODIGO_FASE = 70          THEN '07 - CALANDRA BRILHO'
            WHEN OBF.CODIGO_FASE = 80          THEN '08 - CALANDRA COMPACTA'
            WHEN OBF.CODIGO_FASE = 90          THEN '09 - ABRIDOR'
            WHEN OBF.CODIGO_FASE IN (100, 110) THEN '10 - RAMA'
            WHEN OBF.CODIGO_FASE = 150         THEN '11 - EMBALADEIRA'
            ELSE '99 - NAO DEFINIDO' END AS CD_DS_FASE
      ,SUM(OBF.KILOS_PRODUZIDOS) QT_KG
      ,ROUND(NVL(SUM(OBF.KILOS_PRODUZIDOS), 0) / ((SYSDATE - 5 / 24 - TRUNC(SYSDATE)) * 24), 2) AS QT_KG_HR
      ,SUM(OBF.METROS_PRODUZIDOS) QT_MT
      ,ROUND(NVL(SUM(OBF.METROS_PRODUZIDOS), 0) / ((SYSDATE - 5 / 24 - TRUNC(SYSDATE)) * 24), 2) AS QT_MT_HR
      ,ROUND(
       SUM(
       CASE WHEN UPR.DURACAO_PREVISTA <> 0 THEN UPR.DURACAO_PREVISTA * 1440
            ELSE DECODE(UPR.TEMPOFINALPROGRAMADO, 0, (UPR.TEMPOFINALPLANEJADO - UPR.TEMPOINIPLANEJADO) * 1440, (UPR.TEMPOFINALPROGRAMADO - UPR.TEMPOINIPROGRAMADO) * 1440)
       END),0) MIN_PREV
      ,ROUND(SUM(CASE WHEN ((TEMPOFINAL - TEMPOINICIAL) * 1440) <= 1 THEN 1
            ELSE (TEMPOFINAL - TEMPOINICIAL) * 1440 - (NVL((SELECT TRUNC(SUM(UPA.TEMPOFINAL - UPA.TEMPOINICIAL) * 1440)+1
                                                       FROM SGTPRD.UNIDADE_PROGRAMACAO UPA
                                                      WHERE UPA.EXCLUIDA = 0
                                                        AND UPA.SETOR = UPR.SETOR
                                                        AND UPA.STATUS = 0
                                                        AND UPA.NUMERO_MAQUINA = UPR.NUMERO_MAQUINA
                                                        AND UPA.TEMPOFINAL >= UPR.TEMPOINICIAL
                                                        AND UPA.TEMPOINICIAL >= UPR.TEMPOINICIAL
                                                        AND UPA.TEMPOFINAL <= UPR.TEMPOFINAL
                                                        AND UPA.TIPOUP = 5),0)
                                                       ) + 1
       END),0) MIN_REAL
      ,ROUND((SYSDATE - 5 / 24 - TRUNC(SYSDATE)) * (COUNT(DISTINCT OBF.NUMERO_MAQUINA) * 1440), 0) MIN_DISP
      ,ROUND(AVG(REN.RENDIMENTO),2) RENDIMENTO

      ,(SUM(CASE WHEN UPR.DURACAO_PREVISTA <> 0 THEN UPR.DURACAO_PREVISTA * 1440
            ELSE DECODE(UPR.TEMPOFINALPROGRAMADO, 0, (UPR.TEMPOFINALPLANEJADO - UPR.TEMPOINIPLANEJADO) * 1440, (UPR.TEMPOFINALPROGRAMADO - UPR.TEMPOINIPROGRAMADO) * 1440)
            END
           )
       ) / 
       (SUM(CASE WHEN ((TEMPOFINAL - TEMPOINICIAL) * 1440) <= 1 THEN 1
                 ELSE (TEMPOFINAL - TEMPOINICIAL) * 1440 - (NVL((SELECT TRUNC(SUM(UPA.TEMPOFINAL - UPA.TEMPOINICIAL) * 1440)+1
                                                                 FROM SGTPRD.UNIDADE_PROGRAMACAO UPA
                                                                WHERE UPA.EXCLUIDA = 0
                                                                  AND UPA.SETOR = UPR.SETOR
                                                                  AND UPA.STATUS = 0
                                                                  AND UPA.NUMERO_MAQUINA = UPR.NUMERO_MAQUINA
                                                                  AND UPA.TEMPOFINAL >= UPR.TEMPOINICIAL
                                                                  AND UPA.TEMPOINICIAL >= UPR.TEMPOINICIAL
                                                                  AND UPA.TEMPOFINAL <= UPR.TEMPOFINAL
                                                                  AND UPA.TIPOUP = 5),0)
                                                                 ) + 1
                 END) 
       ) * 100 EFIC_PROC
       
      ,(SUM(CASE WHEN UPR.DURACAO_PREVISTA <> 0 THEN UPR.DURACAO_PREVISTA * 1440
            ELSE DECODE(UPR.TEMPOFINALPROGRAMADO, 0, (UPR.TEMPOFINALPLANEJADO - UPR.TEMPOINIPLANEJADO) * 1440, (UPR.TEMPOFINALPROGRAMADO - UPR.TEMPOINIPROGRAMADO) * 1440)
            END
           )
       ) / 
       ((SYSDATE - 5 / 24 - TRUNC(SYSDATE)) * (COUNT(DISTINCT OBF.NUMERO_MAQUINA) * 1440)) * 100 EFIC_DISP
FROM  SGTPRD.UNIDADE_PROGRAMACAO UPR
    JOIN SGTPRD.UP_ORDEM_MVTO       UOM ON UOM.NUMEROUP = UPR.NUMEROUP
    JOIN SGTPRD.MAQUINA             MAQ ON MAQ.NUMERO_MAQUINA = UPR.NUMERO_MAQUINA
    JOIN SGTPRD.OB_FASES            OBF ON OBF.NUMEROORDEMMOVIMENTO = UOM.NUMEROORDEMREAL AND OBF.SEQUENCIAORDEMMOVIME = UOM.SEQUENCIAORDEMREAL
    LEFT JOIN (SELECT OBE.NUMERO_OB
            ,CASE WHEN EPA.TIPO_DA_GRAMATURA  = 1 AND ICO.TIPOPRODUTO NOT IN (4,9) AND (EPA.GRAMATURA * EPA.LARGURA) <> 0 THEN 1000 / (EPA.GRAMATURA * EPA.LARGURA)
                  WHEN EPA.TIPO_DA_GRAMATURA <> 1 AND ICO.TIPOPRODUTO NOT IN (4,9) AND  EPA.GRAMATURA <> 0                THEN 1000 / EPA.GRAMATURA
                  WHEN EPA.TIPO_DA_GRAMATURA  = 1 AND ICO.TIPOPRODUTO IN (4,9)     AND (EPA.GRAMATURA * EPA.LARGURA) <> 0 THEN 1000 / (EPA.GRAMATURA * EPA.LARGURA * 2)
                  WHEN EPA.TIPO_DA_GRAMATURA <> 1 AND ICO.TIPOPRODUTO IN (4,9)     AND  EPA.GRAMATURA <> 0                THEN 1000 / (EPA.GRAMATURA * 2)
                  ELSE 0 END RENDIMENTO
       FROM SGTPRD.OB                OBE,
            SGTPRD.ITENS_ESTOQUE	   ITE,
            SGTPRD.ENG_PRODG_ACABADO EPA,
            SGTPRD.ITENS_COMPLEMENTO ICO
       WHERE ITE.CODIGO_REDUZIDO = OBE.CODIGO_REDUZIDO
       AND EPA.REDUZIDO_AGRUPADOR = ITE.REDUZIDO_AGRUPADOR
       AND ICO.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
     ) REN ON REN.NUMERO_OB = OBF.NUMERO_OB
WHERE UPR.SETOR = 5
AND   UPR.EXCLUIDA = 0
AND   UPR.TIPOUP = 0
AND   UPR.STATUS = 0
AND   UPR.DTPRODFIM = TRUNC(SYSDATE)
GROUP BY CASE WHEN OBF.CODIGO_FASE = 10          THEN '01 - MONTAGEM'
            WHEN OBF.CODIGO_FASE = 20          THEN '02 - REVISÃO'
            WHEN OBF.CODIGO_FASE = 40          THEN '03 - TINGIMENTO'
            WHEN OBF.CODIGO_FASE IN (50, 55)   THEN '04 - HIDRO'
            WHEN OBF.CODIGO_FASE = 60          THEN '05 - SECADOR'
            WHEN OBF.CODIGO_FASE = 65          THEN '06 - FELPADEIRA'
            WHEN OBF.CODIGO_FASE = 70          THEN '07 - CALANDRA BRILHO'
            WHEN OBF.CODIGO_FASE = 80          THEN '08 - CALANDRA COMPACTA'
            WHEN OBF.CODIGO_FASE = 90          THEN '09 - ABRIDOR'
            WHEN OBF.CODIGO_FASE IN (100, 110) THEN '10 - RAMA'
            WHEN OBF.CODIGO_FASE = 150         THEN '11 - EMBALADEIRA'
            ELSE '99 - NAO DEFINIDO' END
ORDER BY 1
