let
    // 🔹 Definições Centralizadas
    TiposFinais = {
        {"GRUPO", Int64.Type}, {"NUMERO_OB", Int64.Type}, {"PESADA", Text.Type},
        {"MQ_TING", Text.Type}, {"INICIO_TING", DateTime.Type}, {"FINAL_TING", DateTime.Type},
        {"ARTIGO", Text.Type}, {"REDUZIDO", Int64.Type}, {"DESCRICAO", Text.Type},
        {"FASE_ATUAL", Text.Type}, {"STATUS_FASE", Text.Type}, {"USUARIO", Text.Type},
        {"HORARIO_PESADO", DateTime.Type}, {"DIAS_PESADO", Number.Type}, {"QUANT_PESADA", Number.Type}
    },

    // 🔹 Consulta SQL Otimizada
    ConsultaSQL_Otimizada = "
WITH
    TINGIMENTO_TEMPOS AS (
        SELECT
            UPO.NUMEROORDEMREAL AS NUMERO_OB,
            MAX(UNP.DTTEMPOINICIAL) AS INICIO_TING,
            MAX(UNP.DTTEMPOFINAL) AS FINAL_TING
        FROM SGTPRD.UP_ORDEM_MVTO UPO
        JOIN SGTPRD.UNIDADE_PROGRAMACAO UNP ON UPO.NUMEROUP = UNP.NUMEROUP
        WHERE UNP.TIPO_MAQUINA = 19 
        AND UNP.EXCLUIDA = 0 
        --AND UNP.TIPOUP = 0 
        GROUP BY UPO.NUMEROORDEMREAL
    ),

    MAQUINAS_TINGIMENTO AS (
        SELECT 
            NUMERO_OB,
            MAX(LTRIM(NUMERO_MAQUINA, '0')) AS MQ_TING
        FROM SGTPRD.OB_FASES 
        WHERE CODIGO_FASE = 40
        GROUP BY NUMERO_OB
    ),

    DADOS_AGREGADOS AS (
        SELECT
            OBF.NUMERO_OB, M.NUMEROORDEM, OBF.CODIGO_GRUPO, OBP.CODPRO_REDUZIDO,
            MAX(TRIM(OPE.NOME)) AS USUARIO,
            MAX(M.DT_PESAGEM) AS HORARIO_PESADO,
            SUM(M.QUANTIDADEPESADA) AS QUANT_PESADA
        FROM SGTPRD.OB_FASES OBF
        JOIN SGTPRD.VW_BNF_FASEATUALOB OB ON OB.NUMERO_OB = OBF.NUMERO_OB
        JOIN SGTPRD.OB_PRODUTO OBP ON OBP.NUMERO_OB = OBF.NUMERO_OB
        JOIN SGTPRD.MOVTO_RECEITA M ON M.NUMEROORDEM = OBF.NUMEROORDEMMOVIMENTO 
            AND M.SEQUENCIAFASEOB = OBF.SEQUENCIAORDEMMOVIME
        LEFT JOIN SGTPRD.OPERADOR OPE ON OPE.IDOPERADOR = M.IDOPE_PESAGEM
        WHERE OBF.CODIGO_FASE = 40 AND OBF.STATUS IN (1, 2, 3)
        GROUP BY OBF.NUMERO_OB, M.NUMEROORDEM, OBF.CODIGO_GRUPO, OBP.CODPRO_REDUZIDO
    )

SELECT /*+ FIRST_ROWS(1000) */
    BASE.CODIGO_GRUPO AS GRUPO, BASE.NUMERO_OB,
    CASE WHEN SGTPRD.FNC_ESP_REC_PES(BASE.NUMERO_OB) = 0 THEN 'NÃO' ELSE 'SIM' END AS PESADA,
    MT.MQ_TING, TT.INICIO_TING, TT.FINAL_TING,
    ART.CDARTIGOCRU AS ARTIGO, BASE.CODPRO_REDUZIDO AS REDUZIDO,
    TRIM(ITE.DESCRICAO) AS DESCRICAO, FAS.DESCR_FASE AS FASE_ATUAL,
    CASE FAS.STATUS 
        WHEN 0 THEN 'PROGRAMADA' WHEN 1 THEN 'EMITIDA' 
        WHEN 2 THEN 'PESADA' WHEN 3 THEN 'EM EXECUÇÃO' 
    END AS STATUS_FASE,
    BASE.USUARIO, BASE.HORARIO_PESADO,
    ROUND((SYSDATE) - BASE.HORARIO_PESADO, 2) AS DIAS_PESADO,
    BASE.QUANT_PESADA
FROM DADOS_AGREGADOS BASE
LEFT JOIN TINGIMENTO_TEMPOS TT ON TT.NUMERO_OB = BASE.NUMERO_OB
LEFT JOIN MAQUINAS_TINGIMENTO MT ON MT.NUMERO_OB = BASE.NUMERO_OB
LEFT JOIN SGTPRD.ENGEITEMESTOARTCRU ART ON ART.CDREDUZIDO = BASE.CODPRO_REDUZIDO
LEFT JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = BASE.CODPRO_REDUZIDO
LEFT JOIN SGTPRD.VW_BNF_FASEATUALOB FAS ON FAS.NUMERO_OB = BASE.NUMERO_OB
ORDER BY TT.INICIO_TING NULLS LAST
",

    // 🔹 Modelo Vazio Tipado
    TabelaModeloVazia = Table.TransformColumnTypes(#table({}, {}), TiposFinais),

    // 🔹 Execução Segura com Validação
    FonteSegura = try (
        let 
            Resultado = Oracle.Database("dbprd", [
                HierarchicalNavigation = true, 
                Query = ConsultaSQL_Otimizada,
                // CommandTimeout: 10 min — padrão do projeto
                CommandTimeout = #duration(0, 0, 10, 0)
            ])
        in 
            if Table.IsEmpty(Resultado) then TabelaModeloVazia else Resultado
    ) otherwise TabelaModeloVazia,

    // 🔹 Buffer e Validação
    DadosEmBuffer = Table.Buffer(FonteSegura),
    DadosValidados = Table.SelectRows(DadosEmBuffer, each [NUMERO_OB] <> null and [NUMERO_OB] > 0),

    // 🔹 Tipagem Final
    ResultadoFinal = Table.TransformColumnTypes(DadosValidados, TiposFinais)
in
    ResultadoFinal