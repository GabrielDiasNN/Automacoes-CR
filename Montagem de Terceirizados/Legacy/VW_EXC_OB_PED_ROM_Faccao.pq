let
    // -----------------------------------------------------------------------
    // CONFIGURAÇÃO DA QUERY (Mapeamento Explícito VBA <-> Oracle)
    // -----------------------------------------------------------------------
    // Adicionamos 'SYSDATE AS Valida_Atualizacao' para capturar a data/hora do servidor
    ConsultaSQL = "
        SELECT 
            -- Carimbo de Data/Hora da extração
            SYSDATE AS Valida_Atualizacao,
            
            -- Campos Chaves (Validadores)
            V.CD_REF_CLT,
            V.QT_PC_NF,
            TRIM(V.OBS_OB) AS OBS_OB,
            V.NR_OB,
            CAST(NULL AS VARCHAR2(100)) AS VALIDACAO_NF,
            
            -- Campos Informativos (Relatório)
            V.ST_OB_ABERTO,
            V.NR_PROG,
            V.DS_ITEMPED_CLT,
            V.QT_PC_PROG,
            V.NR_KANBAN,
            V.CD_ALTERNATIVO,
            V.DS_FASE_ATUAL,
            V.DS_ST_FASE_ATUAL,
            V.DT_ULT_CONFIRMACAO

        FROM sgtprd.VW_EXC_OB_PED_ROM V
        
        WHERE V.ST_PED_ABERTO = 1
          AND V.ST_VARIOS_FAT IN (0, 1)
          AND V.OB_FAT_TOTAL = 0
          AND V.ST_BLQ_FAT IN (0, 2)
          AND V.NR_PROG LIKE '%T'      
          AND V.ST_OB_MONTADA = '1'    
          AND V.CD_DEST_REC = 1
        ORDER BY NR_PROG, DS_ITEMPED_CLT, CD_ALTERNATIVO, ST_OB_ABERTO, DT_ULT_CONFIRMACAO DESC   
    ",

    // -----------------------------------------------------------------------
    // EXECUÇÃO NO SERVIDOR
    // -----------------------------------------------------------------------
    Fonte = Oracle.Database("dbprd", [
        HierarchicalNavigation = true, 
        Query = ConsultaSQL,
        // CommandTimeout reduz travamentos se o banco demorar (10 minutos)
        CommandTimeout = #duration(0, 0, 10, 0) 
    ]),
    
    // Passo adicional para garantir que os espaços em branco na coluna OBS_OB sejam removidos
    #"Texto Aparado" = Table.TransformColumns(Fonte,{{"OBS_OB", Text.Trim, type text}})
in
    #"Texto Aparado"