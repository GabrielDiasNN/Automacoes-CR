/* =============================================================================
OBJETIVO: Acompanhamento de Fechamento do Mês no Beneficiamento - Monitoramento de OBs em Aberto por Grupo de Programação, Estágio Produtivo, Macro-Setor, Origens, Avanço de Fases, Pesagem Real e Risco Operacional
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO: bnf_fechamento_mes_obs_em_aberto_com_origens.sql
TIPO: SELECT (Consulta Somente Leitura)
PARÂMETROS / BINDS: Nenhum (janela dinâmica: todas as entregas até o fim do mês atual via c.data_entrega < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1))
TABELAS PRINCIPAIS:
  - SGTPRD.OB
  - SGTPRD.OB_PRODUTO
  - SGTPRD.OB_FASES
  - SGTPRD.FASES_FLUXO
  - SGTPRD.GRUPO_FASES
  - SGTPRD.GRUPO_PRODUTO
  - SGTPRD.COR
  - SGTPRD.ENGEITEMESTOCOR
  - SGTPRD.PEDPRODUCAOOB
  - SGTPRD.OFORDENS
  - SGTPRD.OFPEDIDO
  - SGTPRD.ITENSPEDIDOQTDES
  - SGTPRD.ITENSPEDIDOGRADE
  - SGTPRD.PEDIDOCOMERCIAL
  - SGTPRD.ITENSPEDIDOCOMERCIAL
  - SGTPRD.PESSOASFJ
  - SGTPRD.GERAPECAORIGEMOB
  - SGTPRD.GERAPECADESTINOOB
  - SGTPRD.GERAPECASPRODUTO
  - SGTPRD.ITENS_ESTOQUE
  - SGTPRD.OB_BLOQUEIO
  - SGTPRD.OB_REPROCESSO
MELHORIAS TÉCNICAS E OPERACIONAIS IMPLEMENTADAS NA REVISÃO:
  1. Estabilidade e Desempenho (Eliminação de ORA-00028 / ORA-03113):
     - Remoção dos hints prejudiciais de MATERIALIZE que forçavam materializações temporárias em temp table global, provocando esgotamento de recursos e cancelamento de sessão no Oracle.
     - Reestruturação da resolução de pedidos comerciais: separação limpa entre PEDIDO_DIRETO e PEDIDO_MAE (usado apenas pelas ordens filhas sem pedido direto), substituindo árvores de joins com UNION ALL por caminhos diretos totalmente indexados via Nested Loops.
  2. Integridade e Atomicidade de Dados (Fim da agregação Frankenstein):
     - Eliminação de agregações desemparelhadas MIN(pedido), MIN(cliente), MIN(data_entrega).
     - Implementação de particionamento analítico determinístico (ROW_NUMBER) que seleciona a tupla íntegra (pedido, cliente, prazo, bloqueio) do mesmo registro contratual.
  3. Determinação Precisa da Fase Atual:
     - Ranqueamento operacional calibrado: prioriza estritamente a fase física ativa em execução (status 3), seguida por fases pesadas (status 2), emitidas (status 1) e programadas (status 0) por menor sequência. Se todas confirmadas (status 4), assume a última confirmada.
     - Unificação da varredura de SGTPRD.OB_FASES em uma única passada analítica sobre a base ativa, eliminando varreduras redundantes em mais de 1,3 milhão de linhas.
  4. Indicadores de Fechamento de Mês e PCP Calibrados:
     - Correção da inversão de hierarquia no STATUS_FECHAMENTO_MES: o macro-setor (Expedição/CQ >= 50) agora tem precedência sobre o percentual bruto de fases, evitando que ordens na reta final sejam rotuladas erroneamente como "INÍCIO".
     - Adição do indicador ESTAGIO_PRODUTIVO padronizado (Montagem/Preparação, Tinturaria, Terceiros, Acabamento/Rama/Secagem, Controle de Qualidade, Expedição).
     - Inclusão do indicador PERC_AVANCO_SEQ (% da sequência atual no fluxo total) complementando PERC_AVANCO_FASES (% de fases concluídas).
     - Situação de prazo padronizada categoricamente (ATRASADO, ENTREGA HOJE, CRÍTICO, NO PRAZO, SEM PREVISAO) para facilidade de filtros no Excel e Power BI, acompanhada de DIAS_ATE_ENTREGA e DIAS_ATRASO numéricos.
     - Nomenclatura transparente: DIAS_SEM_MOVIMENTACAO (com alias dias_parado_na_fase para retrocompatibilidade) expressando o real intervalo sem apontamento operacional.
============================================================================= */

