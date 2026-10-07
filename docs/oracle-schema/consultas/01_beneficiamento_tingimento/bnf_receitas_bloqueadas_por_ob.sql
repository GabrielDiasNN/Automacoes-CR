/* =============================================================================
OBJETIVO: OB_s com receitas bloqueadas
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s com receitas bloqueadas.sql
TIPO: Tingimento e Tinturaria
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.CADASTRO_RECEITAS, SGTPRD.CLASSIFICACAO_COR, SGTPRD.CRISTAL, SGTPRD.LABRECEITA_BLOQUEADA, SGTPRD.LIGA_CADREC_ITEMREC, SGTPRD.OB, SGTPRD.OB_FASES, SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
============================================================================= */

SELECT OBF.GRUPO,
       OBF.NR_OB,
       OBF.SEQ,
       OBF.PI               AS PI_OB,
       OBF.COR              AS COR_OB,
       OBF.EP               AS EP_OB,
       OBF.PE,
       OBF.MQ_TING,
       OBF.INICIO_TING,
       OBF.FINAL_TING,
       CRE.GRAFICO,
       CRE.DATA_ULT_PROD,
       CRE.CD_CLASSIF,
       CRE.CLASSIF_COR,
       CRE.CODIGO_REDUZIDO_RECE,
       CRE.OBSERVACAO,
       REC.BLOQUEIO_RECEITA,
       REC.DATA_BLOQUEIO,
       REC.USUARIO_BLOQUEIO,
       REC.OBSERVACAO_BLOQUEIO,
       REC.DATA_ALTERACAO,
       REC.NOME_USUARIO_ALTEROU
  FROM (SELECT OBFX.CODIGO_GRUPO    GRUPO,
               OBFX.NUMERO_OB       NR_OB,
               OBFX.SEQUENCIA       SEQ,
               MAX(OBFX.CODIGO_FASE||OBFX.TIPO_PROCESSO) PI,
               OBFX.CODIGO_COR_DESENHO COR,
               OBFX.ESPECIFICACAO_PRODUT EP,
               OBFX.PROCESSO_ESPECIFICO PE,
               MAX(SUBSTR(OBFX.NUMERO_MAQUINA, 7, 4)) MQ_TING,
               (SELECT MAX(UNP.DTTEMPOINICIAL) 
                  FROM SGTPRD.UP_ORDEM_MVTO       UPO, 
                       SGTPRD.UNIDADE_PROGRAMACAO UNP 
                 WHERE UPO.NUMEROUP = UNP.NUMEROUP 
                   AND UPO.NUMEROORDEMREAL = OBFX.NUMERO_OB 
                   AND UNP.TIPO_MAQUINA = 19 
                   AND UNP.EXCLUIDA = 0 
                   AND UNP.TIPOUP = 0)  INICIO_TING,
                                  
               (SELECT MAX(UNP.DTTEMPOFINAL) 
                  FROM SGTPRD.UP_ORDEM_MVTO UPO, 
                       SGTPRD.UNIDADE_PROGRAMACAO UNP 
                 WHERE UPO.NUMEROUP = UNP.NUMEROUP 
                   AND UPO.NUMEROORDEMREAL = OBFX.NUMERO_OB 
                   AND UNP.TIPO_MAQUINA = 19 
                   AND UNP.EXCLUIDA = 0 
                   AND UNP.TIPOUP = 0)    FINAL_TING
                                   
          FROM SGTPRD.OB_FASES OBFX
          JOIN SGTPRD.OB OB ON OBFX.NUMERO_OB = OB.NUMERO_OB
         WHERE OB.STATUS <> 0
           AND OBFX.CODIGO_FASE = 40
         GROUP BY OBFX.CODIGO_GRUPO,
                  OBFX.NUMERO_OB,
                  OBFX.SEQUENCIA,
                  OBFX.CODIGO_COR_DESENHO,
                  OBFX.ESPECIFICACAO_PRODUT,
                  OBFX.PROCESSO_ESPECIFICO
        ) OBF
  LEFT JOIN (SELECT TRIM(CREX.GRAFICO_RECEITA) GRAFICO,
                       DECODE(LCR.DATA_ULTIMA_PRODUC, 0, TO_DATE('31/12/1899','dd/mm/yyyy'), TO_DATE(LCR.DATA_ULTIMA_PRODUC,'rrrrmmdd')) DATA_ULT_PROD,
                       CREX.CODIGO_CLASSIFICACAO CD_CLASSIF,
                       (SELECT TRIM(CLF.DESCRICAO) FROM SGTPRD.CLASSIFICACAO_COR CLF WHERE CLF.CODIGO_CLASSIFICACAO = CREX.CODIGO_CLASSIFICACAO) CLASSIF_COR,
                       CREX.PROCESSOINDUSTRIAL PI,
                       SUBSTR(CREX.CODCOR,1,11) COR,
                       CREX.ESPECIFICACAO_PRODUT EP,
                       CREX.OBSERVACAO,
                       LCR.TIPO_DE_RECEITA,
                       CREX.CODIGO_REDUZIDO_RECE
                  FROM SGTPRD.CADASTRO_RECEITAS CREX
                  JOIN SGTPRD.LIGA_CADREC_ITEMREC LCR ON LCR.CODIGO_REDUZIDO_RECE = CREX.CODIGO_REDUZIDO_RECE
                 WHERE CREX.PROCESSO_ATIVO_PRODU = 1
                ) CRE ON CRE.PI = OBF.PI
                     AND CRE.COR = OBF.COR
                     AND CRE.EP = OBF.EP
  LEFT JOIN (SELECT LCR.CODIGO_REDUZIDO_RECE,
                       LRB.BLOQUEIO_RECEITA,
                       TO_DATE(LRB.DATA_BLOQUEIO,'YYYY/MM/DD') DATA_BLOQUEIO,
                       LRB.USUARIO_BLOQUEIO,
                       LRB.OBSERVACAO_BLOQUEIO,
                       LRB.OBEMOVIMENTO_BLOQ,
                       LRB.SEQOBEMOVIMENTO_BLOQ,
                       TO_DATE(LCR.DATA_ALTERACAO, 'YYYY/MM/DD') DATA_ALTERACAO,
                       LCR.USUARIO_ALTEROU,
                       (SELECT TRIM(CRI.NOME_USERLITERAL) FROM SGTPRD.CRISTAL CRI WHERE CRI.CODREDUSUARIO = LCR.USUARIO_ALTEROU) NOME_USUARIO_ALTEROU
                  FROM SGTPRD.LIGA_CADREC_ITEMREC LCR
                  JOIN SGTPRD.LABRECEITA_BLOQUEADA LRB ON LRB.ID_LABRECEITA_BLOQ = LCR.ID_LABRECEITA_BLOQ
                ) REC ON REC.CODIGO_REDUZIDO_RECE = CRE.CODIGO_REDUZIDO_RECE
                     AND REC.BLOQUEIO_RECEITA = 0
 ORDER BY OBF.INICIO_TING, OBF.NR_OB, OBF.GRUPO
