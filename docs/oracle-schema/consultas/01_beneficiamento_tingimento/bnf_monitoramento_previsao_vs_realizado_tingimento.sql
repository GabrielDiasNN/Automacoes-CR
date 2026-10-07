/* =============================================================================
OBJETIVO: Monitoramento mensal de previsões de tingimento versus realizado
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO ORIGINAL: SQL Reference\templates\monitoramento_previsao_vs_realizado_tingimento.sql
TIPO: SELECT (Template Analítico / Operacional)
PARÂMETROS / BINDS: Nenhum (mês calculado por SYSDATE nesta versão)
TABELAS PRINCIPAIS: SGTPRD.UNIDADE_PROGRAMACAO, SGTPRD.UP_ORDEM_MVTO, SGTPRD.OB_FASES, SGTPRD.OB_PRODUTO
CUIDADOS OPERACIONAIS: Template somente leitura; conferir competência mensal antes da execução.
============================================================================= */
-- ====================================================================================
-- SGT / BENEFICIAMENTO - MONITORAMENTO MENSAL DE PREVISÕES DE TINGIMENTO VS REALIZADO
-- VERSÃO 4.1 (ANÁLISE MENSAL OTIMIZADA: REPROCESSOS, DEFEITOS, QUANTIDADES E OPERAÇÃO)
-- ====================================================================================
-- Objetivo:
--   Painel analítico e operacional mensal para controle rigoroso de aderência da produção
--   de Tingimento (Fase 40 / Setor 5 da Cativa/Systêxtil), rastreando:
--     1. Aderência temporal (Previsão PCP vs Apontamento Real de Chão de Fábrica)
--     2. Gestão de Reprocessos (Indicador binário SIM/NÃO, tipos e quilos reprocessados)
--     3. Defeitos de Qualidade e Não Conformidades (Grupos, tipos, quilos rejeitados e ACPNC)
--     4. Enriquecimento Operacional (Turnos, operadores de início/fim, clientes e pedidos)
--     5. Eficiência de Carga (Partidas compartilhadas na barca/jet e ocupação real)
--     6. Paradas de Máquina (com filtro temporal indexado) e Gargalos da fase antecedente
--
-- Coerência Humana & Regras de Negócio:
--   - FILTRO MENSAL: Parametrizável por mês fechado (padrão: Mês Corrente via TRUNC(SYSDATE, 'MM')).
--   - APONTAMENTO REAL: Somente considerado quando confirmado pelo operador no chão de fábrica
--     (tempoiniconfirmado > 0 e tempofinalconfirmado > 0), evitando armadilha do APS que grava
--     simulações futuras em dttempoinicial.
--   - REPROCESSO: Identificado por destino da receita (2=Fora de Cor, 4=Reclassificação/Qualidade),
--     sequência da fase > 30 (retefação/2ª passagem) ou cadastro em OB_REPROCESSO.
--   - DEFEITOS: Rastreamento em OB_FASES (grupo/tipo defeito) e OB_QUALIDADE (quilos rejeitados).
--   - OTIMIZAÇÃO: Filtro indexado em PARADAS_MAQUINA (DT_NUM_INI/FIM) e FASE_ANTERIOR por UP.
-- ====================================================================================

