/* =============================================================================
OBJETIVO: OBs montadas fora da regra de separação
DOMÍNIO: 06_qualidade_auditoria_obs
ARQUIVO ORIGINAL: Comandos SQL - CR\OBs montadas fora da regra de separação.sql
TIPO: Auditoria e Qualidade de OBs
PARÂMETROS / BINDS: Nenhum (filtros diretos na query)
TABELAS PRINCIPAIS: SGTPRD.ENGEITEMESTOARTCRU, SGTPRD.ENGEITEMESTOCOR, SGTPRD.FASES_FLUXO, SGTPRD.GERAPECACOMPLPECA, SGTPRD.GERAPECACRU, SGTPRD.GERAPECAORIGEMOB, SGTPRD.GERAPECASPRODUTO, SGTPRD.GRUPO_MAQUINAS, SGTPRD.LOTES_FIO_PRODUTO, SGTPRD.MAQUINA, SGTPRD.OB, SGTPRD.OBSERVACAO, SGTPRD.OB_FASES, SGTPRD.OPERADOR
CUIDADOS OPERACIONAIS: Query operacional do acervo SGT. Execução somente leitura salvo se DML restrito.
OTIMIZAÇÃO (20/09/2026): View VW_BNF_FASEATUALOB substituída pela resolução física nativa em OB_FASES + FASES_FLUXO.
REVISÃO (20/09/2026 - Onda 4): OPTSTRAGGR substituído por LISTAGG nativo.
  FNC_DATATEMPO substituído por expressão inline (LPAD + TO_DATE + TO_CHAR) — mesma técnica
  usada em est_conferencia_ob_montada_deposito_90_direto_para_o_100.sql.
  guard_sql.py: exit 0.
REVISÃO (08/10/2026): a subconsulta GRP juntava GRUPO_MAQUINAS só por GRUPO. A chave é (SETOR, GRUPO),
  e os grupos 0G020 e 0G021 existem nos setores 4 e 7. Com a junção antiga, cada máquina desses grupos
  recebia também a linha do setor 7 (agulhas 0), o que inflava COUNT(DISTINCT agulhas) e podia marcar
  REGRA_AGULHAS = 1 sem motivo. Join corrigido com GRM.SETOR = MQ.SETOR (GRP 95 -> 87 linhas).
  Efeito medido em 09/10/2026 no Oracle: a saída final tem 35 linhas e 35 OBs com o join corrigido e com o
  join antigo (só GRUPO), registros idênticos; nenhuma OB entra nem sai. Em 08/10/2026 a mesma saída tinha 40
  linhas (REGRAS_NEGOCIO.md, seção 5.1; a diferença não foi investigada). Sem o filtro externo (65 linhas
  nas duas versões), só REGRA_AGULHAS muda, em 3 linhas do artigo 00149 (OBs 189157, 190111 e 190112), de 1
  para 0; as 3 continuam fora da saída, pois 00149 só usa REGRA_FABRICANTE_MODELO. Nenhuma linha do artigo
  00044 muda REGRA_AGULHAS.
  TP_ORDEM: DECODE alinhado a mal_obs_lotes_teares_misturados.sql (cadastro SGTPRD.DESTINO). Os rótulos
  1, 2 e 4 não mudam; 0 e NULO viram 'Sem destino cadastrado'; 3 e 10 são mapeados; o resto vira
  'Não mapeado'. Medido em 09/10/2026: a saída tem 'Produção' (34) e 'Reclassificação' (1), então nenhuma
  linha troca de rótulo.
  REVISÃO (09/10/2026): OB sem nenhuma linha em OB_FASES não entra em TP_ORDEM_CTE e saía com
  TP_ORDEM NULL no LEFT JOIN, sem o rótulo 'Sem destino cadastrado' (0 e NULO de DESTINO_RECEITA).
  O SELECT final usa NVL(TP.TP_ORDEM, 'Sem destino cadastrado'), como mal_obs_lotes_teares_misturados.sql.
  Medido em 09/10/2026 (06:38): saída de 38 OBs (Produção 37, Reclassificação 1) idêntica em bytes
  antes e depois da troca. Efeito só se a OB não tiver OB_FASES, caso não observado na saída.
============================================================================= */

