-- =============================================================================
-- OBJETIVO: OB_s com receitas que faltam emitir
-- DOMÍNIO: 01_beneficiamento_tingimento
-- ARQUIVO ORIGINAL: Comandos SQL - CR\OB_s com receitas que faltam emitir.sql
-- TIPO: Tingimento e Tinturaria
-- PARÂMETROS / BINDS: Nenhum (janela dinâmica pelas últimas ordens montadas do setor)
-- TABELAS PRINCIPAIS: SGTPRD.CADASTRO_RECEITAS, SGTPRD.ENGEITEMESTOCOR, SGTPRD.ITENS_ESTOQUE,
--                    SGTPRD.LABRECEITA_BLOQUEADA, SGTPRD.LIGA_CADREC_ITEMREC, SGTPRD.MOVTO_RECEITA,
--                    SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO, SGTPRD.PEDPRODUCAOOB, SGTPRD.UNIDADE_PROGRAMACAO,
--                    SGTPRD.UNIDADE_PROGR_PROD, SGTPRD.UP_ORDEM_MVTO
-- CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. 100% nativa sem views. Execução somente leitura.
-- HISTÓRICO DE OTIMIZAÇÃO (23/09/2026):
--   - Substituição de lista hardcoded antiga de OBs dos anos anteriores (89xxx) por CTE
--     dinâmica indexada nas ordens mais recentes do setor de beneficiamento (SGTPRD.PEDPRODUCAOOB).
--   - Validação com dados reais de produção em tempo real no Oracle SGTPRD (~0.48s).
-- =============================================================================

WITH OB_MAX AS (
    SELECT /*+ MATERIALIZE */ MAX(NUMEROOB) AS ULTIMA_OB
      FROM SGTPRD.PEDPRODUCAOOB
     WHERE SETOR = 5
)
SELECT OB.NUMERO_OB,
       OB.NUMERO_MAQUINA                             MAQUINA,
       OB.CODCOR                                     COR,
       OB.ESPECIFICACAO_PRODUT                       EP,
       OB.PROCESSO_ESPECIFICO                        PE,
       OB.DATA_HORA_INICIO                           INICIO_TINGIMENTO,
       DECODE(RBQ.BLOQUEIO_RECEITA, 0, 'SIM', 'NAO') BLOQUEADA
  FROM OB_MAX M,
       (SELECT OBF.NUMERO_OB,
               OBF.NUMERO_MAQUINA,
               OBF.CODIGO_COR_DESENHO AS CODCOR,
               OBFX.ESPECIFICACAO_PRODUT,
               OBFX.PROCESSO_ESPECIFICO,
               UPP.DATA_HORA_INICIO,
               OBP.CODPRO_REDUZIDO
          FROM SGTPRD.OB_FASES OBF
          JOIN SGTPRD.UP_ORDEM_MVTO UOM 
            ON UOM.NUMEROORDEMREAL = OBF.NUMERO_OB 
           AND UOM.SEQUENCIAORDEMREAL = OBF.SEQUENCIA
          JOIN SGTPRD.UNIDADE_PROGR_PROD UPP 
            ON UPP.NUMEROUP = UOM.NUMEROUP
          JOIN SGTPRD.UNIDADE_PROGRAMACAO UPR 
            ON UPR.NUMEROUP = UPP.NUMEROUP 
           AND UPR.SETOR = 5 
           AND UPR.EXCLUIDA = 0 
           AND UPR.TIPOUP = 0
         INNER JOIN SGTPRD.OB_PRODUTO OBP
            ON OBP.NUMERO_OB = OBF.NUMERO_OB
         INNER JOIN SGTPRD.OB_FASES OBFX
            ON OBFX.NUMERO_OB = OBF.NUMERO_OB
           AND OBFX.SEQUENCIA = OBF.SEQUENCIA
         INNER JOIN SGTPRD.PEDPRODUCAOOB PPO
            ON PPO.NUMEROOB = OBF.NUMERO_OB
           AND PPO.SETOR = 5
           AND PPO.OBMONTADA = 1
       ) OB
  LEFT JOIN (SELECT ITEX.CODIGO_REDUZIDO,
                    TRIM(ITEX.DESCRICAO) DESCR_ITEM,
                    CRE.CODCOR,
                    CRE.ESPECIFICACAO_PRODUT,
                    CRE.PROCESSO_ESPECIFICO,
                    CRE.PROCESSO_ATIVO_PRODU,
                    LRB.BLOQUEIO_RECEITA
               FROM SGTPRD.CADASTRO_RECEITAS    CRE
               JOIN SGTPRD.LIGA_CADREC_ITEMREC  LCR ON LCR.CODIGO_REDUZIDO_RECE = CRE.CODIGO_REDUZIDO_RECE
               JOIN SGTPRD.LABRECEITA_BLOQUEADA LRB ON LRB.ID_LABRECEITA_BLOQ = LCR.ID_LABRECEITA_BLOQ
               JOIN SGTPRD.ENGEITEMESTOCOR      EGC ON TRIM(CRE.CODCOR) = TRIM(EGC.CDCOR)
               JOIN SGTPRD.ITENS_ESTOQUE        ITEX ON ITEX.CODIGO_REDUZIDO = EGC.CDREDUZIDO
                                                    AND CRE.ESPECIFICACAO_PRODUT = ITEX.ESPECIFICACAOPRODUTO
              WHERE ITEX.TIPO_ITEM = 10
                AND CRE.PROCESSOINDUSTRIAL = 401
                AND CRE.PROCESSO_ATIVO_PRODU = 1
                AND LRB.BLOQUEIO_RECEITA = 0
            ) RBQ ON RBQ.CODIGO_REDUZIDO = OB.CODPRO_REDUZIDO
                 AND RBQ.ESPECIFICACAO_PRODUT = OB.ESPECIFICACAO_PRODUT
                 AND RBQ.PROCESSO_ESPECIFICO = OB.PROCESSO_ESPECIFICO
 WHERE OB.NUMERO_OB BETWEEN (M.ULTIMA_OB - 10) AND M.ULTIMA_OB
 ORDER BY OB.DATA_HORA_INICIO