WITH PARAMETROS AS (
    SELECT
        -- Defina o mês inicial e final desejados (padrão: Mês Corrente):
        -- Para fixar um mês específico, altere para ex: TO_DATE('2026-09-01', 'YYYY-MM-DD')
        TRUNC(SYSDATE, 'MM') AS DT_INICIO,
        ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1) AS DT_FIM,
        TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYY-MM') AS COMPETENCIA,
        TO_NUMBER(TO_CHAR(TRUNC(SYSDATE, 'MM') - 2, 'YYYYMMDD')) AS DT_NUM_INI,
        TO_NUMBER(TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1), 'YYYYMMDD')) AS DT_NUM_FIM
    FROM DUAL
),
UP_BASE AS (
    -- Extrai as UPs de Tingimento da competência mensal desejada
    SELECT
        upr.numeroup,
        upr.numero_maquina,
        TRIM(maq.nome_maquina) AS nome_maquina,
        maq.tipo_maquina,
        upr.status AS status_up,
        uom.numeroordemreal AS numero_ob,
        uom.sequenciaordemreal AS seq,
        upr.dttempoiniprogramado,
        upr.dttempofinalprograma,
        -- Apontamentos Reais de Início e Término confirmados pelo operador:
        CASE
            WHEN upr.tempoiniconfirmado > 0 AND upr.dttempoiniconfirmado > TO_DATE('1950-01-01', 'YYYY-MM-DD') THEN
                upr.dttempoiniconfirmado
            ELSE NULL
        END AS dt_real_inicio,
        CASE
            WHEN upr.tempofinalconfirmado > 0 AND upr.dttempofinalconfirma > TO_DATE('1950-01-01', 'YYYY-MM-DD') THEN
                upr.dttempofinalconfirma
            ELSE NULL
        END AS dt_real_fim,
        upr.tempoinicial,
        upr.tempofinal,
        upr.nrturnoini,
        upr.nrturnofim,
        -- Duração Prevista em minutos:
        CASE
            WHEN upr.duracao_prevista <> 0 THEN ROUND(upr.duracao_prevista * 1440, 0)
            WHEN upr.tempofinalprogramado <> 0 THEN ROUND((upr.tempofinalprogramado - upr.tempoiniprogramado) * 1440, 0)
            WHEN upr.tempofinalplanejado <> 0 THEN ROUND((upr.tempofinalplanejado - upr.tempoiniplanejado) * 1440, 0)
            ELSE ROUND((upr.dttempofinalprograma - upr.dttempoiniprogramado) * 1440, 0)
        END AS min_prev,
        -- Janela efetiva para cruzamento temporal de paradas:
        upr.dttempoiniprogramado AS dt_janela_ini,
        NVL(upr.dttempofinalconfirma, NVL(upr.dttempofinalprograma, SYSDATE)) AS dt_janela_fim
    FROM SGTPRD.unidade_programacao upr
    JOIN SGTPRD.up_ordem_mvto uom ON uom.numeroup = upr.numeroup
    JOIN SGTPRD.maquina maq ON maq.numero_maquina = upr.numero_maquina
    JOIN PARAMETROS p ON 1=1
    WHERE upr.setor = 5
      AND upr.codigofase = 40
      AND upr.excluida = 0
      AND upr.dttempoiniprogramado >= p.dt_inicio
      AND upr.dttempoiniprogramado < p.dt_fim
),
PARADAS_PROC_UP AS (
    -- Pré-agregação otimizada das paradas internas registradas na UP (TIPOUP = 5) via índice UNIDPROG_IND_UP_TIPOUP
    SELECT
        up.numeroup,
        TRUNC(SUM(upa.tempofinal - upa.tempoinicial) * 1440) AS min_par_proc
    FROM UP_BASE up
    JOIN SGTPRD.unidade_programacao upa ON upa.tipoup = 5
                                       AND upa.status = 0
                                       AND upa.setor = 5
                                       AND upa.numero_maquina = up.numero_maquina
                                       AND upa.excluida = 0
                                       AND upa.tempoinicial >= up.tempoinicial
                                       AND upa.tempofinal <= up.tempofinal
    GROUP BY up.numeroup
),
OBS_FILTRO AS (
    SELECT DISTINCT numero_ob FROM UP_BASE
),
DADOS_OB_TINGIMENTO AS (
    -- Dados cadastrais da OB, produto, cor, cliente, pedido, operadores e defeitos de fase
    SELECT
        obf.numero_ob,
        obf.sequencia,
        obf.codigo_fase,
        obf.status AS status_fase,
        obf.codigo_grupo AS grupo_partida,
        oby.codpro_reduzido,
        TRIM(ite.descricao) AS descr_artigo,
        TRIM(lp.descricaolinha) AS linha_produto,
        TRIM(pfj.nomefantasia) AS nome_cliente,
        NVL(oby.numero_pedido, 0) AS numero_pedido,
        oby.data_entrega_pedido,
        NVL(oby.total_pecas, 0) AS total_pecas,
        TRIM(obf.codigo_cor_desenho) AS codigo_cor,
        NVL(oby.kilos, 0) AS kilos_ob,
        NVL(obf.kilos_produzidos, 0) AS kilos_produzidos,
        NVL(obf.carga_maxima, 0) AS carga_maxima_maq,
        obf.destino_receita,
        NVL(gdx.tipo_destino, 0) AS reprocesso_flag,
        TRIM(dex.descricao) AS descr_destino,
        TRIM(obf.grupo_defeito) AS grupo_defeito,
        obf.tipo_defeito,
        TRIM(gip.descricao_grupo) AS descr_grupo_def,
        TRIM(tip.descricao_tipo) AS descr_tipo_def,
        obf.red_ob_qualidade,
        TRIM(obf.operador_inicio) AS operador_inicio,
        TRIM(obf.operador_final) AS operador_final
    FROM SGTPRD.ob_fases obf
    JOIN OBS_FILTRO fil ON fil.numero_ob = obf.numero_ob
    JOIN SGTPRD.ob_produto oby ON oby.numero_ob = obf.numero_ob
    LEFT JOIN SGTPRD.itens_estoque ite ON ite.codigo_reduzido = oby.codpro_reduzido
    LEFT JOIN SGTPRD.linha_produto lp ON lp.codigolinha = ite.linha_produto
    LEFT JOIN SGTPRD.pessoasfj pfj ON pfj.idpessoafj = oby.idpessoafj
    LEFT JOIN SGTPRD.destino dex ON dex.destino = obf.destino_receita
    LEFT JOIN SGTPRD.grupo_destino gdx ON gdx.codigo_grupo = dex.codigo_grupo
    LEFT JOIN SGTPRD.grupo_defeito_qualid gip ON gip.codigo_grupo = obf.grupo_defeito
    LEFT JOIN SGTPRD.tipo_defeito_qualida tip ON tip.codigo_grupo = obf.grupo_defeito AND tip.codigo_tipo = obf.tipo_defeito
    WHERE obf.codigo_fase = 40
),
CARGA_PARTIDA_GRUPO AS (
    -- Carga compartilhada da partida na barca (múltiplas OBs da mesma cor tingidas juntas)
    SELECT
        dot.numero_ob,
        dot.sequencia,
        dot.grupo_partida,
        CASE
            WHEN dot.grupo_partida <> 0 THEN
                SUM(dot.kilos_ob) OVER (PARTITION BY dot.grupo_partida)
            ELSE dot.kilos_ob
        END AS kilos_total_partida,
        CASE
            WHEN dot.grupo_partida <> 0 THEN
                COUNT(*) OVER (PARTITION BY dot.grupo_partida)
            ELSE 1
        END AS qtd_obs_na_partida
    FROM DADOS_OB_TINGIMENTO dot
),
AJUSTES_RECEITA AS (
    -- Contagem de correções de cor e adições químicas na receita durante o processo
    SELECT
        mr.numeroordem AS numero_ob,
        mr.sequenciafaseob AS seq,
        COUNT(DISTINCT mr.sequencia_ajuste) AS qtd_ajustes_cor,
        MAX(mr.sequencia_ajuste) AS max_seq_ajuste
    FROM SGTPRD.movto_receita mr
    JOIN OBS_FILTRO fil ON fil.numero_ob = mr.numeroordem
    WHERE mr.sequencia_ajuste <> 0
    GROUP BY mr.numeroordem, mr.sequenciafaseob
),
DEFEITOS_QUALIDADE AS (
    -- Apontamentos formais de não conformidade e quilos rejeitados pela qualidade
    SELECT
        obq.numero_ob,
        obq.sequencia_fase,
        SUM(obq.quantidade_rejeitada) AS total_kg_rejeitado,
        SUM(obq.quantidade_a_reprogr) AS total_kg_reprogramar,
        MAX(TRIM(obq.motivo_acpnc)) AS motivo_acpnc,
        MAX(TRIM(obq.usuario_obnaoconform)) AS usuario_qualidade
    FROM SGTPRD.ob_qualidade obq
    JOIN OBS_FILTRO fil ON fil.numero_ob = obq.numero_ob
    GROUP BY obq.numero_ob, obq.sequencia_fase
),
REPROCESSOS_OB AS (
    -- Quilos de reprocesso e receitas de retingimento cadastradas
    SELECT
        obr.numero_ob,
        obr.sequencia_fase,
        SUM(obr.kilos) AS total_kg_reprocesso,
        COUNT(*) AS qtd_receitas_reprocesso
    FROM SGTPRD.ob_reprocesso obr
    JOIN OBS_FILTRO fil ON fil.numero_ob = obr.numero_ob
    GROUP BY obr.numero_ob, obr.sequencia_fase
),
PARADAS_CRUZADAS AS (
    -- Cruzamento híbrido de paradas de máquina por OB ou interceptação temporal na barca com filtro de período
    SELECT DISTINCT
        up.numeroup,
        up.numero_ob,
        SUBSTR(TRIM(mp.descricao), 1, 50) AS descr_parada
    FROM UP_BASE up
    JOIN PARAMETROS p ON 1=1
    JOIN SGTPRD.paradas_maquina pm ON pm.setor = 5
                                 AND pm.data_inicio >= p.dt_num_ini
                                 AND pm.data_inicio <= p.dt_num_fim
                                 AND (
                                     pm.numeroobe_insumo_pro = up.numero_ob
                                     OR (
                                         pm.numero_maquina = up.numero_maquina
                                         AND (TO_DATE(TO_CHAR(pm.data_inicio), 'YYYYMMDD') + (pm.hora_inicio / 1440)) <= up.dt_janela_fim
                                         AND (TO_DATE(TO_CHAR(pm.data_termino), 'YYYYMMDD') + (pm.hora_termino / 1440)) >= up.dt_janela_ini
                                     )
                                 )
    JOIN SGTPRD.motivos_paradas mp ON mp.codigo_parada = pm.codigo_parada AND mp.setor = pm.setor
),
PARADAS_AGRUPADAS AS (
    SELECT
        pc.numeroup,
        LISTAGG(pc.descr_parada, ' | ') WITHIN GROUP (ORDER BY pc.descr_parada) AS motivos_parada_apontados,
        COUNT(*) AS qtd_paradas_apontadas
    FROM PARADAS_CRUZADAS pc
    GROUP BY pc.numeroup
),
FASE_ANTERIOR AS (
    -- Identificação de gargalos da fase antecedente vinculada cirurgicamente a cada UP
    SELECT
        up.numeroup,
        ant.numero_ob,
        ant.sequencia AS seq_anterior,
        ant.codigo_fase AS fase_anterior,
        TRIM(ffl_ant.descricao_fase) AS descr_fase_anterior,
        ant.status AS status_fase_anterior,
        ROW_NUMBER() OVER (PARTITION BY up.numeroup ORDER BY ant.sequencia DESC) AS rn
    FROM UP_BASE up
    JOIN SGTPRD.ob_fases ant ON ant.numero_ob = up.numero_ob
                            AND ant.codigo_fase <> 40
                            AND ant.sequencia < up.seq
    LEFT JOIN SGTPRD.fases_fluxo ffl_ant ON ffl_ant.codigo_fase = ant.codigo_fase
),
ANALITICO_MENSAL_TINGIMENTO AS (
    SELECT
        p.competencia,
        up.numeroup,
        up.numero_ob,
        up.seq,
        up.numero_maquina,
        up.nome_maquina,
        dot.codpro_reduzido,
        dot.descr_artigo,
        dot.linha_produto,
        dot.nome_cliente,
        CASE
            WHEN dot.numero_pedido > 0 THEN TO_CHAR(dot.numero_pedido)
            ELSE 'ESTOQUE PROPRIO'
        END AS pedido_ou_estoque,
        dot.data_entrega_pedido,
        dot.codigo_cor,
        cpg.qtd_obs_na_partida,
        CASE
            WHEN cpg.qtd_obs_na_partida > 1 THEN 'PARTIDA COMPARTILHADA (' || cpg.qtd_obs_na_partida || ' OBs)'
            ELSE 'PARTIDA INDIVIDUAL'
        END AS tipo_partida,
        up.dttempoiniprogramado,
        up.dttempofinalprograma,
        up.dt_real_inicio,
        up.dt_real_fim,
        up.nrturnoini,
        up.nrturnofim,
        dot.operador_inicio,
        dot.operador_final,
        up.min_prev,
        -- Duração Real Efetiva calculada humanamente (inclui ordens rodando na máquina neste momento):
        CASE
            WHEN up.dt_real_inicio IS NOT NULL AND up.dt_real_fim IS NOT NULL THEN
                ROUND((up.dt_real_fim - up.dt_real_inicio) * 1440, 0)
            WHEN up.dt_real_inicio IS NOT NULL AND up.dt_real_fim IS NULL THEN
                ROUND((SYSDATE - up.dt_real_inicio) * 1440, 0)
            ELSE NULL
        END AS duracao_real_min,
        -- Diferença de duração em relação ao padrão:
        CASE
            WHEN up.dt_real_inicio IS NOT NULL AND up.dt_real_fim IS NOT NULL THEN
                ROUND((up.dt_real_fim - up.dt_real_inicio) * 1440, 0) - up.min_prev
            WHEN up.dt_real_inicio IS NOT NULL AND up.dt_real_fim IS NULL THEN
                ROUND((SYSDATE - up.dt_real_inicio) * 1440, 0) - up.min_prev
            ELSE NULL
        END AS dif_duracao_min,
        -- Desvio de Início em minutos:
        CASE
            WHEN up.dt_real_inicio IS NOT NULL THEN
                ROUND((up.dt_real_inicio - up.dttempoiniprogramado) * 1440, 0)
            WHEN up.dt_real_inicio IS NULL AND up.dttempoiniprogramado < SYSDATE THEN
                ROUND((SYSDATE - up.dttempoiniprogramado) * 1440, 0)
            ELSE 0
        END AS atraso_inicio_min,
        -- Desvio de Término em minutos:
        CASE
            WHEN up.dt_real_fim IS NOT NULL THEN
                ROUND((up.dt_real_fim - up.dttempofinalprograma) * 1440, 0)
            WHEN up.dt_real_fim IS NULL AND SYSDATE > up.dttempofinalprograma THEN
                ROUND((SYSDATE - up.dttempofinalprograma) * 1440, 0)
            ELSE 0
        END AS atraso_fim_min,
        NVL(ppu.min_par_proc, 0) AS min_par_proc,
        dot.kilos_ob,
        dot.kilos_produzidos,
        dot.total_pecas,
        dot.carga_maxima_maq,
        cpg.kilos_total_partida,
        -- Eficiência real de carga considerando o grupo compartilhado da barca:
        CASE
            WHEN dot.carga_maxima_maq > 0 THEN
                ROUND((cpg.kilos_total_partida / dot.carga_maxima_maq) * 100, 1)
            ELSE 100
        END AS perc_ocupacao_carga_real,
        dot.status_fase,
        -- ============================================================================
        -- 1. GESTÃO DE REPROCESSO (REQUISITO EXPLÍCITO)
        -- ============================================================================
        CASE
            WHEN dot.reprocesso_flag = 1 
              OR dot.destino_receita IN (2, 4) 
              OR up.seq > 30 
              OR NVL(rep.total_kg_reprocesso, 0) > 0 THEN 'SIM'
            ELSE 'NAO'
        END AS flg_reprocesso,
        CASE
            WHEN dot.destino_receita = 2 THEN 'FORA DE COR'
            WHEN dot.destino_receita = 4 THEN 'RECLASSIFICACAO / QUALIDADE'
            WHEN up.seq > 30 THEN 'SEGUNDA PASSAGEM (SEQ ' || up.seq || ')'
            WHEN NVL(rep.total_kg_reprocesso, 0) > 0 THEN 'RECEITA DE RETINGIMENTO'
            ELSE 'PRODUCAO NORMAL'
        END AS tipo_reprocesso,
        dot.descr_destino AS descr_destino_receita,
        NVL(rep.total_kg_reprocesso, 0) AS kilos_reprocesso_apontados,
        NVL(aj.qtd_ajustes_cor, 0) AS qtd_ajustes_cor,
        -- ============================================================================
        -- 2. GESTÃO DE DEFEITOS E NÃO CONFORMIDADES (REQUISITO EXPLÍCITO)
        -- ============================================================================
        CASE
            WHEN dot.descr_grupo_def IS NOT NULL 
              OR NVL(def.total_kg_rejeitado, 0) > 0 
              OR dot.red_ob_qualidade <> 0 THEN 'SIM'
            ELSE 'NAO'
        END AS flg_defeito,
        dot.grupo_defeito,
        dot.descr_grupo_def,
        dot.tipo_defeito,
        dot.descr_tipo_def,
        CASE
            WHEN dot.descr_grupo_def IS NOT NULL THEN dot.descr_grupo_def || ' - ' || dot.descr_tipo_def
            WHEN def.motivo_acpnc IS NOT NULL THEN 'N/C: ' || def.motivo_acpnc
            ELSE NULL
        END AS detalhe_defeito,
        NVL(def.total_kg_rejeitado, 0) AS kilos_rejeitados_qualidade,
        def.motivo_acpnc,
        def.usuario_qualidade,
        -- ============================================================================
        -- 3. PARADAS E FASE ANTERIOR
        -- ============================================================================
        prd.motivos_parada_apontados,
        NVL(prd.qtd_paradas_apontadas, 0) AS qtd_paradas_apontadas,
        fa.descr_fase_anterior,
        fa.status_fase_anterior,
        -- ============================================================================
        -- 4. CLASSIFICAÇÃO DE STATUS COM COERÊNCIA TEMPORAL HUMANA
        -- ============================================================================
        CASE
            WHEN up.dt_real_inicio IS NULL AND up.dttempoiniprogramado > SYSDATE THEN
                '1. PROGRAMADO FUTURO'
            WHEN up.dt_real_inicio IS NULL AND up.dttempoiniprogramado <= SYSDATE THEN
                '2. PENDENTE ATRASADO (NAO INICIADO)'
            WHEN up.dt_real_inicio IS NOT NULL AND up.dt_real_fim IS NULL THEN
                CASE
                    WHEN SYSDATE > up.dttempofinalprograma THEN '3. EM ANDAMENTO ATRASADO'
                    ELSE '4. EM ANDAMENTO NO PRAZO'
                END
            WHEN up.dt_real_fim IS NOT NULL OR dot.status_fase = 4 THEN
                CASE
                    WHEN (up.dt_real_fim - up.dttempofinalprograma) * 1440 > 15 THEN '5. CONCLUIDO COM ATRASO'
                    WHEN (up.dt_real_fim - up.dttempofinalprograma) * 1440 < -15 THEN '6. CONCLUIDO ADIANTADO'
                    ELSE '7. CONCLUIDO NO PRAZO'
                END
            ELSE 'OUTRO'
        END AS status_aderencia,
        -- ============================================================================
        -- 5. CATEGORIA MACRO DE DESVIO (PARA DASHBOARD E PAINÉIS DE BI)
        -- ============================================================================
        CASE
            WHEN up.dt_real_inicio IS NULL AND up.dttempoiniprogramado > SYSDATE THEN
                'PROGRAMACAO FUTURA'
            WHEN up.dt_real_inicio IS NULL AND up.dttempoiniprogramado <= SYSDATE THEN
                'PENDENTE DE INICIO NO CHAO DE FABRICA'
            WHEN dot.reprocesso_flag = 1 OR dot.destino_receita IN (2, 4) OR up.seq > 30 THEN
                'REPROCESSO / RETINGIMENTO'
            WHEN NVL(aj.qtd_ajustes_cor, 0) > 0 THEN
                'AJUSTE DE RECEITA / CORRECAO DE COR'
            WHEN prd.motivos_parada_apontados IS NOT NULL THEN
                'PARADA DE MAQUINA'
            WHEN NVL(ppu.min_par_proc, 0) > 0 THEN
                'PARADA DE PROCESSO INTERNA NA UP'
            WHEN dot.descr_grupo_def IS NOT NULL OR NVL(def.total_kg_rejeitado, 0) > 0 THEN
                'NAO CONFORMIDADE / QUALIDADE'
            WHEN fa.status_fase_anterior IS NOT NULL AND fa.status_fase_anterior <> 4 THEN
                'GARGALO FASE ANTERIOR'
            WHEN (up.dt_real_fim IS NOT NULL AND (up.dt_real_fim - up.dt_real_inicio) * 1440 - up.min_prev > 15)
              OR (up.dt_real_fim IS NULL AND up.dt_real_inicio IS NOT NULL AND (SYSDATE - up.dt_real_inicio) * 1440 - up.min_prev > 15) THEN
                'TEMPO DE PROCESSO EXCEDIDO'
            WHEN (up.dt_real_inicio - up.dttempoiniprogramado) * 1440 > 15 THEN
                'ATRASO NO INICIO DA CARGA'
            WHEN (dot.carga_maxima_maq > 0 AND (cpg.kilos_total_partida / dot.carga_maxima_maq) < 0.75) THEN
                'SUBCARGA NA BARCA/JET'
            WHEN up.dt_real_inicio IS NOT NULL AND up.dt_real_fim IS NULL THEN
                'EM ANDAMENTO NO PRAZO'
            ELSE
                'CONFORME / NO PRAZO OU ADIANTADO'
        END AS categoria_desvio,
        -- ============================================================================
        -- 6. CAUSA RAIZ DETALHADA / DIAGNÓSTICO CIRÚRGICO
        -- ============================================================================
        CASE
            WHEN up.dt_real_inicio IS NULL AND up.dttempoiniprogramado > SYSDATE THEN
                'ORDEM AGENDADA PARA EXECUCAO FUTURA NO PCP'
            WHEN up.dt_real_inicio IS NULL AND up.dttempoiniprogramado <= SYSDATE THEN
                CASE
                    WHEN prd.motivos_parada_apontados IS NOT NULL THEN
                        'PARADA DE MAQUINA ANTES DO INICIO: ' || prd.motivos_parada_apontados
                    WHEN fa.status_fase_anterior IS NOT NULL AND fa.status_fase_anterior <> 4 THEN
                        'GARGALO FASE ANTERIOR: ' || NVL(fa.descr_fase_anterior, 'PREPARACAO/CRU') || ' AINDA NAO CONCLUIDA'
                    WHEN (SYSDATE - up.dttempoiniprogramado) * 24 > 24 THEN
                        'PENDENCIA CRITICA DE SEQUENCIAMENTO (+ ' || ROUND((SYSDATE - up.dttempoiniprogramado) * 24, 0) || 'H SEM APONTAMENTO)'
                    ELSE 'CHAO DE FABRICA NAO INICIOU NO HORARIO PROGRAMADO (AGUARDANDO CARGA/OPERADOR)'
                END
            WHEN dot.reprocesso_flag = 1 OR dot.destino_receita IN (2, 4) OR up.seq > 30 THEN
                'REPROCESSO / RETINGIMENTO (' || NVL(dot.descr_destino, 'REPROCESSAMENTO') || ')'
            WHEN NVL(aj.qtd_ajustes_cor, 0) > 0 THEN
                'AJUSTE DE RECEITA / CORRECAO DE COR (' || aj.qtd_ajustes_cor || ' ADICAO(OES) DE QUIMICOS/CORANTE)'
            WHEN prd.motivos_parada_apontados IS NOT NULL THEN
                'PARADA DE MAQUINA NO TINGIMENTO: ' || prd.motivos_parada_apontados
            WHEN NVL(ppu.min_par_proc, 0) > 0 THEN
                'PARADA DE PROCESSO INTERNA NA UP (' || ppu.min_par_proc || ' MIN PARADOS)'
            WHEN dot.descr_grupo_def IS NOT NULL THEN
                'NAO CONFORMIDADE / QUALIDADE: ' || dot.descr_grupo_def || ' - ' || dot.descr_tipo_def
            WHEN fa.status_fase_anterior IS NOT NULL AND fa.status_fase_anterior <> 4 THEN
                'ATRASO LIBERACAO FASE ANTERIOR: ' || fa.descr_fase_anterior
            WHEN up.dt_real_fim IS NOT NULL AND (up.dt_real_fim - up.dt_real_inicio) * 1440 - up.min_prev > 15 THEN
                'TEMPO DE CICLO / PROCESSO EXCEDIDO (+ ' || ROUND((up.dt_real_fim - up.dt_real_inicio) * 1440 - up.min_prev, 0) || ' MIN ALEM DO PADRAO)'
            WHEN up.dt_real_fim IS NULL AND up.dt_real_inicio IS NOT NULL AND (SYSDATE - up.dt_real_inicio) * 1440 - up.min_prev > 15 THEN
                'EM ANDAMENTO ATRASADO: PROCESSO EXCEDEU PREVISAO (+ ' || ROUND((SYSDATE - up.dt_real_inicio) * 1440 - up.min_prev, 0) || ' MIN ALEM DO PADRAO)'
            WHEN (up.dt_real_inicio - up.dttempoiniprogramado) * 1440 > 15 THEN
                'ATRASO NO INICIO DA CARGA (+ ' || ROUND((up.dt_real_inicio - up.dttempoiniprogramado) * 1440, 0) || ' MIN)'
            WHEN (dot.carga_maxima_maq > 0 AND (cpg.kilos_total_partida / dot.carga_maxima_maq) < 0.75) THEN
                'SUBCARGA NA BARCA/JET (' || ROUND((cpg.kilos_total_partida / dot.carga_maxima_maq) * 100, 1) || '% DA CAPACIDADE)'
            WHEN up.dt_real_inicio IS NOT NULL AND up.dt_real_fim IS NULL THEN
                'EM ANDAMENTO: PROCESSO EXECUTANDO DENTRO DO TEMPO PADRAO'
            WHEN (up.dt_real_fim - up.dttempofinalprograma) * 1440 < -15 THEN
                'PROCESSO OTIMIZADO / CONCLUIDO ANTECIPADAMENTE (- ' || ROUND((up.dttempofinalprograma - up.dt_real_fim) * 1440, 0) || ' MIN)'
            ELSE 'CONFORME / REALIZADO DENTRO DA PREVISAO'
        END AS motivo_principal_desvio
    FROM UP_BASE up
    JOIN DADOS_OB_TINGIMENTO dot ON dot.numero_ob = up.numero_ob AND dot.sequencia = up.seq
    JOIN CARGA_PARTIDA_GRUPO cpg ON cpg.numero_ob = up.numero_ob AND cpg.sequencia = up.seq
    JOIN PARAMETROS p ON 1=1
    LEFT JOIN PARADAS_PROC_UP ppu ON ppu.numeroup = up.numeroup
    LEFT JOIN AJUSTES_RECEITA aj ON aj.numero_ob = up.numero_ob AND aj.seq = up.seq
    LEFT JOIN DEFEITOS_QUALIDADE def ON def.numero_ob = up.numero_ob AND def.sequencia_fase = up.seq
    LEFT JOIN REPROCESSOS_OB rep ON rep.numero_ob = up.numero_ob AND rep.sequencia_fase = up.seq
    LEFT JOIN PARADAS_AGRUPADAS prd ON prd.numeroup = up.numeroup
    LEFT JOIN FASE_ANTERIOR fa ON fa.numeroup = up.numeroup AND fa.rn = 1
)
-- ====================================================================================
-- PARTE 1: SAÍDA ANALÍTICA MENSAL COMPLETA (ORDENADA POR DATA PROGRAMADA):
-- ====================================================================================
SELECT
    at.competencia,
    at.numeroup,
    at.numero_ob,
    at.seq AS seq_fase,
    at.numero_maquina,
    at.nome_maquina,
    at.codpro_reduzido,
    at.descr_artigo,
    at.linha_produto,
    at.nome_cliente,
    at.pedido_ou_estoque,
    at.codigo_cor,
    at.tipo_partida,
    at.qtd_obs_na_partida,
    TO_CHAR(at.dttempoiniprogramado, 'DD/MM/YYYY HH24:MI') AS prev_inicio,
    TO_CHAR(at.dttempofinalprograma, 'DD/MM/YYYY HH24:MI') AS prev_fim,
    TO_CHAR(at.dt_real_inicio, 'DD/MM/YYYY HH24:MI') AS real_inicio,
    TO_CHAR(at.dt_real_fim, 'DD/MM/YYYY HH24:MI') AS real_fim,
    at.nrturnoini AS turno_inicio,
    at.nrturnofim AS turno_fim,
    at.operador_inicio,
    at.operador_final,
    at.min_prev AS duracao_prev_min,
    at.duracao_real_min,
    at.dif_duracao_min,
    at.atraso_inicio_min,
    at.atraso_fim_min,
    at.min_par_proc,
    at.kilos_ob AS kilos_programados_ob,
    at.kilos_produzidos AS kilos_produzidos_ob,
    at.total_pecas,
    at.kilos_total_partida,
    at.carga_maxima_maq,
    at.perc_ocupacao_carga_real,
    -- Bloco de Reprocesso:
    at.flg_reprocesso,
    at.tipo_reprocesso,
    at.descr_destino_receita,
    at.kilos_reprocesso_apontados,
    at.qtd_ajustes_cor,
    -- Bloco de Defeitos e Qualidade:
    at.flg_defeito,
    at.detalhe_defeito,
    at.kilos_rejeitados_qualidade,
    at.motivo_acpnc,
    at.usuario_qualidade,
    -- Bloco de Status e Causas Raiz:
    at.status_aderencia,
    at.categoria_desvio,
    at.motivo_principal_desvio,
    at.motivos_parada_apontados AS detalhe_paradas_maquina,
    at.descr_fase_anterior AS fase_precedente
FROM ANALITICO_MENSAL_TINGIMENTO at
ORDER BY at.dttempoiniprogramado DESC

-- ====================================================================================
-- NOTA: O PAINEL EXECUTIVO MENSAL / DASHBOARD CONSOLIDADO DE KPIS (PARTE 2)
-- Foi concluído e estruturado em arquivo dedicado pronto para execução e BI:
-- -> painel_executivo_kpis_tingimento_mensal.sql
-- ====================================================================================