WITH TP_ORDEM_CTE AS (
    SELECT
        OBFXX.NUMERO_OB,
        DECODE(NVL(MAX(OBFXX.DESTINO_RECEITA), 0),
               0, 'Sem destino cadastrado',
               1, 'Produção',
               2, 'Reprocesso',
               3, 'Limpeza de máquina',
               4, 'Reclassificação',
               10, 'Consumo',
               'Não mapeado') AS TP_ORDEM
    FROM SGTPRD.OB_FASES OBFXX
    GROUP BY OBFXX.NUMERO_OB
),
COR_CTE AS (
    SELECT
        OBE.NUMERO_OB,
        COALESCE(
            MAX(RPAD(COR_FASE.CODIGO_COR_DESENHO, 10, ' ')),
            RPAD(COR_ESTOQUE.CDCOR, 10, ' ')
        ) AS COR
    FROM SGTPRD.OB OBE
    LEFT JOIN SGTPRD.OB_FASES COR_FASE
        ON COR_FASE.NUMERO_OB = OBE.NUMERO_OB
       AND COR_FASE.CODIGO_FASE = 40
    LEFT JOIN SGTPRD.ENGEITEMESTOCOR COR_ESTOQUE
        ON COR_ESTOQUE.CDREDUZIDO = OBE.CODIGO_REDUZIDO
    GROUP BY OBE.NUMERO_OB, RPAD(COR_ESTOQUE.CDCOR, 10, ' ')
),
FASE_ATUAL_CTE AS (
    SELECT
        OBF.NUMERO_OB,
        MIN(FFL.DESCRICAO_FASE) KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA) AS FASE_ATUAL,
        DECODE(MIN(OBF.STATUS) KEEP (DENSE_RANK FIRST ORDER BY OBF.SEQUENCIA),
               0, 'PROGRAMADA',
               1, 'EMITIDA',
               2, 'PESADA',
               3, 'EM EXECUÇÃO') AS ST_FASE
    FROM SGTPRD.OB_FASES OBF
    JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
    WHERE OBF.STATUS <> 4
    GROUP BY OBF.NUMERO_OB
),
OPERADOR_CTE AS (
    SELECT
        OBF.NUMERO_OB,
        TRIM(LISTAGG(OPE.NOME, ', ') WITHIN GROUP (ORDER BY OBF.SEQUENCIA)) AS OPERADOR,
        MIN(CASE WHEN OBF.TEMPO_FINAL_CONFIRMA BETWEEN 0 AND 235959
                 THEN TO_CHAR(
                        TO_DATE(LPAD(TO_CHAR(OBF.TEMPO_FINAL_CONFIRMA), 6, '0'), 'HH24MISS'),
                        'HH24:MI:SS')
            END) AS HORARIO_CONFIRMADO
    FROM SGTPRD.OB_FASES OBF
    JOIN SGTPRD.OPERADOR OPE ON OPE.CODIGO = OBF.OPERADOR_FINAL
    WHERE OBF.CODIGO_FASE = 10
    GROUP BY OBF.NUMERO_OB
),
ANALISE_CTE AS (
    SELECT
        X.NUMERO_OB,
        X.REDUZIDO_CRU,
        X.REGRA_FINALIDADE,
        X.REGRA_LOTE_PRODUTO,
        X.REGRA_LOTE_FIO,
        X.REGRA_AGULHAS,
        X.REGRA_FABRICANTE_MODELO,
        X.REGRA_MAQUINA,
        X.ARTIGO,
        X.OBSERVACAO_OB
    FROM (
        SELECT
            GPO.NUMERO_OB,
            NVL(GPP.CODIGO_REDUZIDO_PROD, OB.CODIGO_REDUZIDO_CRU) REDUZIDO_CRU,
            CASE WHEN COUNT(DISTINCT GPC.FINALIDADE) > 2 THEN 1 ELSE 0 END AS REGRA_FINALIDADE,
            CASE WHEN COUNT(DISTINCT GPP.LOTE_PRODUTO) > 1 THEN 1 ELSE 0 END AS REGRA_LOTE_PRODUTO,
            CASE WHEN COUNT(DISTINCT LFP.LOTE_PRODUTO_CRU) > 1 THEN 1 ELSE 0 END AS REGRA_LOTE_FIO,
            CASE WHEN COUNT(DISTINCT GRP.NUMERO_AGULHAS_CILIN) > 1 THEN 1 ELSE 0 END AS REGRA_AGULHAS,
            CASE WHEN COUNT(DISTINCT GRP.FABRICANTE_MODELO) > 1 THEN 1 ELSE 0 END AS REGRA_FABRICANTE_MODELO,
            CASE WHEN COUNT(DISTINCT GPR.NUMERO_MAQUINA) > 1 THEN 1 ELSE 0 END AS REGRA_MAQUINA,
            ART.CDARTIGOCRU AS ARTIGO,
            OBS.TEXTO AS OBSERVACAO_OB
        FROM SGTPRD.GERAPECAORIGEMOB GPO
        JOIN SGTPRD.GERAPECACOMPLPECA GPC ON GPC.IDPECASPRODUTO = GPO.IDPECASPRODUTO
        JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.IDPECASPRODUTO = GPO.IDPECASPRODUTO
        JOIN SGTPRD.OB OB
            ON GPO.NUMERO_OB = OB.NUMERO_OB
           AND OB.STATUS <> 0
           AND OB.TIPO_ORDEM = 0
        JOIN SGTPRD.ENGEITEMESTOARTCRU ART
            ON ART.CDREDUZIDO = OB.CODIGO_REDUZIDO_CRU
        LEFT JOIN SGTPRD.OBSERVACAO OBS
            ON OBS.CODIGO = OB.CODIGO_OBSERVACAO
        JOIN SGTPRD.GERAPECACRU GPR ON GPR.IDPECASPRODUTO = GPO.IDPECASPRODUTO
        JOIN SGTPRD.LOTES_FIO_PRODUTO LFP ON LFP.LOTE_PRODUTO_CRU = GPP.LOTE_PRODUTO
        JOIN (
            SELECT
                MQ.NUMERO_MAQUINA,
                GRM.NUMERO_AGULHAS_CILIN,
                GRM.NUMERO_AGULHAS_DISCO,
                TRIM(MQ.FABRICANTE) || ' - ' || TRIM(MQ.MODELO) FABRICANTE_MODELO
            FROM SGTPRD.MAQUINA MQ
            JOIN SGTPRD.GRUPO_MAQUINAS GRM ON MQ.GRUPO = GRM.GRUPO AND GRM.SETOR = MQ.SETOR
            WHERE MQ.TIPO_MAQUINA = 145
              AND MQ.CODIGO_UNIDADE_FABRI = '00005'
            GROUP BY MQ.NUMERO_MAQUINA, GRM.NUMERO_AGULHAS_CILIN, GRM.NUMERO_AGULHAS_DISCO,
                     TRIM(MQ.FABRICANTE) || ' - ' || TRIM(MQ.MODELO)
        ) GRP ON GPR.NUMERO_MAQUINA = GRP.NUMERO_MAQUINA
        WHERE
            GPP.TIDOCUMENTOENTRADA <> 8
            AND GPP.PADRAO_QUALIDADE_SIN = 1
            AND OB.CODIGO_REDUZIDO IN (
                SELECT ENG.CDREDUZIDO
                FROM SGTPRD.ENGEITEMESTOCOR ENG
                WHERE RPAD(ENG.CDCOR, 10, ' ') <> RPAD('99999', 10, ' ')
            )
            AND ART.CDARTIGOCRU IN (
                RPAD('00044', 10, ' '), RPAD('00047', 10, ' '), RPAD('00066', 10, ' '),
                RPAD('00149', 10, ' '), RPAD('00183', 10, ' '), RPAD('00189', 10, ' '),
                RPAD('00489', 10, ' '), RPAD('00042', 10, ' '), RPAD('00184', 10, ' '),
                RPAD('00442', 10, ' '), RPAD('00484', 10, ' ')
            )
        GROUP BY
            GPO.NUMERO_OB, NVL(GPP.CODIGO_REDUZIDO_PROD, OB.CODIGO_REDUZIDO_CRU),
            ART.CDARTIGOCRU, OBS.TEXTO
    ) X
    WHERE
        --Separar Somente Grupo de Máquina
        (X.ARTIGO = RPAD('00149', 10, ' ') AND X.REGRA_FABRICANTE_MODELO <> 0)
        OR
        --Separar Lote de Fio, Qtd. de Agulhas e Grupo de Máquinas
        (X.ARTIGO IN (
            RPAD('00044', 10, ' '), RPAD('00047', 10, ' '), RPAD('00066', 10, ' '),
            RPAD('00183', 10, ' '), RPAD('00189', 10, ' '), RPAD('00489', 10, ' ')
         )
         AND (X.REGRA_LOTE_FIO <> 0 OR X.REGRA_AGULHAS <> 0 OR X.REGRA_FABRICANTE_MODELO <> 0))
        OR
        --Separar Somente Lote de Fio
        (X.ARTIGO IN (RPAD('00042', 10, ' '), RPAD('00184', 10, ' '), RPAD('00442', 10, ' '), RPAD('00484', 10, ' '))
         AND X.REGRA_LOTE_FIO <> 0)
)
SELECT
    A.NUMERO_OB,
    NVL(TP.TP_ORDEM, 'Sem destino cadastrado') AS TP_ORDEM,
    A.ARTIGO,
    COR.COR,
    --A.REGRA_FINALIDADE,
    A.REGRA_LOTE_PRODUTO,
    A.REGRA_LOTE_FIO,
    A.REGRA_AGULHAS,
    A.REGRA_FABRICANTE_MODELO,
    A.REGRA_MAQUINA,
    FASE.FASE_ATUAL,
    FASE.ST_FASE,
    OPE.OPERADOR,
    OPE.HORARIO_CONFIRMADO,
    A.OBSERVACAO_OB
FROM ANALISE_CTE A
LEFT JOIN TP_ORDEM_CTE TP ON TP.NUMERO_OB = A.NUMERO_OB
LEFT JOIN COR_CTE COR ON COR.NUMERO_OB = A.NUMERO_OB
LEFT JOIN FASE_ATUAL_CTE FASE ON FASE.NUMERO_OB = A.NUMERO_OB
LEFT JOIN OPERADOR_CTE OPE ON OPE.NUMERO_OB = A.NUMERO_OB
ORDER BY OPE.HORARIO_CONFIRMADO
