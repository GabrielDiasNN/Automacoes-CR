-- =============================================================================
-- OBJETIVO: Quantidade de KGs em cada fase (antigo)
-- DOMÍNIO: 09_pcp_kpis_gestao
-- ARQUIVO ORIGINAL: Comandos SQL - CR\Quantidade de KGs em cada fase (antigo).sql
-- TIPO: PCP e Indicadores Fabris
-- PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
-- TABELAS PRINCIPAIS: SGTPRD.BD_BAS_MASCPRODACAB, SGTPRD.ENGEITEMESTONIVELGE9, SGTPRD.FLUXO, SGTPRD.FLUXOGRUPO, SGTPRD.FASES_FLUXO, SGTPRD.GERAPECADESTINOOB, SGTPRD.GERAPECAORIGEMOB, SGTPRD.GERAPECASPRODUTO, SGTPRD.GRUPO_FASES, SGTPRD.ITENS_ESTOQUE, SGTPRD.OB, SGTPRD.OB_PRODUTO, SGTPRD.PEDPRODUCAOOB, SGTPRD.UNIDADE_MEDIDA
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
-- CORREÇÃO (20/09/2026 - TIMEOUT, RESOLVIDO): usava SGTPRD.VW_PI_CBPAP01_PROCBENEF
--   SEM NENHUM FILTRO (a mesma view intratável de com_consulta_pedidos_atrasados.sql,
--   pasta 07_expedicao_pedidos_comercial). Diagnóstico inicial (sessão anterior)
--   descartou correção por achar que as ~16 colunas usadas exigiam reconstruir a
--   view inteira sem filtro possível — reavaliado a pedido do usuário ("tem certeza
--   que não dá pra resolver?"): lendo o texto-fonte da view (ALL_VIEWS.TEXT),
--   confirmado que TODAS as colunas usadas aqui (FASE, MONTADA, STATUS,
--   STATUS_FASE, TIPO_ORDEM, FLUXO, PEDIDO_EXCLUSIVO, ESTAMPADO, TIPO_MAQUINA,
--   QUANT_ACA/PROG/ORIG, PECAS_ORIG/ACA, UM, REDUZ) vêm de fontes baratas e 1:1
--   por OB: VW_BNF_OBMONTADA, VW_BNF_FASEATUALOB, VW_PI_CENGA03_PRODACA, a tabela
--   OB (codigo_reduzido/tipo_ordem/codigo_fluxo) e MAQUINA (tipo_maquina via
--   vfa.numero_maquina). PEDIDO_EXCLUSIVO vem da mesma cadeia de pedido já
--   resolvida em com_consulta_pedidos_atrasados.sql/070 (PEDPRODUCAOOB->OFORDENS->
--   OFPEDIDO->ITENSPEDIDOQTDES->ITENSPEDIDOGRADE->PEDIDOCOMERCIAL, aqui com
--   P.SETOR=5, igual ao "ped" da view original). Como o objetivo é uma foto das
--   OBs ATIVAS (obx.status<>0 and obx.tipo_ordem in (0,6), replicado aqui como
--   OB.STATUS<>0 AND OB.TIPO_ORDEM IN (0,6)), a base é pequena (545 OBs no
--   momento do teste) — nada parecido com o volume total da view. Validado com
--   execução real: 17 linhas, rápido, sem timeout; contagem de OB_ATIVAS bate
--   exatamente com a contagem final da junção (545=545), confirmando ausência de
--   duplicação por fan-out nos joins 1:1.
-- =============================================================================

WITH OB_ATIVAS AS (
  -- Substitui obx.status<>0 and obx.tipo_ordem in (0,6) da VW_PI_CBPAP01_PROCBENEF
  SELECT /*+ MATERIALIZE */ NUMERO_OB, CODIGO_REDUZIDO, TIPO_ORDEM, CODIGO_FLUXO, STATUS
    FROM SGTPRD.OB WHERE STATUS <> 0 AND TIPO_ORDEM IN (0,6)
),
FASE_ATUAL AS (
  SELECT NUMERO_OB, CODIGO_FASE, STATUS, NUMERO_MAQUINA
    FROM (
      SELECT OBF.NUMERO_OB, OBF.CODIGO_FASE, OBF.STATUS, OBF.NUMERO_MAQUINA,
             ROW_NUMBER() OVER (
               PARTITION BY OBF.NUMERO_OB
               ORDER BY CASE WHEN OBF.STATUS IN (1,2,3) THEN 1 WHEN OBF.STATUS = 0 THEN 2 ELSE 3 END,
                        OBF.SEQUENCIA DESC
             ) RN
        FROM SGTPRD.OB_FASES OBF
        JOIN OB_ATIVAS OBA ON OBA.NUMERO_OB = OBF.NUMERO_OB
    )
   WHERE RN = 1
),
PECAS_OB AS (
  SELECT OBA.NUMERO_OB,
         COUNT(DISTINCT ORI.IDPECASPRODUTO) PECAS_ORIG,
         COUNT(DISTINCT DES.IDPECASPRODUTO) PECAS_ACA
    FROM OB_ATIVAS OBA
    LEFT JOIN SGTPRD.GERAPECAORIGEMOB ORI ON ORI.NUMERO_OB = OBA.NUMERO_OB
    LEFT JOIN SGTPRD.GERAPECADESTINOOB DES ON DES.NUMERO_OB = OBA.NUMERO_OB
   GROUP BY OBA.NUMERO_OB
),
MEDIDAS_OB AS (
  SELECT OBA.NUMERO_OB,
         NVL(PPOB.OBMONTADA, 0) MONTADA,
          CASE WHEN UM.TPUNIDADEMEDIDA = 1 THEN NVL(OP.KILOS_ACABADOS, 0)
              ELSE NVL(OP.METROS_ACABADOS, 0) END QUANT_ACA,
          CASE WHEN UM.TPUNIDADEMEDIDA = 1 THEN NVL(OP.KILOS_PROGRAMADOS, 0)
              ELSE NVL(OP.METROS_PROGRAMADOS, 0) END QUANT_PROG,
          CASE WHEN UM.TPUNIDADEMEDIDA = 1 THEN NVL(OP.KILOS, 0)
              ELSE NVL(OP.METROS, 0) END QUANT_ORIG,
         OP.NUMERO_OB AS OB_PRODUTO,
         TRIM(UM.DSSIGLA) UM,
          P.PECAS_ORIG,
         P. PECAS_ACA
    FROM OB_ATIVAS OBA
    JOIN SGTPRD.OB_PRODUTO OP ON OP.NUMERO_OB = OBA.NUMERO_OB
    JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = OBA.CODIGO_REDUZIDO
    LEFT JOIN SGTPRD.UNIDADE_MEDIDA UM ON UM.IDUNIDADEMEDIDA = ITE.IDUNIDADEMEDIDA
    LEFT JOIN SGTPRD.PEDPRODUCAOOB PPOB ON PPOB.NUMEROOB = OBA.NUMERO_OB AND PPOB.SETOR = 5
    LEFT JOIN PECAS_OB P ON P.NUMERO_OB = OBA.NUMERO_OB
),
PED_EXCLUSIVO AS (
  -- Substitui a subtabela "ped" da view (mesma cadeia de pedido de
  -- com_consulta_pedidos_atrasados.sql / est_conferencia_furo_estoque_peca_peca.sql)
  SELECT /*+ MATERIALIZE */ P.NUMEROOB NUMERO_OB, MIN(PCO.PEDIDO) PEDIDO, COUNT(PCO.PEDIDO) NRO_PEDIDOS
    FROM SGTPRD.PEDPRODUCAOOB P, SGTPRD.OFORDENS OFO, SGTPRD.OFPEDIDO OFP, SGTPRD.ITENSPEDIDOQTDES IPX,
         SGTPRD.ITENSPEDIDOGRADE IPG, SGTPRD.PEDIDOCOMERCIAL PCO, OB_ATIVAS OBA
   WHERE OFO.NUMEROPEDPRODUCAO = P.NUMERO AND OFP.NUMEROOF = OFO.NUMEROOF
     AND IPX.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES AND IPG.IDITENSPEDIDOGRADE = IPX.IDITEMPEDGRADE
     AND PCO.PEDIDO = IPG.PEDIDO AND P.SETOR = 5 AND P.NUMEROOB = OBA.NUMERO_OB
    GROUP BY P.NUMEROOB
),
ENG_PRODUTO AS (
  -- Substitui VW_PI_CENGA03_PRODACA pelas três fontes físicas usadas
  -- somente para UM e ESTAMPADO.
  SELECT /*+ MATERIALIZE */
         ITE.CODIGO_REDUZIDO AS REDUZ,
         TRIM(UND.DSSIGLA) AS UM,
         VMA.ESTAMPADO
    FROM SGTPRD.ITENS_ESTOQUE ITE
    JOIN SGTPRD.UNIDADE_MEDIDA UND
      ON UND.IDUNIDADEMEDIDA = ITE.IDUNIDADEMEDIDA
    JOIN SGTPRD.BD_BAS_MASCPRODACAB VMA
      ON VMA.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
   WHERE ITE.TIPO_ITEM = 10
     AND EXISTS (
           SELECT 1
             FROM OB_ATIVAS OBA
            WHERE OBA.CODIGO_REDUZIDO = ITE.CODIGO_REDUZIDO
         )
),
V AS (
  -- Substitui VW_PI_CBPAP01_PROCBENEF (ver nota de correção no cabeçalho):
  -- as colunas usadas nesta query vêm todas de fontes 1:1 por OB, sem precisar
  -- da view inteira.
  SELECT /*+ MATERIALIZE */
         OBA.NUMERO_OB, OBA.CODIGO_REDUZIDO REDUZ, VFA.CODIGO_FASE FASE, OBE.MONTADA, OBA.STATUS,
         VFA.STATUS STATUS_FASE, OBA.TIPO_ORDEM, OBA.CODIGO_FLUXO FLUXO,
         CASE WHEN NVL(PED.NRO_PEDIDOS,0)<>0 THEN PED.PEDIDO ELSE 0 END PEDIDO_EXCLUSIVO,
         ENG.ESTAMPADO, MAQ.TIPO_MAQUINA,
         OBE.QUANT_ACA, OBE.QUANT_PROG, OBE.QUANT_ORIG,
         OBE.PECAS_ORIG, OBE.PECAS_ACA, OBE.UM
    FROM OB_ATIVAS OBA
    JOIN MEDIDAS_OB OBE ON OBE.NUMERO_OB = OBA.NUMERO_OB
    JOIN FASE_ATUAL VFA ON VFA.NUMERO_OB = OBA.NUMERO_OB
    JOIN ENG_PRODUTO ENG ON ENG.REDUZ = OBA.CODIGO_REDUZIDO
    LEFT JOIN PED_EXCLUSIVO PED ON PED.NUMERO_OB = OBA.NUMERO_OB
    LEFT JOIN (SELECT MAQX.NUMERO_MAQUINA, MAQX.IDTIPOSMAQUINA TIPO_MAQUINA FROM SGTPRD.MAQUINA MAQX WHERE MAQX.SETOR=5) MAQ
           ON MAQ.NUMERO_MAQUINA = VFA.NUMERO_MAQUINA
)
SELECT  BASE.FASES
       ,BASE.QT_PEAS
       ,CASE WHEN BASE.FASES = '999 - EM EXECUO NAS FASES DA PRODUO' THEN BASE.QUANTIDADE_CRU
        ELSE QUANTIDADE_REGRA
        END AS QUANTIDADE
       ,BASE.UM
       ,BASE.QT_OB


      FROM (SELECT CASE WHEN V.FASE IN (10)            AND V.MONTADA = 0 AND V.STATUS = 3 AND V.STATUS_FASE = 0 THEN                              '10 - FALTA MONTAR -> (PROGRAMADA)'
                        WHEN V.FASE IN (10)            AND V.MONTADA = 0 AND V.STATUS = 1 AND V.STATUS_FASE = 0 THEN                              '11 - FALTA MONTAR -> (EMITADA)'
                        WHEN V.PEDIDO_EXCLUSIVO = 0    THEN                                                                                       '12 - SEM PROGRAMAO'
                        WHEN V.FASE IN (10)            AND V.MONTADA = 1 AND V.TIPO_ORDEM = 6 AND V.STATUS_FASE = 0 THEN                          '13 - REPROCESSO -> (FALTA AGRUPAR)'
                        WHEN V.FASE IN (20)            AND V.FLUXO <> 204 AND V.STATUS_FASE = 0 THEN                                              '20 - MONTADO -> (REVISAR P/TINGIMENTO)'
                        WHEN V.FASE IN (20)            AND V.FLUXO = 204      	THEN                                                              '21 - MONTADO -> (REVISAR P/ABRIDOR)'                          
                        WHEN V.FASE IN (40)            AND V.STATUS_FASE <> 3 	THEN                                                              '22 - REVISADO'
                        WHEN V.FASE IN (40)            AND V.STATUS_FASE = 3  	THEN                                                              '25 - TINGINDO AGORA'
                        WHEN V.FASE IN (45,50)         AND FLG.ID IN (1,3,5,9,12) 	THEN                                                          '30 - HIDRO UMIDO'
                        WHEN V.FASE IN (45,55)         AND FLG.ID IN (1,3,5,9,12)	THEN                                                          '31 - HIDRO SECO'
                        WHEN V.FASE IN (60)            THEN                                                                                       '35 - SECADOR'
                        WHEN V.TIPO_MAQUINA = 29       AND FLG.ID = 5 THEN                                        					              '36 - FELPADEIRA (TUBULAR)'
                        WHEN V.TIPO_MAQUINA = 29       AND FLG.ID = 12 THEN                                        				                  '37 - FELPADEIRA (RAMADO -> FELPADO TUBULAR)' 
                        WHEN V.TIPO_MAQUINA = 29       AND FLG.ID = 6 THEN                                        					              '38 - FELPADEIRA (RAMADO -> FELPADO ABERTO)' 
                        WHEN V.FASE IN (70)            THEN                                                                                       '40 - CALANDRA DE BRILHO'
                        WHEN V.FASE IN (80)            THEN                                                                                       '45 - CALANDRA COMPACTA'
                        WHEN V.FASE IN (45,90,100,110) AND V.ESTAMPADO = 0 AND FLG.ID = 2 		THEN                              	              '50 - ABR/RAS/RAU'
                        WHEN V.TIPO_MAQUINA IN (6,23)  AND V.ESTAMPADO = 1 AND FLG.ID IN (4,7,11) AND NOT (V.FASE = 100 AND FLG.ID IN (4,7)) THEN '51 - ABR/RAS/RAU -> (ENVIAR P/ ESTAMPARIA)'
                        WHEN V.TIPO_MAQUINA IN (6,23)  AND V.ESTAMPADO = 0 AND FLG.ID IN (8,10) THEN                                              '52 - ABR/RAS/RAU (DIRETO RAMA)'
                        WHEN V.FASE IN (100)           AND V.ESTAMPADO = 1 AND FLG.ID = 4 		THEN                  				              '53 - RAMAR UMIDO -> (FINALIZAR ESTAMPADO)'
                        WHEN V.FASE IN (110)           AND V.ESTAMPADO = 0 AND FLG.ID IN (6,12) THEN                  				              '54 - RAMAR SECO -> (FINALIZAR FELPADO)'
                        WHEN V.FASE IN (150,160)       AND V.ESTAMPADO = 0 THEN                                                                   '60 - CQ/EXP -> (FALTA EMBALAR)'
                        WHEN V.FASE IN (150,160)       AND V.FLUXO IN (107,109)              THEN                                                 '61 - CQ/EXP -> (FALTA ENSACAR MANNRICH)'
                        WHEN V.FASE IN (150,160)       AND V.FLUXO IN (110,111)              THEN                                                 '62 - CQ/EXP -> (FALTA ENSACAR ZIMERMANN)'
                        WHEN V.FASE IN (150,160)       AND V.FLUXO IN (112,113)              THEN                                                 '63 - CQ/EXP -> (FALTA ENSACAR CORES & TONS)' 
                        WHEN V.FASE IN (120)           AND V.STATUS_FASE = 3 THEN                                                                 '70 - RETORNAR DA MANNRICH'
                        WHEN V.FASE IN (125)           AND V.STATUS_FASE = 3 THEN                                                                 '71 - RETORNAR DA ZIMERMANN'
                        WHEN V.FASE IN (130)           AND V.STATUS_FASE = 3 THEN                                                                 '72 - RETORNAR DA CORES & TONS'
                        WHEN V.FASE IN (135)           AND V.STATUS_FASE = 3 THEN                                                                 '73 - RETORNAR DA PRIMER COLOR'
                        WHEN V.FASE IN (140)           AND V.STATUS_FASE = 3 THEN                                                                 '74 - RETORNAR DA ODORIZZI'
                        WHEN V.FASE IN (145)           AND V.STATUS_FASE = 3 THEN                                                                 '75 - RETORNAR DA SSG (CIRR)'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (301,303) THEN                                                              '80 - ENVIAR P/ ODORIZZI'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (302,306) THEN                                                              '81 - ENVIAR P/ CORES & TONS'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (305,308) THEN                                                              '82 - ENVIAR P/ PRIME COLOR'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (304)     THEN                                                              '83 - ENVIAR P/ 3A DIGITAL'
                        WHEN V.FASE IN (120)           AND V.FLUXO IN (107,109) THEN                                                              '84 - ENVIAR ENSACADO P/ MANNRICH'
                        WHEN V.FASE IN (125)           AND V.FLUXO IN (110,111) THEN                                                              '85 - ENVIAR ENSACADO P/ ZIMERMANN'
                        WHEN V.FASE IN (130)           AND V.FLUXO IN (112,113) THEN                                                              '86 - ENVIAR ENSACADO P/ CORES & TONS'
                        WHEN V.FASE IN (190)           AND V.FLUXO IN (207)     THEN                                                              '95 - ENTREGAR P/ URBANO'
																																	              
                        ELSE                                                                                                                      '999 - OUTROS'
                        END AS FASES

                       ,DECODE(SUM(V.QUANT_ACA),0,(SUM(DECODE(V.MONTADA, 0, V.QUANT_PROG, 1, V.QUANT_ORIG, ''))),SUM(V.QUANT_ACA)) QUANTIDADE_REGRA
                       ,SUM(DECODE(V.MONTADA, 0, V.QUANT_PROG, 1, V.QUANT_ORIG, ''))  QUANTIDADE_CRU
                       ,SUM(NVL(V.PECAS_ORIG, V.PECAS_ACA)) QT_PEAS
                       ,V.UM
                       ,COUNT(V.NUMERO_OB) QT_OB

      FROM V,
           SGTPRD.ENGEITEMESTONIVELGE9    ENG2,
           SGTPRD.FLUXOGRUPO              FLG,
           SGTPRD.FLUXO                   FLX
      WHERE ENG2.CDREDUZIDO  = V.REDUZ
      AND   FLX.CODIGO_FLUXO = V.FLUXO
      AND   FLG.ID           = FLX.IDFLUXOGRUPO

         GROUP BY  CASE WHEN V.FASE IN (10)            AND V.MONTADA = 0 AND V.STATUS = 3 AND V.STATUS_FASE = 0 THEN                              '10 - FALTA MONTAR -> (PROGRAMADA)'
                        WHEN V.FASE IN (10)            AND V.MONTADA = 0 AND V.STATUS = 1 AND V.STATUS_FASE = 0 THEN                              '11 - FALTA MONTAR -> (EMITADA)'
                        WHEN V.PEDIDO_EXCLUSIVO = 0    THEN                                                                                       '12 - SEM PROGRAMAO'
                        WHEN V.FASE IN (10)            AND V.MONTADA = 1 AND V.TIPO_ORDEM = 6 AND V.STATUS_FASE = 0 THEN                          '13 - REPROCESSO -> (FALTA AGRUPAR)'
                        WHEN V.FASE IN (20)            AND V.FLUXO <> 204 AND V.STATUS_FASE = 0 THEN                                              '20 - MONTADO -> (REVISAR P/TINGIMENTO)'
                        WHEN V.FASE IN (20)            AND V.FLUXO = 204      	THEN                                                              '21 - MONTADO -> (REVISAR P/ABRIDOR)'                          
                        WHEN V.FASE IN (40)            AND V.STATUS_FASE <> 3 	THEN                                                              '22 - REVISADO'
                        WHEN V.FASE IN (40)            AND V.STATUS_FASE = 3  	THEN                                                              '25 - TINGINDO AGORA'
                        WHEN V.FASE IN (45,50)         AND FLG.ID IN (1,3,5,9,12) 	THEN                                                          '30 - HIDRO UMIDO'
                        WHEN V.FASE IN (45,55)         AND FLG.ID IN (1,3,5,9,12)	THEN                                                          '31 - HIDRO SECO'
                        WHEN V.FASE IN (60)            THEN                                                                                       '35 - SECADOR'
                        WHEN V.TIPO_MAQUINA = 29       AND FLG.ID = 5 THEN                                        					              '36 - FELPADEIRA (TUBULAR)'
                        WHEN V.TIPO_MAQUINA = 29       AND FLG.ID = 12 THEN                                        				                  '37 - FELPADEIRA (RAMADO -> FELPADO TUBULAR)' 
                        WHEN V.TIPO_MAQUINA = 29       AND FLG.ID = 6 THEN                                        					              '38 - FELPADEIRA (RAMADO -> FELPADO ABERTO)' 
                        WHEN V.FASE IN (70)            THEN                                                                                       '40 - CALANDRA DE BRILHO'
                        WHEN V.FASE IN (80)            THEN                                                                                       '45 - CALANDRA COMPACTA'
                        WHEN V.FASE IN (45,90,100,110) AND V.ESTAMPADO = 0 AND FLG.ID = 2 		THEN                              	              '50 - ABR/RAS/RAU'
                        WHEN V.TIPO_MAQUINA IN (6,23)  AND V.ESTAMPADO = 1 AND FLG.ID IN (4,7,11) AND NOT (V.FASE = 100 AND FLG.ID IN (4,7)) THEN '51 - ABR/RAS/RAU -> (ENVIAR P/ ESTAMPARIA)'
                        WHEN V.TIPO_MAQUINA IN (6,23)  AND V.ESTAMPADO = 0 AND FLG.ID IN (8,10) THEN                                              '52 - ABR/RAS/RAU (DIRETO RAMA)'
                        WHEN V.FASE IN (100)           AND V.ESTAMPADO = 1 AND FLG.ID = 4 		THEN                  				              '53 - RAMAR UMIDO -> (FINALIZAR ESTAMPADO)'
                        WHEN V.FASE IN (110)           AND V.ESTAMPADO = 0 AND FLG.ID IN (6,12) THEN                  				              '54 - RAMAR SECO -> (FINALIZAR FELPADO)'
                        WHEN V.FASE IN (150,160)       AND V.ESTAMPADO = 0 THEN                                                                   '60 - CQ/EXP -> (FALTA EMBALAR)'
                        WHEN V.FASE IN (150,160)       AND V.FLUXO IN (107,109)              THEN                                                 '61 - CQ/EXP -> (FALTA ENSACAR MANNRICH)'
                        WHEN V.FASE IN (150,160)       AND V.FLUXO IN (110,111)              THEN                                                 '62 - CQ/EXP -> (FALTA ENSACAR ZIMERMANN)'
                        WHEN V.FASE IN (150,160)       AND V.FLUXO IN (112,113)              THEN                                                 '63 - CQ/EXP -> (FALTA ENSACAR CORES & TONS)' 
                        WHEN V.FASE IN (120)           AND V.STATUS_FASE = 3 THEN                                                                 '70 - RETORNAR DA MANNRICH'
                        WHEN V.FASE IN (125)           AND V.STATUS_FASE = 3 THEN                                                                 '71 - RETORNAR DA ZIMERMANN'
                        WHEN V.FASE IN (130)           AND V.STATUS_FASE = 3 THEN                                                                 '72 - RETORNAR DA CORES & TONS'
                        WHEN V.FASE IN (135)           AND V.STATUS_FASE = 3 THEN                                                                 '73 - RETORNAR DA PRIMER COLOR'
                        WHEN V.FASE IN (140)           AND V.STATUS_FASE = 3 THEN                                                                 '74 - RETORNAR DA ODORIZZI'
                        WHEN V.FASE IN (145)           AND V.STATUS_FASE = 3 THEN                                                                 '75 - RETORNAR DA SSG (CIRR)'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (301,303) THEN                                                              '80 - ENVIAR P/ ODORIZZI'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (302,306) THEN                                                              '81 - ENVIAR P/ CORES & TONS'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (305,308) THEN                                                              '82 - ENVIAR P/ PRIME COLOR'
                        WHEN V.FASE IN (25)            AND V.FLUXO IN (304)     THEN                                                              '83 - ENVIAR P/ 3A DIGITAL'
                        WHEN V.FASE IN (120)           AND V.FLUXO IN (107,109) THEN                                                              '84 - ENVIAR ENSACADO P/ MANNRICH'
                        WHEN V.FASE IN (125)           AND V.FLUXO IN (110,111) THEN                                                              '85 - ENVIAR ENSACADO P/ ZIMERMANN'
                        WHEN V.FASE IN (130)           AND V.FLUXO IN (112,113) THEN                                                              '86 - ENVIAR ENSACADO P/ CORES & TONS'
                        WHEN V.FASE IN (190)           AND V.FLUXO IN (207)     THEN                                                              '95 - ENTREGAR P/ URBANO'
																																	              
                        ELSE                                                                                                                      '999 - OUTROS'
                        END, V.UM
       ) BASE

       WHERE BASE.FASES <> '999 - OUTROS'
       ORDER BY 1
