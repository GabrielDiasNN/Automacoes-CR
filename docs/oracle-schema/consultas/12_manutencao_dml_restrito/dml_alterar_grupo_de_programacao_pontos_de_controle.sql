/* =============================================================================
OBJETIVO: Alterar grupo de programação (pontos de controle)
DOMÍNIO: 12_manutencao_dml_restrito
ARQUIVO ORIGINAL: Comandos SQL - CR\Alterar grupo de programação (pontos de controle).sql
TIPO: DML - Atualização Controlada
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.BENEPTSCONTGRUFLUMAQ, SGTPRD.BENEPTSCONTROLEMAQ, SGTPRD.FLUXO, SGTPRD.FLUXOGRUPO, SGTPRD.GRUPO_FLUXO, SGTPRD.GRUPO_FLUXO_FASES, SGTPRD.GRUPO_FLUXO_MAQUINAS, SGTPRD.GRUPO_PRODUTO, SGTPRD.MAQUINA, SGTPRD.PTS_CONTROLE
CUIDADOS OPERACIONAIS: ESTE ARQUIVO CONTÉM DML (UPDATE) e NÃO é somente leitura. Execução apenas
  manual, por operador autorizado: rode antes o SELECT de conferência, valide as linhas afetadas e
  só então execute o UPDATE, com COMMIT consciente (ou ROLLBACK se o rowcount divergir). Ver AVISO_SEGURANCA.md.
============================================================================= */

SELECT PTC.IDPTSCONTGRUPFLUXMAQ,
       PTC.VLPONTOCONTROLE,
       PTC.VALOR_PADRAOMINIMO,
       PTC.VALOR_PADRAOMAXIMO,
       PTC.DESCRICAO_RESULTADO,
       LTRIM(MAQ.NUMERO_MAQUINA, '0') AS MAQUINA_NUM,
       MAQ.NUMERO_MAQUINA,
       MAQ.NOME_MAQUINA,
       TRIM(PT.CODIGO_PC)             AS CODIGO_PC,
       --PT.DESCRICAO_PC,
       GRP.CODIGO_GRUPO_PROGRAM,
       GRP.DESCRICAO                  AS DESCRICAO_GRUPO,
       GRP.CDITEMARTIGOCRU,
       GFF.SEQUENCIA                  AS SEQ_FASE,
       GFF.CODIGO_FASE,
       FLX.CODIGO_FLUXO,
       FLX.DESCRICAO                  AS DESCRICAO_FLUXO,
       GFM.ATIVA                      AS MAQ_FLUXO_ATIVA
FROM SGTPRD.BENEPTSCONTGRUFLUMAQ PTC
JOIN SGTPRD.BENEPTSCONTROLEMAQ   PTCM ON PTCM.IDPONTOSCONTROLEMAQ = PTC.IDPONTOSCONTROLEMAQ
JOIN SGTPRD.PTS_CONTROLE         PT   ON PT.IDPC                  = PTCM.IDPC
JOIN SGTPRD.GRUPO_FLUXO_MAQUINAS GFM  ON GFM.IDGRUPOFLUXOMAQ      = PTC.ID_GRUPO_FLUXO_MAQ
JOIN SGTPRD.GRUPO_FLUXO_FASES    GFF  ON GFF.IDGRUPOFLUXOFASE     = GFM.IDGRUPOFLUXOFASE
JOIN SGTPRD.GRUPO_FLUXO          GPF  ON GPF.IDGRUPOFLUXO         = GFF.IDGRUPOFLUXO
JOIN SGTPRD.GRUPO_PRODUTO        GRP  ON GRP.NUMERO_GRUPO_PROGRAM = GPF.NUMERO_GRUPO_PROGRAM
JOIN SGTPRD.MAQUINA              MAQ  ON MAQ.NUMERO_MAQUINA       = GFM.NUMERO_MAQUINA
-- FLUXO e FLUXOGRUPO são INNER JOIN de propósito: além das colunas, restringem o escopo
-- a pontos cujo fluxo existe e tem grupo. O UPDATE abaixo usa os mesmos joins, então
-- este SELECT confere exatamente as linhas que ele altera.
JOIN SGTPRD.FLUXO                FLX  ON FLX.CODIGO_FLUXO         = GPF.CODIGO_FLUXO
JOIN SGTPRD.FLUXOGRUPO           FLG  ON FLG.ID                   = FLX.IDFLUXOGRUPO
WHERE TRIM(PT.CODIGO_PC) = 'AB01'
AND   SUBSTR(GRP.CODIGO_GRUPO_PROGRAM, 6, 3) IN ('184','187','140') -- mesmo filtro e joins do UPDATE abaixo
ORDER BY MAQ.NUMERO_MAQUINA,
         GRP.CODIGO_GRUPO_PROGRAM,
         GFF.SEQUENCIA,
         PT.CODIGO_PC;
-----------------------------------------------------------------------------------------------------------------------------------
UPDATE SGTPRD.BENEPTSCONTGRUFLUMAQ PTC
SET PTC.VLPONTOCONTROLE    = '200                          ', --(VARCHAR2(30))
    PTC.VALOR_PADRAOMINIMO = 200,                             --(FLOAT)
    PTC.VALOR_PADRAOMAXIMO = 200                              --(FLOAT)
WHERE PTC.IDPTSCONTGRUPFLUXMAQ IN (
                                    SELECT PTC.IDPTSCONTGRUPFLUXMAQ
                                    FROM SGTPRD.BENEPTSCONTGRUFLUMAQ PTC
                                    JOIN SGTPRD.BENEPTSCONTROLEMAQ   PTCM ON PTCM.IDPONTOSCONTROLEMAQ = PTC.IDPONTOSCONTROLEMAQ
                                    JOIN SGTPRD.PTS_CONTROLE         PT   ON PT.IDPC                  = PTCM.IDPC
                                    JOIN SGTPRD.GRUPO_FLUXO_MAQUINAS GFM  ON GFM.IDGRUPOFLUXOMAQ      = PTC.ID_GRUPO_FLUXO_MAQ
                                    JOIN SGTPRD.GRUPO_FLUXO_FASES    GFF  ON GFF.IDGRUPOFLUXOFASE     = GFM.IDGRUPOFLUXOFASE
                                    JOIN SGTPRD.GRUPO_FLUXO          GPF  ON GPF.IDGRUPOFLUXO         = GFF.IDGRUPOFLUXO
                                    JOIN SGTPRD.GRUPO_PRODUTO        GRP  ON GRP.NUMERO_GRUPO_PROGRAM = GPF.NUMERO_GRUPO_PROGRAM
                                    JOIN SGTPRD.MAQUINA              MAQ  ON MAQ.NUMERO_MAQUINA       = GFM.NUMERO_MAQUINA
                                    -- Filtros de existência (ver o SELECT acima): não trocar por LEFT JOIN.
                                    JOIN SGTPRD.FLUXO                FLX  ON FLX.CODIGO_FLUXO         = GPF.CODIGO_FLUXO
                                    JOIN SGTPRD.FLUXOGRUPO           FLG  ON FLG.ID                   = FLX.IDFLUXOGRUPO
                                    WHERE TRIM(PT.CODIGO_PC) = 'AB01'
                                    AND   SUBSTR(GRP.CODIGO_GRUPO_PROGRAM, 6, 3) IN ('184','187','140')
                                  );