WITH
    -- 1. Driving CTE: Ordens ativas em chão de fábrica (não encerradas)
    OB_BASE AS (
        SELECT
            o.numero_ob,
            o.status AS status_ob_cod,
            CASE o.status
                WHEN 0 THEN 'Encerrada'
                WHEN 1 THEN 'Emitida'
                WHEN 2 THEN 'Pré OB'
                WHEN 3 THEN 'Programada'
                WHEN 4 THEN 'Bloqueada'
                WHEN 5 THEN 'Interditada Kanban'
                ELSE 'Status ' || o.status
            END AS status_ob,
            o.tipo_ordem AS tipo_ordem_cod,
            CASE o.tipo_ordem
                WHEN 0 THEN 'Produção'
                WHEN 1 THEN 'Sem Programação'
                WHEN 2 THEN 'Receita Simples'
                WHEN 3 THEN 'Receita Laboratório'
                WHEN 4 THEN 'Químico Composto'
                WHEN 5 THEN 'Receita Estamparia'
                WHEN 6 THEN 'Ordem de Reprocesso'
                WHEN 7 THEN 'Limpeza Máquina'
                WHEN 8 THEN 'Produção Lavanderia'
                WHEN 9 THEN 'Reprocesso Lavanderia'
                ELSE 'Tipo ' || o.tipo_ordem
            END AS descr_tipo_ordem,
            o.numero_grupo_program,
            o.codigo_reduzido,
            o.codigo_reduzido_cru,
            o.dtentrpedido,
            o.dtiniproducao,
            o.dt_programacao,
            o.dtemissaordem,
            ROUND(SYSDATE - COALESCE(o.dtiniproducao, o.dtemissaordem, o.dt_programacao), 1) AS dias_em_processo
        FROM sgtprd.ob o
        WHERE o.status <> 0
          AND o.dtencerordem IS NULL
    ),

    -- 2. Grupo de Programação Têxtil (Loteamento / Família de PCP)
    GRUPO_PROG AS (
        SELECT
            grp.numero_grupo_program,
            TRIM(grp.codigo_grupo_program) AS cod_grupo_program,
            TRIM(grp.descricao) AS descr_grupo_program
        FROM sgtprd.grupo_produto grp
        JOIN (SELECT DISTINCT numero_grupo_program FROM OB_BASE WHERE numero_grupo_program IS NOT NULL) obg
          ON obg.numero_grupo_program = grp.numero_grupo_program
    ),

    -- 3. Consolidação de Fases em Varredura Única (Fase Atual Operacional, Macro-Setor, Avanço e Posição)
    FASES_RANQUEADAS AS (
        SELECT
            obf.numero_ob,
            obf.codigo_fase,
            obf.sequencia,
            obf.status AS status_fase_cod,
            TRIM(ffl.descricao_fase) AS descr_fase,
            CASE
                WHEN obf.status = 4 THEN 'Confirmada'
                WHEN obf.status = 0 THEN 'Programada'
                WHEN obf.status = 1 THEN 'Emitida'
                WHEN obf.status = 2 THEN 'Pesada'
                WHEN obf.status = 3 THEN 'Em Execução'
                WHEN obf.status = 5 THEN 'Cancelada'
                WHEN obf.status = 6 THEN 'Consumo Estamparia'
                ELSE 'Status ' || obf.status
            END AS status_fase,
            TRIM(obf.numero_maquina) AS numero_maquina,
            TRIM(gf.descricao) AS macro_setor,
            NVL(gf.setor_sequencia, 99) AS macro_setor_seq,
            -- Métricas consolidadas da ordem técnica
            COUNT(*) OVER (PARTITION BY obf.numero_ob) AS total_fases,
            SUM(CASE WHEN obf.status = 4 THEN 1 ELSE 0 END) OVER (PARTITION BY obf.numero_ob) AS fases_concluidas,
            MAX(CASE WHEN obf.tempo_final_confirma > 0 THEN DATE '1996-01-01' + obf.tempo_final_confirma / 1440 END) 
                OVER (PARTITION BY obf.numero_ob) AS dt_ult_confirmacao,
            MAX(TRIM(obf.codigo_placa)) OVER (PARTITION BY obf.numero_ob) AS placa_kanban,
            MAX(obf.sequencia) OVER (PARTITION BY obf.numero_ob) AS max_sequencia_ob,
            MAX(CASE WHEN obf.codigo_fase = 40 THEN TRIM(obf.codigo_cor_desenho) END)
                OVER (PARTITION BY obf.numero_ob) AS cd_cor_receita,
            -- Ranqueamento determinístico operacional: prioriza fase física em execução > pesada > emitida > programada
            ROW_NUMBER() OVER (
                PARTITION BY obf.numero_ob
                ORDER BY
                    CASE 
                        WHEN obf.status = 3 THEN 1 -- Em Execução (fase ativa prioritária)
                        WHEN obf.status = 2 THEN 2 -- Pesada (lote já pesado)
                        WHEN obf.status = 1 THEN 3 -- Emitida
                        WHEN obf.status = 0 THEN 4 -- Programada
                        WHEN obf.status = 4 THEN 5 -- Confirmada
                        ELSE 6
                    END ASC,
                    CASE WHEN obf.status <> 4 THEN obf.sequencia END ASC NULLS LAST,
                    obf.sequencia DESC
            ) AS rn_fase_atual
        FROM sgtprd.ob_fases obf
        JOIN OB_BASE b ON b.numero_ob = obf.numero_ob
        JOIN sgtprd.fases_fluxo ffl ON ffl.codigo_fase = obf.codigo_fase
        LEFT JOIN sgtprd.grupo_fases gf ON gf.codigo = ffl.codigo_grupo
        WHERE obf.status <> 5
    ),

    FASE_CONSOLIDADA AS (
        SELECT
            numero_ob,
            codigo_fase AS fase_atual_cod,
            descr_fase AS fase_atual_nome,
            status_fase,
            numero_maquina,
            macro_setor,
            macro_setor_seq,
            sequencia AS sequencia_fase_atual,
            max_sequencia_ob,
            total_fases,
            fases_concluidas,
            ROUND(fases_concluidas * 100.0 / NULLIF(total_fases, 0), 1) AS perc_avanco_fases,
            ROUND(sequencia * 100.0 / NULLIF(max_sequencia_ob, 0), 1) AS perc_avanco_seq,
            dt_ult_confirmacao,
            placa_kanban,
            cd_cor_receita
        FROM FASES_RANQUEADAS
        WHERE rn_fase_atual = 1
    ),

    -- 4. Peso Real Físico das Peças Montadas em Balança
    PESO_REAL AS (
        SELECT
            ori.numero_ob,
            COUNT(ori.idpecasproduto) AS pecas_fisicas_montadas,
            ROUND(SUM(gpp.qtliquida), 2) AS kilos_reais_montados
        FROM sgtprd.gerapecaorigemob ori
        JOIN sgtprd.gerapecasproduto gpp ON gpp.idpecasproduto = ori.idpecasproduto
        JOIN OB_BASE b ON b.numero_ob = ori.numero_ob
        GROUP BY ori.numero_ob
    ),

    -- 5. Cadastro do Artigo e Cor Comercial
    PROD_INFO AS (
        SELECT
            b.numero_ob,
            MAX(obp.kilos_programados) AS kilos_programados,
            MAX(obp.total_pecas) AS pecas_programadas,
            TRIM(MAX(ite.codigo_alternativo)) AS codigo_alternativo,
            TRIM(MAX(ite.descricao)) AS descricao_artigo,
            TRIM(MAX(cor.descricao)) AS nome_cor
        FROM OB_BASE b
        LEFT JOIN sgtprd.ob_produto obp ON obp.numero_ob = b.numero_ob
        LEFT JOIN sgtprd.itens_estoque ite ON ite.codigo_reduzido = b.codigo_reduzido
        LEFT JOIN sgtprd.engeitemestocor eic ON eic.cdreduzido = b.codigo_reduzido
        LEFT JOIN sgtprd.cor cor ON cor.codigo_cor = eic.cdcor
        GROUP BY b.numero_ob
    ),

    -- 6. Bloqueios de Chão de Fábrica Ativos (Qualidade / Processo)
    BLOQUEIOS_OB AS (
        SELECT
            blq.numero_ob,
            COUNT(*) AS qtd_bloqueios,
            MAX(TRIM(blq.observacao)) KEEP (DENSE_RANK LAST ORDER BY blq.data_bloqueio NULLS FIRST, blq.id NULLS FIRST) AS motivo_bloqueio_ob
        FROM sgtprd.ob_bloqueio blq
        JOIN OB_BASE b ON b.numero_ob = blq.numero_ob
        WHERE blq.liberado = 0
        GROUP BY blq.numero_ob
    ),

    -- 7. Ocorrências de Reprocesso (Tingimento Químico vs Acabamento Mecânico)
    REPROCESSOS_OB AS (
        SELECT
            rep.numero_ob,
            COUNT(CASE WHEN rep.numero_maquina LIKE '%MQ%' THEN 1 END) AS qtd_reproc_tingimento,
            COUNT(CASE WHEN rep.numero_maquina NOT LIKE '%MQ%' OR rep.numero_maquina IS NULL THEN 1 END) AS qtd_reproc_acabamento,
            COUNT(*) AS qtd_reprocessos_total
        FROM sgtprd.ob_reprocesso rep
        JOIN OB_BASE b ON b.numero_ob = rep.numero_ob
        GROUP BY rep.numero_ob
    ),

    -- 8. Linhagem: Identificação de Peças Montadas a Partir de OB Mãe
    ORIGEM_PECAS AS (
        SELECT
            ori.numero_ob AS ob_filha,
            dest.numero_ob AS ob_mae,
            COUNT(DISTINCT ori.idpecasproduto) AS qtd_pecas
        FROM sgtprd.gerapecaorigemob ori
        JOIN sgtprd.gerapecadestinoob dest ON dest.idpecasproduto = ori.idpecasproduto
        JOIN OB_BASE b ON b.numero_ob = ori.numero_ob
        WHERE dest.numero_ob <> ori.numero_ob
        GROUP BY ori.numero_ob, dest.numero_ob
    ),

    ORIGEM_AGRUPADA AS (
        SELECT
            op.ob_filha,
            LISTAGG(op.ob_mae, ', ' ON OVERFLOW TRUNCATE '...') WITHIN GROUP (ORDER BY op.ob_mae) AS obs_origem,
            MIN(op.ob_mae) AS ob_mae_principal
        FROM ORIGEM_PECAS op
        GROUP BY op.ob_filha
    ),

    -- 9. Pedidos Comerciais Diretos da OB (Atômico, Sem Mistura de Agregações)
    PEDIDO_DIRETO AS (
        SELECT
            b.numero_ob,
            ipg.pedido,
            TRIM(ped.pedidocliente) AS pedidocliente,
            TRIM(cli.nome) AS cliente_nome,
            COALESCE(
                ipc.dataexpedirem,
                TO_DATE(TO_CHAR(ipc.expedirem) DEFAULT NULL ON CONVERSION ERROR, 'YYYYMMDD')
            ) AS data_entrega,
            NVL(ped.bloqueiofaturamento, 0) AS bloqueio_faturamento,
            TRIM(ped.descbloqfaturamento) AS motivo_bloq_fat,
            ROW_NUMBER() OVER (
                PARTITION BY b.numero_ob
                ORDER BY
                    COALESCE(ipc.dataexpedirem, TO_DATE(TO_CHAR(ipc.expedirem) DEFAULT NULL ON CONVERSION ERROR, 'YYYYMMDD')) ASC NULLS LAST,
                    ipg.pedido ASC
            ) AS rn
        FROM OB_BASE b
        JOIN sgtprd.pedproducaoob ppob ON ppob.numeroob = b.numero_ob
        JOIN sgtprd.ofordens ofo ON ofo.numeropedproducao = ppob.numero AND ofo.reduzido = ppob.reduzido
        JOIN sgtprd.ofpedido ofp ON ofp.numeroof = ofo.numeroof AND ofp.nivel = ofo.nivel AND ofp.reduzido = ofo.reduzido
        JOIN sgtprd.itenspedidoqtdes ipq ON ipq.iditenspedidoqtdes = ofp.iditenspedidoqtdes
        JOIN sgtprd.itenspedidograde ipg ON ipg.iditenspedidograde = ipq.iditempedgrade
        JOIN sgtprd.pedidocomercial ped ON ped.pedido = ipg.pedido
        LEFT JOIN sgtprd.itenspedidocomercial ipc ON ipc.pedido = ipg.pedido AND ipc.itempedido = ipg.itempedido
        LEFT JOIN sgtprd.pessoasfj cli ON cli.idpessoafj = ped.idfilialresponsavel
    ),

    -- 10. Pedidos Herdados da OB Mãe (Somente para OBs Filhas Sem Pedido Direto)
    ORIGEM_SEM_PEDIDO AS (
        SELECT op.ob_filha, MIN(op.ob_mae) AS ob_mae
        FROM ORIGEM_PECAS op
        LEFT JOIN PEDIDO_DIRETO pd ON pd.numero_ob = op.ob_filha AND pd.rn = 1
        WHERE pd.pedido IS NULL
        GROUP BY op.ob_filha
    ),

    PEDIDO_MAE AS (
        SELECT
            osp.ob_filha AS numero_ob,
            ipg.pedido,
            TRIM(ped.pedidocliente) AS pedidocliente,
            TRIM(cli.nome) AS cliente_nome,
            COALESCE(
                ipc.dataexpedirem,
                TO_DATE(TO_CHAR(ipc.expedirem) DEFAULT NULL ON CONVERSION ERROR, 'YYYYMMDD')
            ) AS data_entrega,
            NVL(ped.bloqueiofaturamento, 0) AS bloqueio_faturamento,
            TRIM(ped.descbloqfaturamento) AS motivo_bloq_fat,
            ROW_NUMBER() OVER (
                PARTITION BY osp.ob_filha
                ORDER BY
                    COALESCE(ipc.dataexpedirem, TO_DATE(TO_CHAR(ipc.expedirem) DEFAULT NULL ON CONVERSION ERROR, 'YYYYMMDD')) ASC NULLS LAST,
                    ipg.pedido ASC
            ) AS rn
        FROM ORIGEM_SEM_PEDIDO osp
        JOIN sgtprd.pedproducaoob ppob ON ppob.numeroob = osp.ob_mae
        JOIN sgtprd.ofordens ofo ON ofo.numeropedproducao = ppob.numero AND ofo.reduzido = ppob.reduzido
        JOIN sgtprd.ofpedido ofp ON ofp.numeroof = ofo.numeroof AND ofp.nivel = ofo.nivel AND ofp.reduzido = ofo.reduzido
        JOIN sgtprd.itenspedidoqtdes ipq ON ipq.iditenspedidoqtdes = ofp.iditenspedidoqtdes
        JOIN sgtprd.itenspedidograde ipg ON ipg.iditenspedidograde = ipq.iditempedgrade
        JOIN sgtprd.pedidocomercial ped ON ped.pedido = ipg.pedido
        LEFT JOIN sgtprd.itenspedidocomercial ipc ON ipc.pedido = ipg.pedido AND ipc.itempedido = ipg.itempedido
        LEFT JOIN sgtprd.pessoasfj cli ON cli.idpessoafj = ped.idfilialresponsavel
    ),

    -- 11. Consolidação Operacional Unificada (1 Linha por OB)
    CONSOLIDADO AS (
        SELECT
            b.numero_ob,
            b.status_ob,
            b.status_ob_cod,
            b.descr_tipo_ordem,
            b.tipo_ordem_cod,
            b.numero_grupo_program,
            gp.cod_grupo_program,
            gp.descr_grupo_program,
            b.codigo_reduzido,
            pi.codigo_alternativo,
            b.codigo_reduzido_cru,
            b.dtiniproducao,
            b.dt_programacao,
            b.dtemissaordem,
            b.dias_em_processo,
            fc.fase_atual_cod,
            fc.fase_atual_nome,
            CASE
                WHEN fc.status_fase IS NOT NULL THEN fc.status_fase
                ELSE 'Aguardando Início/Encerramento'
            END AS status_fase,
            fc.macro_setor,
            fc.macro_setor_seq,
            fc.numero_maquina,
            fc.placa_kanban,
            fc.cd_cor_receita,
            fc.total_fases,
            fc.fases_concluidas,
            fc.perc_avanco_fases,
            fc.perc_avanco_seq,
            fc.dt_ult_confirmacao,
            ROUND(
                CASE
                    WHEN SYSDATE - COALESCE(fc.dt_ult_confirmacao, b.dtiniproducao, b.dt_programacao, b.dtemissaordem) < 0 THEN 0
                    ELSE SYSDATE - COALESCE(fc.dt_ult_confirmacao, b.dtiniproducao, b.dt_programacao, b.dtemissaordem)
                END, 1
            ) AS dias_sem_movimentacao,
            pi.descricao_artigo,
            pi.nome_cor,
            ROUND(NVL(pi.kilos_programados, 0), 2) AS kilos_programados,
            pr.kilos_reais_montados,
            ROUND(COALESCE(pr.kilos_reais_montados, pi.kilos_programados, 0), 2) AS kilos_efetivos,
            ROUND(NVL(pr.kilos_reais_montados, 0) - NVL(pi.kilos_programados, 0), 2) AS variacao_peso_kg,
            ROUND(
                (NVL(pr.kilos_reais_montados, 0) - NVL(pi.kilos_programados, 0)) * 100.0 / NULLIF(pi.kilos_programados, 0),
                1
            ) AS perc_variacao_peso,
            pi.pecas_programadas,
            NVL(pr.pecas_fisicas_montadas, 0) AS pecas_fisicas_montadas,
            COALESCE(NULLIF(pr.pecas_fisicas_montadas, 0), pi.pecas_programadas, 0) AS total_pecas,
            CASE
                WHEN pd.pedido IS NOT NULL THEN 'DIRETO'
                WHEN pm.pedido IS NOT NULL THEN 'ORIGEM'
                ELSE 'SEM PEDIDO'
            END AS tipo_vinculo,
            oa.obs_origem,
            COALESCE(pd.pedido, pm.pedido) AS pedido_comercial,
            COALESCE(pd.pedidocliente, pm.pedidocliente) AS pedido_cliente,
            COALESCE(pd.cliente_nome, pm.cliente_nome) AS cliente,
            COALESCE(pd.data_entrega, pm.data_entrega, b.dtentrpedido) AS data_entrega,
            NVL(COALESCE(pd.bloqueio_faturamento, pm.bloqueio_faturamento), 0) AS bloqueio_faturamento,
            COALESCE(pd.motivo_bloq_fat, pm.motivo_bloq_fat) AS motivo_bloq_fat,
            NVL(bo.qtd_bloqueios, 0) AS qtd_bloqueios,
            bo.motivo_bloqueio_ob,
            NVL(ro.qtd_reproc_tingimento, 0) AS qtd_reproc_tingimento,
            NVL(ro.qtd_reproc_acabamento, 0) AS qtd_reproc_acabamento,
            NVL(ro.qtd_reprocessos_total, 0) AS qtd_reprocessos_total
        FROM OB_BASE b
        LEFT JOIN GRUPO_PROG gp ON gp.numero_grupo_program = b.numero_grupo_program
        LEFT JOIN FASE_CONSOLIDADA fc ON fc.numero_ob = b.numero_ob
        LEFT JOIN PESO_REAL pr ON pr.numero_ob = b.numero_ob
        LEFT JOIN PROD_INFO pi ON pi.numero_ob = b.numero_ob
        LEFT JOIN BLOQUEIOS_OB bo ON bo.numero_ob = b.numero_ob
        LEFT JOIN REPROCESSOS_OB ro ON ro.numero_ob = b.numero_ob
        LEFT JOIN ORIGEM_AGRUPADA oa ON oa.ob_filha = b.numero_ob
        LEFT JOIN PEDIDO_DIRETO pd ON pd.numero_ob = b.numero_ob AND pd.rn = 1
        LEFT JOIN PEDIDO_MAE pm ON pm.numero_ob = b.numero_ob AND pm.rn = 1
    )

SELECT
    c.numero_ob,
    c.status_ob,
    c.descr_tipo_ordem AS tipo_ordem,
    c.numero_grupo_program,
    c.descr_grupo_program AS grupo_programacao,
    c.tipo_vinculo,
    c.obs_origem,
    c.pedido_comercial,
    c.pedido_cliente,
    c.cliente,
    c.data_entrega,

    -- Situação Categórica de Prazo (Padronizada para Filtros no Excel e Power BI)
    CASE
        WHEN c.data_entrega IS NULL THEN 'SEM PREVISAO'
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE) THEN 'ATRASADO'
        WHEN TRUNC(c.data_entrega) = TRUNC(SYSDATE) THEN 'ENTREGA HOJE'
        WHEN TRUNC(c.data_entrega) - TRUNC(SYSDATE) <= 3 THEN 'CRÍTICO'
        ELSE 'NO PRAZO'
    END AS situacao_prazo,

    -- Métricas Numéricas de Prazo
    TRUNC(c.data_entrega) - TRUNC(SYSDATE) AS dias_ate_entrega,
    CASE 
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE) THEN TRUNC(SYSDATE) - TRUNC(c.data_entrega) 
        ELSE 0 
    END AS dias_atraso,

    -- Indicador Estratégico de Fechamento de Mês (Hierarquia Operacional Corrigida)
    CASE
        WHEN c.bloqueio_faturamento <> 0
             THEN '1 - BLOQUEIO FATURAMENTO'
        WHEN c.qtd_bloqueios > 0
             THEN '2 - BLOQUEIO CHÃO FÁBRICA'
        WHEN c.tipo_ordem_cod = 6 OR c.qtd_reproc_tingimento > 0
             THEN '3 - REPROCESSO EM CURSO'
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE) AND c.macro_setor_seq >= 50
             THEN '4 - ATRASO EXPEDIÇÃO/CQ'
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE) AND (c.macro_setor_seq <= 20 OR NVL(c.perc_avanco_seq, 0) < 50)
             THEN '5 - ATRASADO CRÍTICO (INÍCIO)'
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE)
             THEN '6 - ATRASADO EM PROCESSO'
        WHEN c.dias_sem_movimentacao >= 3
             THEN '7 - PARADO NA FASE (>3 DIAS)'
        WHEN c.macro_setor_seq >= 50
             THEN '8 - RETA FINAL NO PRAZO'
        ELSE '9 - FLUXO NORMAL'
    END AS status_fechamento_mes,

    -- Indicador de Potencial de Faturamento no Mês Atual
    CASE
        WHEN c.bloqueio_faturamento <> 0 THEN 'BLOQUEADO COMERCIAL'
        WHEN c.qtd_bloqueios > 0 THEN 'BLOQUEADO QUALIDADE'
        WHEN c.tipo_ordem_cod = 6 OR c.qtd_reproc_tingimento > 0 THEN 'BAIXO (EM REPROCESSO)'
        WHEN c.macro_setor_seq >= 50 THEN 'ALTO (NA EXPEDIÇÃO/CQ)'
        WHEN c.macro_setor_seq = 40 OR NVL(c.perc_avanco_seq, 0) >= 60 THEN 'MÉDIO (EM ACABAMENTO)'
        WHEN c.macro_setor_seq <= 20 OR NVL(c.perc_avanco_seq, 0) < 50 THEN 'BAIXO (FASE INICIAL)'
        ELSE 'REGULAR'
    END AS potencial_faturamento_mes,

    -- Estágio Produtivo Padronizado para PCP
    CASE
        WHEN c.macro_setor_seq <= 10 THEN 'MONTAGEM / PREPARAÇÃO'
        WHEN c.macro_setor_seq = 20 THEN 'TINTURARIA'
        WHEN c.macro_setor_seq = 30 THEN 'TERCEIROS'
        WHEN c.macro_setor_seq IN (40, 45) THEN 'ACABAMENTO / RAMA / SECAGEM'
        WHEN c.macro_setor_seq = 50 THEN 'CONTROLE DE QUALIDADE'
        WHEN c.macro_setor_seq >= 60 THEN 'EXPEDIÇÃO'
        ELSE 'NÃO IDENTIFICADO'
    END AS estagio_produtivo,

    c.macro_setor,
    c.macro_setor_seq,
    c.fase_atual_cod,
    c.fase_atual_nome,
    c.status_fase,
    c.numero_maquina,
    c.placa_kanban,
    c.dias_sem_movimentacao AS dias_parado_na_fase,
    c.dias_sem_movimentacao,
    c.dias_em_processo AS dias_processo_total,
    c.total_fases,
    c.fases_concluidas,
    c.perc_avanco_fases AS perc_avanco_fluxo,
    c.perc_avanco_seq,
    c.codigo_reduzido,
    c.codigo_alternativo AS alternativo,
    c.descricao_artigo,
    c.nome_cor,
    c.codigo_reduzido_cru,
    c.cd_cor_receita,
    c.kilos_efetivos,
    c.kilos_reais_montados,
    c.kilos_programados,
    c.variacao_peso_kg,
    c.perc_variacao_peso,
    c.total_pecas,
    c.pecas_fisicas_montadas,
    c.pecas_programadas,
    CASE
        WHEN c.bloqueio_faturamento <> 0
             THEN 'BLOQUEIO FAT: ' || NVL(c.motivo_bloq_fat, 'ATIVO')
        ELSE 'LIBERADO'
    END AS bloqueio_comercial,
    CASE
        WHEN c.qtd_bloqueios > 0
             THEN 'BLOQUEADA: ' || NVL(c.motivo_bloqueio_ob, 'QUALIDADE/PROCESSO')
        ELSE 'NORMAL'
    END AS bloqueio_ob_chao_fabrica,
    CASE
        WHEN c.tipo_ordem_cod = 6 THEN 'SIM (ORDEM REPROCESSO GERAL)'
        WHEN c.qtd_reproc_tingimento > 0 AND c.qtd_reproc_acabamento > 0
             THEN 'SIM (TINGIMENTO ' || TO_CHAR(c.qtd_reproc_tingimento) || 'x + ACABAMENTO ' || TO_CHAR(c.qtd_reproc_acabamento) || 'x)'
        WHEN c.qtd_reproc_tingimento > 0
             THEN 'SIM (TINGIMENTO ' || TO_CHAR(c.qtd_reproc_tingimento) || 'x)'
        WHEN c.qtd_reproc_acabamento > 0
             THEN 'SIM (RETRABALHO ACABAMENTO ' || TO_CHAR(c.qtd_reproc_acabamento) || 'x)'
        ELSE 'NÃO'
    END AS reprocesso_tingimento,
    CASE
        WHEN c.bloqueio_faturamento <> 0
             THEN 'BLOQUEIO COMERCIAL: ' || NVL(c.motivo_bloq_fat, 'ATIVO')
        WHEN c.qtd_bloqueios > 0
             THEN 'BLOQUEIO INDUSTRIAL: ' || NVL(c.motivo_bloqueio_ob, 'QUALIDADE/PROCESSO')
        WHEN c.tipo_ordem_cod = 6 OR c.qtd_reproc_tingimento > 0
             THEN 'REPROCESSO TINGIMENTO'
        WHEN c.qtd_reproc_acabamento > 0
             THEN 'RETRABALHO ACABAMENTO'
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE) AND c.macro_setor_seq >= 50
             THEN 'ATRASO EXPEDICAO'
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE)
             THEN 'ATRASO PRODUCAO'
        WHEN c.dias_sem_movimentacao >= 3
             THEN 'FLUXO ESTAGNADO (>3 DIAS)'
        ELSE 'NENHUMA OCORRENCIA (NORMAL)'
    END AS ocorrencia_principal,
    CASE
        WHEN c.bloqueio_faturamento <> 0
          OR c.qtd_bloqueios > 0
          OR (TRUNC(c.data_entrega) < TRUNC(SYSDATE) AND (c.macro_setor_seq <= 20 OR NVL(c.perc_avanco_seq, 0) < 50))
          OR (TRUNC(SYSDATE) - TRUNC(c.data_entrega) > 3)
             THEN 'ALTA'
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE)
          OR c.tipo_ordem_cod = 6
          OR c.qtd_reproc_tingimento > 0
          OR c.dias_sem_movimentacao >= 3
             THEN 'MEDIA'
        ELSE 'BAIXA'
    END AS gravidade_ocorrencia,
    c.dtiniproducao AS data_inicio_producao,
    c.dt_programacao AS data_programacao
FROM CONSOLIDADO c
WHERE c.data_entrega < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1)
ORDER BY
    CASE
        WHEN c.bloqueio_faturamento <> 0 THEN 1
        WHEN c.qtd_bloqueios > 0 THEN 2
        WHEN TRUNC(c.data_entrega) < TRUNC(SYSDATE) THEN 3
        WHEN TRUNC(c.data_entrega) = TRUNC(SYSDATE) THEN 4
        ELSE 5
    END ASC,
    c.data_entrega ASC,
    c.numero_ob ASC
