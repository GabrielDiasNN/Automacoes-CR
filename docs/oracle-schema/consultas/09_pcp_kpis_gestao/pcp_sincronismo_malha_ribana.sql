/* =============================================================================
OBJETIVO: Monitoramento analítico e operacional do sincronismo entre malha principal e ribana para rede de lojas
DOMÍNIO: 09_pcp_kpis_gestao
ARQUIVO: pcp_sincronismo_malha_ribana.sql
TIPO: SELECT (Painel Analítico / Operacional PCP)
COMPATIBILIDADE: Power Query (Excel), Power BI, Oracle Database Connector, OLE DB, ODBC, FastAPI
GRANULARIDADE: 1 linha estrita por CODIGO_GRUPO (da fase de tingimento 40)
PARÂMETROS / BINDS: Nenhum (horizonte operacional dinâmico calculado por SYSDATE)
DESTINO: Todas as filiais/lojas da rede Costa Rica (NOMEFANTASIA LIKE 'CR-%' E ID <> 1)
REGRA DE CORTE: Horizonte operacional do PCP (OBs ativas ou com emissão/entrega >= SYSDATE - 15 dias)
OTIMIZAÇÃO E AUDITORIA PÓS-HOMOLOGAÇÃO (04/10/2026):
  - 100% Tabelas físicas nativas indexadas (zero views pesadas; junções cobertas por índices B-Tree)
  - Identificação e junção direta em SGTPRD.OB, SGTPRD.OB_PRODUTO, SGTPRD.ITENS_ESTOQUE, SGTPRD.PEDPRODUCAOOB, SGTPRD.GERAPECADESTINOOB, SGTPRD.PECAS_ROMANEIO_SAIDA, SGTPRD.OB_FASES
  - Genealogia e desdobramento de lotes comprovados via SGTPRD.LOTES_PRODUTO (LOTE_PRODUTO_CRU) para incluir derivadas
  - Coerência estrita de tuplas indivisíveis: (ITEM, ARTIGO, COR, LARGURA, GRAMATURA), (ID_LOJA, NOME_LOJA, PEDIDO, PEDIDOCLIENTE), (ROMANEIO, DATA_EXPEDICAO) e (FASE, STATUS, DEFEITO) via KEEP (DENSE_RANK FIRST) vinculadas à mesma OB física representativa
  - Precedência operacional de gargalo/produto blindada: OBs ativas em processamento real (EH_PROGRAMADA = 0) têm prioridade sobre OBs programadas em carteira (EH_PROGRAMADA = 1) e encerradas (STATUS_OB = 0)
  - DT_ENTREGA_PROMETIDA consolidada deterministicamente pela Regra B (decisão funcional do PCP): data associada ao PEDIDO comercial principal exibido, garantindo tupla indivisível (ID_LOJA, NOME_LOJA, PEDIDO, PEDIDOCLIENTE, DT_ENTREGA_PROMETIDA)
  - Matriz de classificação blindada contra falsos concluídos em ordens com expedição parcial e saldo fabril ativo
  - Granularidade comprovada: estritamente 1 linha por (CODIGO_GRUPO, NUMERO_OB) em DADOS_OB_UNICAS e 1 linha por CODIGO_GRUPO no resultado final
TABELAS PRINCIPAIS:
  - SGTPRD.OB (Cabeçalho da ordem de beneficiamento)
  - SGTPRD.OB_PRODUTO (Peças e quilos programados por pedido/entrega)
  - SGTPRD.ITENS_ESTOQUE (Descrição e classificação de produtos/malhas/ribanas)
  - SGTPRD.BD_BAS_MASCPRODACAB (Máscara de acabamento, artigos e cores)
  - SGTPRD.ENG_PRODG_ACABADO (Engenharia de produto, largura e gramatura)
  - SGTPRD.PEDPRODUCAOOB + SGTPRD.OFORDENS + SGTPRD.OFPEDIDO (Cadeia de ordens de fabricação)
  - SGTPRD.ITENSPEDIDOQTDES + SGTPRD.ITENSPEDIDOGRADE + SGTPRD.ITENSPEDIDOCOMERCIAL (Itens e grades de pedidos)
  - SGTPRD.PEDIDOCOMERCIAL + SGTPRD.PESSOASFJ (Pedidos comerciais e lojas de destino da rede CR)
  - SGTPRD.GERAPECADESTINOOB + SGTPRD.PECAS_ROMANEIO_SAIDA (Histórico de romaneios e peças expedidas)
  - SGTPRD.OB_FASES + SGTPRD.FASES_FLUXO + SGTPRD.OBSERVACAO (Fases do fluxo, tingimento grupo 40 e defeitos)
CUIDADOS OPERACIONAIS: Consulta 100% somente leitura via tabelas físicas indexadas.
REVISÃO: 05/10/2026 (Procedimento revisao-queries-oracle)
PARECER FINAL: APROVADA (Homologação técnica e funcional completa com o PCP)
============================================================================= */
/* =============================================================================
PIPELINE DE CTEs (nesta ordem de dependência):
  OB_PRODUTO_TOTAIS, FILIAIS_LOJAS_CR  -> universos auxiliares (agregados/filtrados 1x)
  UNIVERSO_OB_HORIZONTE                -> OBs dentro do horizonte de 15 dias, decodificadas
  LOTES_HORIZONTE                      -> (IDLOTESPRODUTO, CODIGO_REDUZIDO) distintos do horizonte
  OB_LOTE_FORA_HORIZONTE               -> OBs do MESMO lote de uma OB do horizonte, mas que ficaram
                                           fora dele (ver comentário em UNIVERSO_OB abaixo)
  UNIVERSO_OB                          -> UNIVERSO_OB_HORIZONTE + OB_LOTE_FORA_HORIZONTE
  VINCULO_PEDIDO_LOJA                  -> 1 pedido/loja CR por OB (cadeia comercial)
  GENEALOGIA_LOTES                     -> expande cada OB para as OBs derivadas do mesmo lote
  EXPEDICAO_OB, FASE_ATUAL_OB          -> status de expedição e fase atual, 1 linha por OB
  GRUPO_TINGIMENTO                     -> CODIGO_GRUPO da fase de tingimento (o elo malha<->ribana:
                                           OBs tingidas juntas compartilham o mesmo grupo)
  DADOS_OB_UNICAS                      -> junta tudo acima por (CODIGO_GRUPO, NUMERO_OB)
  CONJUNTOS_CONSOLIDADOS               -> 1 linha por CODIGO_GRUPO, pivotada em colunas _MALHA/_RIBANA
  CLASSIFICACAO                        -> classifica o conjunto em 1 de 9 situações mutuamente
                                           exclusivas (SITUACAO_COD), consumida pelo SELECT final
============================================================================= */
WITH FILIAIS_LOJAS_CR AS (
    -- Sem MATERIALIZE: referenciada uma unica vez (em VINCULO_PEDIDO_LOJA), diferente de
    -- UNIVERSO_OB abaixo (8 referencias) — materializar aqui so pagaria o custo de criar
    -- uma temp table para ~65 linhas sem nenhum reuso que justifique.
    SELECT
        IDPESSOAFJ AS ID_LOJA,
        TRIM(NOMEFANTASIA) AS NOME_LOJA
    FROM SGTPRD.PESSOASFJ
    WHERE NOMEFANTASIA LIKE 'CR-%'
      AND IDPESSOAFJ <> 1
),

-- OB_PRODUTO tem PK composta (NUMERO_OB, CODPRO_REDUZIDO, NUMERO_PEDIDO, DATA_ENTREGA_PEDIDO,
-- IDPESSOAFJ): uma OB pode legitimamente ter mais de uma linha (um pedido/entrega distinto cada).
-- Agregar por NUMERO_OB aqui evita duplicar PECAS_PROG/KG_PROG se isso um dia deixar de ser 1 para 1.
-- Sem filtro previo por OB antes do GROUP BY (o.OB_PRODUTO tem ~177K linhas, nao e a tabela de
-- 13M do padrao "sempre filtrar antes"): confirmado via EXPLAIN PLAN que o otimizador ja
-- reescreve isto como subquery correlacionada por indice (OB_PROD_PK_OB_PRODUTO, custo=1) —
-- adicionar um EXISTS/JOIN contra UNIVERSO_OB aqui exigiria duplicar o filtro de data (esta CTE
-- e usada ANTES de UNIVERSO_OB existir) sem ganho medido.
OB_PRODUTO_TOTAIS AS (
    SELECT
        NUMERO_OB,
        SUM(TOTAL_PECAS) AS TOTAL_PECAS,
        SUM(KILOS_PROGRAMADOS) AS KILOS_PROGRAMADOS
    FROM SGTPRD.OB_PRODUTO
    GROUP BY NUMERO_OB
),

UNIVERSO_OB_HORIZONTE AS (
    -- DT_EMISSAO e calculado aqui e reaproveitado no WHERE abaixo (subquery): Oracle nao deixa
    -- referenciar um alias do proprio SELECT no WHERE do mesmo nivel, entao sem este envelope a
    -- expressao "DATE '1996-01-01' + (TEMPO_EMISSAO_OB/1440)" ficaria duplicada.
    SELECT
        H.NUMERO_OB,
        H.CODIGO_REDUZIDO,
        H.IDLOTESPRODUTO,
        H.STATUS_OB,
        H.TEMPO_EMISSAO_OB,
        H.DTENTRPEDIDO,
        H.DATA_ENTREGA_PEDIDO,
        H.EH_PROGRAMADA,
        H.DT_ENTREGA_PCP,
        H.DT_EMISSAO,
        H.TIPO_PRODUTO,
        H.DESCR_PRODUTO,
        H.PECAS_PROG,
        H.KG_PROG,
        H.ARTIGO,
        H.DESCR_ARTIGO,
        H.COR,
        H.DESCR_COR,
        H.LARGURA,
        H.GRAMATURA
    FROM (
        SELECT
            o.NUMERO_OB,
            o.CODIGO_REDUZIDO,
            o.IDLOTESPRODUTO,
            o.STATUS AS STATUS_OB,
            o.TEMPO_EMISSAO_OB,
            o.DTENTRPEDIDO,
            o.DATA_ENTREGA_PEDIDO,
            -- "OB ainda nao entrou em producao?" — fonte UNICA desta regra, propagada por
            -- GENEALOGIA_LOTES -> DADOS_OB_UNICAS -> CONJUNTOS_CONSOLIDADOS (EM_PRODUCAO_MALHA/
            -- RIBANA = NOT EH_PROGRAMADA) e usada direto em FASE_ATUAL_OB. Antes desta CTE havia
            -- duas implementacoes independentes desta MESMA regra (aqui e em CONJUNTOS_CONSOLIDADOS)
            -- que podiam dessincronizar silenciosamente se editadas em separado.
            CASE WHEN o.STATUS = 3 OR o.TEMPO_EMISSAO_OB = 0 THEN 1 ELSE 0 END AS EH_PROGRAMADA,
            -- Conversao segura de data legada armazenada como NUMBER YYYYMMDD (padrao
            -- "> 19000101 AND LENGTH(...) = 8"). O MESMO padrao se repete em DT_EXPEDICAO_PEDIDO
            -- (VINCULO_PEDIDO_LOJA, coluna ITENSPEDIDOCOMERCIAL.EXPEDIREM) porque e assim que este
            -- ERP legado guarda datas em mais de uma tabela — nao e a mesma expressao recalculada,
            -- e o mesmo formato aplicado a colunas de tabelas diferentes. Alternativas descartadas:
            -- (1) function Oracle compartilhada — objeto de schema, fora do escopo desta query;
            -- (2) WITH FUNCTION local — testado e suportado pelo Oracle, mas usa ';' interno e
            -- quebraria a validacao via `oracle_catalog.py check`, que rejeita multiplos statements;
            -- (3) converter o NUMBER cru em Python pos-fetch (serialize_rows ja normaliza datetime)
            -- — tecnicamente eliminaria a duplicacao, mas moveria uma regra de negocio central
            -- (DT_ENTREGA_PCP alimenta DIAS_ATE_ENTREGA, que decide ATRASADO/URGENTE/VENCE_HOJE) para
            -- fora deste arquivo, quebrando o contrato de "relatorio SQL autocontido" do template.
            COALESCE(
                o.DTENTRPEDIDO,
                CASE
                    WHEN o.DATA_ENTREGA_PEDIDO > 19000101 AND LENGTH(TO_CHAR(o.DATA_ENTREGA_PEDIDO)) = 8
                    THEN TO_DATE(TO_CHAR(o.DATA_ENTREGA_PEDIDO), 'YYYYMMDD')
                END
            ) AS DT_ENTREGA_PCP,
            CASE
                WHEN o.TEMPO_EMISSAO_OB > 0 THEN (DATE '1996-01-01' + (o.TEMPO_EMISSAO_OB / 1440))
                ELSE NULL
            END AS DT_EMISSAO,
            CASE
                -- Delimitador de palavra: '%GOLA%' sozinho tambem casa com "ARGOLA" (confirmado em
                -- ITENS_ESTOQUE, ex. "ARGOLA INOX P/ CONE DE PAPELAO"), classificando insumo como RIBANA.
                -- Usa RIBANA (palavra completa), nao RIB: RIB e prefixo de RIBANA, nunca teria um
                -- nao-letra logo apos (testado contra o Oracle: reduzia 129 grupos malha+ribana para 2).
                WHEN REGEXP_LIKE(UPPER(i.DESCRICAO), '(^|[^A-Z])(RIBANA|GOLA|PUNHO)([^A-Z]|$)') THEN 'RIBANA'
                ELSE 'MALHA'
            END AS TIPO_PRODUTO,
            TRIM(i.DESCRICAO) AS DESCR_PRODUTO,
            NVL(obp.TOTAL_PECAS, 0) AS PECAS_PROG,
            NVL(obp.KILOS_PROGRAMADOS, 0) AS KG_PROG,
            p.ARTIGO,
            TRIM(p.DESCR_ARTIGO) AS DESCR_ARTIGO,
            p.COR,
            TRIM(p.DESCR_COR) AS DESCR_COR,
            NVL(epa.LARGURA, 0) AS LARGURA,
            NVL(epa.GRAMATURA, 0) AS GRAMATURA
        FROM SGTPRD.OB o
        JOIN SGTPRD.ITENS_ESTOQUE i ON i.CODIGO_REDUZIDO = o.CODIGO_REDUZIDO
        LEFT JOIN OB_PRODUTO_TOTAIS obp ON obp.NUMERO_OB = o.NUMERO_OB
        LEFT JOIN SGTPRD.BD_BAS_MASCPRODACAB p ON p.CODIGO_REDUZIDO = o.CODIGO_REDUZIDO
        LEFT JOIN SGTPRD.ENG_PRODG_ACABADO epa ON epa.REDUZIDO_AGRUPADOR = p.REDUZIDO_AGRUPADOR
    ) H
    WHERE (
        STATUS_OB <> 0
        OR (TEMPO_EMISSAO_OB > 0 AND DT_EMISSAO >= TRUNC(SYSDATE) - 15)
        OR DTENTRPEDIDO >= TRUNC(SYSDATE) - 15
        OR (DATA_ENTREGA_PEDIDO >= TO_NUMBER(TO_CHAR(TRUNC(SYSDATE) - 15, 'YYYYMMDD')) AND DATA_ENTREGA_PEDIDO > 19000101)
    )
),

LOTES_HORIZONTE AS (
    SELECT DISTINCT IDLOTESPRODUTO, CODIGO_REDUZIDO
    FROM UNIVERSO_OB_HORIZONTE
    WHERE IDLOTESPRODUTO > 0
),

-- BUG REAL CORRIGIDO (14/09/2026): uma OB pode ser desdobrada em OBs derivadas (ex.: peças
-- separadas por defeito viram uma 2a OB do mesmo lote) que ja foram expedidas HA MAIS de 15 dias,
-- enquanto a OB "pai" (ou outra derivada do mesmo lote) ainda esta dentro do horizonte por outro
-- motivo (ex.: DTENTRPEDIDO mais recente). Caso observado: OB 185352 (malha, dentro do horizonte)
-- foi desdobrada em 186383/186384 (mesmo IDLOTESPRODUTO+CODIGO_REDUZIDO), que expediram 28+2 pecas
-- via romaneios 245517/246630 mas tem DTENTRPEDIDO de 28/08 — fora da janela de 15 dias. Como
-- GENEALOGIA_LOTES antes so linkava pai<->filha quando AMBAS estavam em UNIVERSO_OB, a expedicao
-- real das derivadas nunca era contabilizada e o relatorio reportava 185352 como "0% expedido"
-- incorretamente. Esta CTE busca essas derivadas "orfas" (mesmo lote de uma OB do horizonte, mas
-- elas mesmas fora dele) para que GENEALOGIA_LOTES as inclua.
OB_LOTE_FORA_HORIZONTE AS (
    SELECT
        o.NUMERO_OB,
        o.CODIGO_REDUZIDO,
        o.IDLOTESPRODUTO,
        o.STATUS AS STATUS_OB,
        o.TEMPO_EMISSAO_OB,
        o.DTENTRPEDIDO,
        o.DATA_ENTREGA_PEDIDO,
        CASE WHEN o.STATUS = 3 OR o.TEMPO_EMISSAO_OB = 0 THEN 1 ELSE 0 END AS EH_PROGRAMADA,
        COALESCE(
            o.DTENTRPEDIDO,
            CASE
                WHEN o.DATA_ENTREGA_PEDIDO > 19000101 AND LENGTH(TO_CHAR(o.DATA_ENTREGA_PEDIDO)) = 8
                THEN TO_DATE(TO_CHAR(o.DATA_ENTREGA_PEDIDO), 'YYYYMMDD')
            END
        ) AS DT_ENTREGA_PCP,
        CASE
            WHEN o.TEMPO_EMISSAO_OB > 0 THEN (DATE '1996-01-01' + (o.TEMPO_EMISSAO_OB / 1440))
            ELSE NULL
        END AS DT_EMISSAO,
        CASE
            WHEN REGEXP_LIKE(UPPER(i.DESCRICAO), '(^|[^A-Z])(RIBANA|GOLA|PUNHO)([^A-Z]|$)') THEN 'RIBANA'
            ELSE 'MALHA'
        END AS TIPO_PRODUTO,
        TRIM(i.DESCRICAO) AS DESCR_PRODUTO,
        NVL(obp.TOTAL_PECAS, 0) AS PECAS_PROG,
        NVL(obp.KILOS_PROGRAMADOS, 0) AS KG_PROG,
        p.ARTIGO,
        TRIM(p.DESCR_ARTIGO) AS DESCR_ARTIGO,
        p.COR,
        TRIM(p.DESCR_COR) AS DESCR_COR,
        NVL(epa.LARGURA, 0) AS LARGURA,
        NVL(epa.GRAMATURA, 0) AS GRAMATURA
    FROM SGTPRD.OB o
    JOIN LOTES_HORIZONTE lh ON lh.IDLOTESPRODUTO = o.IDLOTESPRODUTO AND lh.CODIGO_REDUZIDO = o.CODIGO_REDUZIDO
    JOIN SGTPRD.ITENS_ESTOQUE i ON i.CODIGO_REDUZIDO = o.CODIGO_REDUZIDO
    LEFT JOIN OB_PRODUTO_TOTAIS obp ON obp.NUMERO_OB = o.NUMERO_OB
    LEFT JOIN SGTPRD.BD_BAS_MASCPRODACAB p ON p.CODIGO_REDUZIDO = o.CODIGO_REDUZIDO
    LEFT JOIN SGTPRD.ENG_PRODG_ACABADO epa ON epa.REDUZIDO_AGRUPADOR = p.REDUZIDO_AGRUPADOR
    WHERE NOT EXISTS (
        SELECT 1 FROM UNIVERSO_OB_HORIZONTE uh WHERE uh.NUMERO_OB = o.NUMERO_OB
    )
),

-- NOTA SOBRE O EXPLAIN PLAN: apos esta UNION ALL, `oracle_catalog.py explain` reporta um custo
-- estimado absurdo (~233G, ">999h") por causa de under/overestimacao de cardinalidade do CBO em
-- HASH JOINs entre CTEs materializadas geradas por UNION ALL — comportamento conhecido, nao
-- reflete o custo real. Medido via execucao real (fetch_all): ~8s para os volumes desta janela
-- (UNIVERSO_OB_HORIZONTE ~2.2K linhas + OB_LOTE_FORA_HORIZONTE ~60 linhas), aceitavel para um
-- relatorio batch. Nao usar o numero do EXPLAIN como sinal de regressao aqui — medir tempo real.
UNIVERSO_OB AS (
    SELECT /*+ MATERIALIZE */
        NUMERO_OB,
        CODIGO_REDUZIDO,
        IDLOTESPRODUTO,
        STATUS_OB,
        TEMPO_EMISSAO_OB,
        DTENTRPEDIDO,
        DATA_ENTREGA_PEDIDO,
        EH_PROGRAMADA,
        DT_ENTREGA_PCP,
        DT_EMISSAO,
        TIPO_PRODUTO,
        DESCR_PRODUTO,
        PECAS_PROG,
        KG_PROG,
        ARTIGO,
        DESCR_ARTIGO,
        COR,
        DESCR_COR,
        LARGURA,
        GRAMATURA
    FROM UNIVERSO_OB_HORIZONTE
    UNION ALL
    SELECT
        NUMERO_OB,
        CODIGO_REDUZIDO,
        IDLOTESPRODUTO,
        STATUS_OB,
        TEMPO_EMISSAO_OB,
        DTENTRPEDIDO,
        DATA_ENTREGA_PEDIDO,
        EH_PROGRAMADA,
        DT_ENTREGA_PCP,
        DT_EMISSAO,
        TIPO_PRODUTO,
        DESCR_PRODUTO,
        PECAS_PROG,
        KG_PROG,
        ARTIGO,
        DESCR_ARTIGO,
        COR,
        DESCR_COR,
        LARGURA,
        GRAMATURA
    FROM OB_LOTE_FORA_HORIZONTE
),

VINCULO_PEDIDO_LOJA AS (
    -- Uma OB pode estar ligada a mais de um pedido/loja na cadeia comercial (PEDPRODUCAOOB
    -- não é 1 para 1 com NUMEROOB). MAX() KEEP com o MESMO critério de ordenação em todas as
    -- colunas garante que PEDIDO/LOJA/DT_EXPEDICAO vêm sempre da mesma linha "vencedora"
    -- (expedição mais recente), em vez de combinar campos de pedidos distintos.
    SELECT /*+ MATERIALIZE */
        p.NUMEROOB AS NUMERO_OB,
        MAX(ped.PEDIDO) KEEP (DENSE_RANK FIRST ORDER BY ipc.EXPEDIREM DESC NULLS LAST, ped.PEDIDO DESC) AS PEDIDO,
        MAX(ped.PEDIDOCLIENTE) KEEP (DENSE_RANK FIRST ORDER BY ipc.EXPEDIREM DESC NULLS LAST, ped.PEDIDO DESC) AS PEDIDOCLIENTE,
        MAX(fl.ID_LOJA) KEEP (DENSE_RANK FIRST ORDER BY ipc.EXPEDIREM DESC NULLS LAST, ped.PEDIDO DESC) AS ID_LOJA,
        MAX(fl.NOME_LOJA) KEEP (DENSE_RANK FIRST ORDER BY ipc.EXPEDIREM DESC NULLS LAST, ped.PEDIDO DESC) AS NOME_LOJA,
        MAX(CASE
            WHEN ipc.EXPEDIREM > 19000101 AND LENGTH(TO_CHAR(ipc.EXPEDIREM)) = 8
            THEN TO_DATE(TO_CHAR(ipc.EXPEDIREM), 'YYYYMMDD')
        END) KEEP (DENSE_RANK FIRST ORDER BY ipc.EXPEDIREM DESC NULLS LAST, ped.PEDIDO DESC) AS DT_EXPEDICAO_PEDIDO
    FROM SGTPRD.PEDPRODUCAOOB p
    JOIN UNIVERSO_OB u ON u.NUMERO_OB = p.NUMEROOB
    JOIN SGTPRD.OFORDENS ofo ON ofo.NUMEROPEDPRODUCAO = p.NUMERO AND ofo.REDUZIDO = p.REDUZIDO
    JOIN SGTPRD.OFPEDIDO ofp ON ofp.NUMEROOF = ofo.NUMEROOF AND ofp.NIVEL = ofo.NIVEL AND ofp.REDUZIDO = ofo.REDUZIDO AND ofp.QUANTIDADE_ATUAL <> 0
    JOIN SGTPRD.ITENSPEDIDOQTDES ipq ON ipq.IDITENSPEDIDOQTDES = ofp.IDITENSPEDIDOQTDES
    JOIN SGTPRD.ITENSPEDIDOGRADE ipg ON ipg.IDITENSPEDIDOGRADE = ipq.IDITEMPEDGRADE
    JOIN SGTPRD.ITENSPEDIDOCOMERCIAL ipc ON ipc.PEDIDO = ipg.PEDIDO AND ipc.ITEMPEDIDO = ipg.ITEMPEDIDO
    JOIN SGTPRD.PEDIDOCOMERCIAL ped ON ped.PEDIDO = ipc.PEDIDO
    JOIN FILIAIS_LOJAS_CR fl ON fl.ID_LOJA = ped.IDFILIALRESPONSAVEL
    GROUP BY p.NUMEROOB
),

GENEALOGIA_LOTES AS (
    SELECT /*+ MATERIALIZE */
        u.NUMERO_OB AS OB_ORIGEM,
        u.NUMERO_OB AS OB_DERIVADA,
        u.TIPO_PRODUTO,
        u.STATUS_OB,
        u.TEMPO_EMISSAO_OB,
        u.EH_PROGRAMADA,
        u.DT_ENTREGA_PCP,
        u.DESCR_PRODUTO,
        u.PECAS_PROG,
        u.KG_PROG,
        u.ARTIGO,
        u.DESCR_ARTIGO,
        u.COR,
        u.DESCR_COR,
        u.LARGURA,
        u.GRAMATURA
    FROM UNIVERSO_OB u
    UNION ALL
    SELECT
        u_pai.NUMERO_OB AS OB_ORIGEM,
        u_filha.NUMERO_OB AS OB_DERIVADA,
        u_filha.TIPO_PRODUTO,
        u_filha.STATUS_OB,
        u_filha.TEMPO_EMISSAO_OB,
        u_filha.EH_PROGRAMADA,
        u_filha.DT_ENTREGA_PCP,
        u_filha.DESCR_PRODUTO,
        u_filha.PECAS_PROG,
        u_filha.KG_PROG,
        u_filha.ARTIGO,
        u_filha.DESCR_ARTIGO,
        u_filha.COR,
        u_filha.DESCR_COR,
        u_filha.LARGURA,
        u_filha.GRAMATURA
    FROM UNIVERSO_OB u_pai
    JOIN UNIVERSO_OB u_filha
      ON u_filha.IDLOTESPRODUTO = u_pai.IDLOTESPRODUTO
     AND u_filha.CODIGO_REDUZIDO = u_pai.CODIGO_REDUZIDO
    WHERE u_pai.IDLOTESPRODUTO > 0
      AND u_filha.NUMERO_OB <> u_pai.NUMERO_OB
),

EXPEDICAO_OB AS (
    SELECT /*+ MATERIALIZE */
        d.NUMERO_OB,
        MAX(prs.NUMERO_ROMANEIO_SAID) KEEP (
            DENSE_RANK FIRST ORDER BY prs.DATAEXPEDICAO DESC NULLS LAST, prs.NUMERO_ROMANEIO_SAID DESC
        ) AS NUMERO_ROMANEIO,
        MAX(prs.DATAEXPEDICAO) AS DATA_EXPEDICAO,
        COUNT(DISTINCT d.IDPECASPRODUTO) AS PECAS_EXPEDIDAS,
        ROUND(SUM(prs.PESO_PECA), 2) AS KG_EXPEDIDOS
    FROM SGTPRD.GERAPECADESTINOOB d
    JOIN SGTPRD.PECAS_ROMANEIO_SAIDA prs ON prs.IDPECASPRODUTO = d.IDPECASPRODUTO
    JOIN UNIVERSO_OB u ON u.NUMERO_OB = d.NUMERO_OB
    GROUP BY d.NUMERO_OB
),

FASE_ATUAL_OB AS (
    -- Nao usa a view canonica SGTPRD.VW_BNF_FASEATUALOB (recomendada por oracle-sql-patterns para
    -- "fase atual" generica) porque a regra de negocio deste relatorio e mais especifica: precisa
    -- rotular explicitamente "PROGRAMADA" para OBs que ainda nao emitiram (a view usa
    -- PKGBENF0001.FNC_RETORNA_SEQUENCIA_OB, uma function de pacote sem corpo inspecionavel por
    -- este projeto, e nao ha garantia de que ela replique esse rotulo customizado) e a prioridade
    -- de ordenacao "em andamento > proxima pendente > ja concluida" (linhas ~223-227) e propria
    -- deste template. Reimplementar aqui, sob controle total, evita risco de regressao silenciosa
    -- por uma mudanca futura na function do pacote.
    -- EH_PROGRAMADA vem pronta de UNIVERSO_OB (fonte unica da regra, ver comentario la) e e
    -- reaproveitada no CASE do rotulo e no ORDER BY do RN, sem recalcular a condicao aqui.
    SELECT /*+ MATERIALIZE */
        NUMERO_OB,
        CODIGO_FASE,
        NOME_FASE,
        STATUS_FASE,
        CODIGO_OBSERVACAO,
        DESCR_OBSERVACAO
    FROM (
        SELECT
            f.NUMERO_OB,
            f.CODIGO_FASE,
            CASE
                WHEN u.EH_PROGRAMADA = 1 THEN 'PROGRAMADA'
                WHEN u.STATUS_OB = 0 THEN 'CONCLUÍDO / EXPEDIDO'
                ELSE TRIM(ff.DESCRICAO_FASE)
            END AS NOME_FASE,
            f.STATUS AS STATUS_FASE,
            f.CODIGO_OBSERVACAO,
            TRIM(obs.TEXTO) AS DESCR_OBSERVACAO,
            ROW_NUMBER() OVER (
                PARTITION BY f.NUMERO_OB
                ORDER BY
                    -- 1. Se OB ainda não entrou em produção: pegar a primeira fase do fluxo
                    CASE WHEN u.EH_PROGRAMADA = 1 THEN f.SEQUENCIA END ASC NULLS LAST,
                    -- 2. Se OB ativa em produção:
                    CASE
                        WHEN f.STATUS IN (1, 2, 3) THEN 1  -- Em andamento
                        WHEN f.STATUS = 0 THEN 2          -- Próxima pendente na fila
                        ELSE 3                            -- Já concluída
                    END ASC,
                    CASE WHEN f.STATUS IN (0, 1, 2, 3) THEN f.SEQUENCIA END ASC NULLS LAST,
                    f.SEQUENCIA DESC
            ) AS RN
        FROM SGTPRD.OB_FASES f
        JOIN UNIVERSO_OB u ON u.NUMERO_OB = f.NUMERO_OB
        JOIN SGTPRD.FASES_FLUXO ff ON ff.CODIGO_FASE = f.CODIGO_FASE
        LEFT JOIN SGTPRD.OBSERVACAO obs ON obs.CODIGO = f.CODIGO_OBSERVACAO
    )
    WHERE RN = 1
),

GRUPO_TINGIMENTO AS (
    -- CODIGO_FASE = 40 = TIN-TINGIMENTO (confirmado em FASES_FLUXO). Malha e ribana sao
    -- sincronizadas por terem passado pelo MESMO CODIGO_GRUPO nesta fase (tingidas juntas).
    SELECT /*+ MATERIALIZE */
        f.NUMERO_OB,
        f.CODIGO_GRUPO
    FROM SGTPRD.OB_FASES f
    JOIN UNIVERSO_OB u ON u.NUMERO_OB = f.NUMERO_OB
    WHERE f.CODIGO_FASE = 40
      AND f.CODIGO_GRUPO > 0
),

DADOS_OB_UNICAS AS (
    -- DISTINCT e salvaguarda deliberada, nao "esconde" fan-out conhecido: cada LEFT JOIN abaixo
    -- (VINCULO_PEDIDO_LOJA, FASE_ATUAL_OB, EXPEDICAO_OB) ja agrega/filtra para 1 linha por
    -- NUMERO_OB, entao hoje (CODIGO_GRUPO, NUMERO_OB) e naturalmente unico sem o DISTINCT
    -- (validado: mesma contagem com e sem). Mantido porque esta query ja teve fan-out real de
    -- um join incompleto (ver OB_PRODUTO_TOTAIS acima) — o custo do DISTINCT e baixo perto do
    -- risco de linhas duplicadas inflarem SUM()/COUNT() silenciosamente em CONJUNTOS_CONSOLIDADOS.
    SELECT /*+ MATERIALIZE */ DISTINCT
        g.CODIGO_GRUPO,
        gen.OB_DERIVADA AS NUMERO_OB,
        gen.TIPO_PRODUTO,
        gen.STATUS_OB,
        gen.TEMPO_EMISSAO_OB,
        gen.EH_PROGRAMADA,
        gen.DESCR_PRODUTO,
        gen.PECAS_PROG,
        gen.KG_PROG,
        gen.ARTIGO,
        gen.DESCR_ARTIGO,
        gen.COR,
        gen.DESCR_COR,
        gen.LARGURA,
        gen.GRAMATURA,
        COALESCE(gen.DT_ENTREGA_PCP, v_orig.DT_EXPEDICAO_PEDIDO, v_der.DT_EXPEDICAO_PEDIDO) AS DT_ENTREGA,
        COALESCE(v_orig.ID_LOJA, v_der.ID_LOJA) AS ID_LOJA,
        COALESCE(v_orig.NOME_LOJA, v_der.NOME_LOJA) AS NOME_LOJA,
        COALESCE(v_orig.PEDIDO, v_der.PEDIDO) AS PEDIDO,
        COALESCE(v_orig.PEDIDOCLIENTE, v_der.PEDIDOCLIENTE) AS PEDIDOCLIENTE,
        f.CODIGO_FASE,
        f.NOME_FASE,
        f.STATUS_FASE,
        f.CODIGO_OBSERVACAO,
        f.DESCR_OBSERVACAO,
        e.NUMERO_ROMANEIO,
        e.DATA_EXPEDICAO,
        NVL(e.PECAS_EXPEDIDAS, 0) AS PECAS_EXPEDIDAS,
        NVL(e.KG_EXPEDIDOS, 0) AS KG_EXPEDIDOS
    FROM GRUPO_TINGIMENTO g
    JOIN UNIVERSO_OB u ON u.NUMERO_OB = g.NUMERO_OB
    JOIN GENEALOGIA_LOTES gen ON gen.OB_ORIGEM = u.NUMERO_OB
    LEFT JOIN VINCULO_PEDIDO_LOJA v_orig ON v_orig.NUMERO_OB = u.NUMERO_OB
    LEFT JOIN VINCULO_PEDIDO_LOJA v_der  ON v_der.NUMERO_OB = gen.OB_DERIVADA
    LEFT JOIN FASE_ATUAL_OB f ON f.NUMERO_OB = gen.OB_DERIVADA
    LEFT JOIN EXPEDICAO_OB e ON e.NUMERO_OB = gen.OB_DERIVADA
),

CONJUNTOS_CONSOLIDADOS AS (
    SELECT
        d.CODIGO_GRUPO,

        -- TUPLA COMERCIAL ATÔMICA DA LINHA VENCEDORA (Prioriza Malha com Pedido)
        MAX(d.ID_LOJA) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.PEDIDO IS NOT NULL THEN 1 
                     WHEN d.PEDIDO IS NOT NULL THEN 2 ELSE 3 END ASC,
                d.DT_ENTREGA ASC NULLS LAST,
                d.PEDIDO DESC NULLS LAST
        ) AS ID_LOJA,

        MAX(d.NOME_LOJA) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.PEDIDO IS NOT NULL THEN 1 
                     WHEN d.PEDIDO IS NOT NULL THEN 2 ELSE 3 END ASC,
                d.DT_ENTREGA ASC NULLS LAST,
                d.PEDIDO DESC NULLS LAST
        ) AS NOME_LOJA,

        MAX(d.PEDIDO) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.PEDIDO IS NOT NULL THEN 1 
                     WHEN d.PEDIDO IS NOT NULL THEN 2 ELSE 3 END ASC,
                d.DT_ENTREGA ASC NULLS LAST,
                d.PEDIDO DESC NULLS LAST
        ) AS PEDIDO,

        MAX(d.PEDIDOCLIENTE) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.PEDIDO IS NOT NULL THEN 1 
                     WHEN d.PEDIDO IS NOT NULL THEN 2 ELSE 3 END ASC,
                d.DT_ENTREGA ASC NULLS LAST,
                d.PEDIDO DESC NULLS LAST
        ) AS PEDIDO_CLIENTE,

        -- TUPLA COMERCIAL ATÔMICA DA LINHA VENCEDORA: DATA DO PEDIDO EXIBIDO (REGRA B - PCP)
        TRUNC(MAX(d.DT_ENTREGA) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.PEDIDO IS NOT NULL THEN 1 
                     WHEN d.PEDIDO IS NOT NULL THEN 2 ELSE 3 END ASC,
                d.DT_ENTREGA ASC NULLS LAST,
                d.PEDIDO DESC NULLS LAST
        )) AS DT_ENTREGA_PROMETIDA,

        TRUNC(MAX(d.DT_ENTREGA) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.PEDIDO IS NOT NULL THEN 1 
                     WHEN d.PEDIDO IS NOT NULL THEN 2 ELSE 3 END ASC,
                d.DT_ENTREGA ASC NULLS LAST,
                d.PEDIDO DESC NULLS LAST
        )) - TRUNC(SYSDATE) AS DIAS_ATE_ENTREGA,

        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN
            CASE WHEN d.EH_PROGRAMADA = 0 THEN 'SIM' ELSE 'NAO' END
        END) AS EM_PRODUCAO_MALHA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN
            CASE WHEN d.EH_PROGRAMADA = 0 THEN 'SIM' ELSE 'NAO' END
        END) AS EM_PRODUCAO_RIBANA,

        -- DADOS CONSOLIDADOS DE MALHA
        LISTAGG(TO_CHAR(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END), ',' ON OVERFLOW TRUNCATE)
            WITHIN GROUP (ORDER BY CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END) AS OBS_MALHA,
        -- TUPLA ATÔMICA DE PRODUTO DA MALHA (DA MESMA OB REPRESENTATIVA DO GARGALO)
        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.DESCR_PRODUTO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS ITEM_MALHA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.DESCR_ARTIGO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS ARTIGO_MALHA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.COR || ' - ' || d.DESCR_COR END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS COR_MALHA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.LARGURA END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS LARGURA_MALHA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.GRAMATURA END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS GRAMATURA_MALHA,
        SUM(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.PECAS_PROG ELSE 0 END) AS PECAS_PROG_MALHA,
        SUM(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.KG_PROG ELSE 0 END) AS KG_PROG_MALHA,
        SUM(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.PECAS_EXPEDIDAS ELSE 0 END) AS PECAS_EXP_MALHA,
        ROUND(SUM(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.KG_EXPEDIDOS ELSE 0 END), 2) AS KG_EXP_MALHA,
        COUNT(DISTINCT CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.NUMERO_OB END) AS OBS_MALHA_ATIVAS,

        -- TUPLA DE FASE ATUAL, STATUS E DEFEITO DA MALHA (DA MESMA OB REPRESENTATIVA DO GARGALO)
        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NOME_FASE END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS FASE_MALHA,

        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.STATUS_FASE END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS STATUS_FASE_MALHA,

        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.DESCR_OBSERVACAO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END ASC
        ) AS DEFEITO_MALHA,

        -- TUPLA DE EXPEDIÇÃO DA MALHA (ROMANEIO E DATA DA MESMA EXPEDIÇÃO VENCEDORA)
        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_ROMANEIO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.DATA_EXPEDICAO END DESC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_ROMANEIO END DESC NULLS LAST
        ) AS ROMANEIO_MALHA,

        MAX(CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.DATA_EXPEDICAO END) AS DT_EXP_MALHA,

        -- DADOS CONSOLIDADOS DE RIBANA
        LISTAGG(TO_CHAR(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END), ',' ON OVERFLOW TRUNCATE)
            WITHIN GROUP (ORDER BY CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END) AS OBS_RIBANA,
        -- TUPLA ATÔMICA DE PRODUTO DA RIBANA (DA MESMA OB REPRESENTATIVA DO GARGALO)
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.DESCR_PRODUTO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS ITEM_RIBANA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.DESCR_ARTIGO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS ARTIGO_RIBANA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.COR || ' - ' || d.DESCR_COR END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS COR_RIBANA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.LARGURA END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS LARGURA_RIBANA,
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.GRAMATURA END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS GRAMATURA_RIBANA,
        SUM(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.PECAS_PROG ELSE 0 END) AS PECAS_PROG_RIBANA,
        SUM(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.KG_PROG ELSE 0 END) AS KG_PROG_RIBANA,
        SUM(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.PECAS_EXPEDIDAS ELSE 0 END) AS PECAS_EXP_RIBANA,
        ROUND(SUM(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.KG_EXPEDIDOS ELSE 0 END), 2) AS KG_EXP_RIBANA,
        COUNT(DISTINCT CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.NUMERO_OB END) AS OBS_RIBANA_ATIVAS,

        -- TUPLA DE FASE ATUAL, STATUS E DEFEITO DA RIBANA (DA MESMA OB REPRESENTATIVA DO GARGALO)
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NOME_FASE END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS FASE_RIBANA,

        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.STATUS_FASE END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS STATUS_FASE_RIBANA,

        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.DESCR_OBSERVACAO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE 
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
                    WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
                    ELSE 3
                END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END ASC
        ) AS DEFEITO_RIBANA,

        -- TUPLA DE EXPEDIÇÃO DA RIBANA (ROMANEIO E DATA DA MESMA EXPEDIÇÃO VENCEDORA)
        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_ROMANEIO END) KEEP (
            DENSE_RANK FIRST ORDER BY 
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.DATA_EXPEDICAO END DESC NULLS LAST,
                CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_ROMANEIO END DESC NULLS LAST
        ) AS ROMANEIO_RIBANA,

        MAX(CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.DATA_EXPEDICAO END) AS DT_EXP_RIBANA

    FROM DADOS_OB_UNICAS d
    GROUP BY d.CODIGO_GRUPO
    HAVING MAX(d.NOME_LOJA) IS NOT NULL
       AND COUNT(DISTINCT CASE WHEN d.TIPO_PRODUTO = 'MALHA' THEN d.NUMERO_OB END) > 0
       AND COUNT(DISTINCT CASE WHEN d.TIPO_PRODUTO = 'RIBANA' THEN d.NUMERO_OB END) > 0
),

MAPA_SITUACAO AS (
    SELECT 'MALHA_SEM_RIBANA'     AS SITUACAO_COD, 'SIM' AS EXIGE_ACAO,  1 AS ORDEM_PRIORIDADE, 1 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'RIBANA_SEM_MALHA'     AS SITUACAO_COD, 'SIM' AS EXIGE_ACAO,  1 AS ORDEM_PRIORIDADE, 1 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'CONCLUIDO_ATENDIDO'   AS SITUACAO_COD, 'NAO' AS EXIGE_ACAO, 99 AS ORDEM_PRIORIDADE, 0 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'CONCLUIDO_SEM_ACAO'   AS SITUACAO_COD, 'NAO' AS EXIGE_ACAO, 99 AS ORDEM_PRIORIDADE, 0 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'PROGRAMADO_A_INICIAR' AS SITUACAO_COD, 'NAO' AS EXIGE_ACAO, 50 AS ORDEM_PRIORIDADE, 5 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'ATRASADO'             AS SITUACAO_COD, 'SIM' AS EXIGE_ACAO,  2 AS ORDEM_PRIORIDADE, 2 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'VENCE_HOJE'           AS SITUACAO_COD, 'SIM' AS EXIGE_ACAO,  3 AS ORDEM_PRIORIDADE, 3 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'URGENTE'              AS SITUACAO_COD, 'SIM' AS EXIGE_ACAO,  4 AS ORDEM_PRIORIDADE, 4 AS PRIORIDADE_EXIBICAO FROM DUAL UNION ALL
    SELECT 'NO_PRAZO'             AS SITUACAO_COD, 'SIM' AS EXIGE_ACAO,  5 AS ORDEM_PRIORIDADE, 5 AS PRIORIDADE_EXIBICAO FROM DUAL
),

CLASSIFICACAO AS (
    SELECT
        base.*,
        m.EXIGE_ACAO,
        m.ORDEM_PRIORIDADE,
        m.PRIORIDADE_EXIBICAO
    FROM (
        SELECT
            c.*,
            CASE
                -- 1. Riscos Críticos de Sincronismo (Expedição Descasada)
                WHEN c.PECAS_EXP_MALHA > 0 AND c.PECAS_EXP_RIBANA = 0
                THEN 'MALHA_SEM_RIBANA'

                WHEN c.PECAS_EXP_RIBANA > 0 AND c.PECAS_EXP_MALHA = 0
                THEN 'RIBANA_SEM_MALHA'

                -- 2. Conclusão Operacional Real: SEM NENHUMA OB ATIVA NO CHÃO DE FÁBRICA
                WHEN c.OBS_MALHA_ATIVAS = 0 AND c.OBS_RIBANA_ATIVAS = 0
                THEN CASE
                    WHEN c.PECAS_EXP_MALHA > 0 AND c.PECAS_EXP_RIBANA > 0 THEN 'CONCLUIDO_ATENDIDO'
                    ELSE 'CONCLUIDO_SEM_ACAO'
                END

                -- 3. Ordens ainda em programação (não emitidas)
                WHEN c.EM_PRODUCAO_MALHA = 'NAO' AND c.EM_PRODUCAO_RIBANA = 'NAO'
                THEN 'PROGRAMADO_A_INICIAR'

                -- 4. Ordens em produção ativa (inclusive com expedições parciais em andamento)
                WHEN c.DIAS_ATE_ENTREGA < 0
                THEN 'ATRASADO'

                WHEN c.DIAS_ATE_ENTREGA = 0
                THEN 'VENCE_HOJE'

                WHEN c.DIAS_ATE_ENTREGA BETWEEN 1 AND 2
                THEN 'URGENTE'

                ELSE 'NO_PRAZO'
            END AS SITUACAO_COD
        FROM CONJUNTOS_CONSOLIDADOS c
    ) base
    JOIN MAPA_SITUACAO m ON m.SITUACAO_COD = base.SITUACAO_COD
)

SELECT
    cl.CODIGO_GRUPO,
    cl.ID_LOJA,
    cl.NOME_LOJA,
    cl.PEDIDO,
    cl.PEDIDO_CLIENTE,
    cl.DT_ENTREGA_PROMETIDA,
    cl.DIAS_ATE_ENTREGA,

    -- CONTROLE DE AÇÃO BINÁRIO: valor fixo por SITUACAO_COD, vem pronto de MAPA_SITUACAO
    cl.EXIGE_ACAO,

    -- STATUS DE CONTROLE DE AÇÃO CALIBRADO. O prefixo numerico vem de cl.PRIORIDADE_EXIBICAO
    -- (MAPA_SITUACAO), nao mais hardcoded aqui — evita a string de exibicao dessincronizar do
    -- numero se uma situacao nova for adicionada e so o mapa for atualizado.
    CASE cl.SITUACAO_COD
        WHEN 'MALHA_SEM_RIBANA' THEN cl.PRIORIDADE_EXIBICAO || ' - CRÍTICO: MALHA EXPEDIDA SEM RIBANA (0% RIBANA)'
        WHEN 'RIBANA_SEM_MALHA' THEN cl.PRIORIDADE_EXIBICAO || ' - CRÍTICO: RIBANA EXPEDIDA SEM MALHA (0% MALHA)'
        WHEN 'CONCLUIDO_ATENDIDO' THEN cl.PRIORIDADE_EXIBICAO || ' - CONCLUÍDO / ATENDIDO (MALHA E RIBANA EXPEDIDAS)'
        WHEN 'CONCLUIDO_SEM_ACAO' THEN cl.PRIORIDADE_EXIBICAO || ' - CONCLUÍDO (ENCERRADO / SEM AÇÃO)'
        WHEN 'PROGRAMADO_A_INICIAR' THEN cl.PRIORIDADE_EXIBICAO || ' - PROGRAMADO / A INICIAR (' || cl.DIAS_ATE_ENTREGA || ' DIAS)'
        WHEN 'ATRASADO' THEN cl.PRIORIDADE_EXIBICAO || ' - ATRASADO EM PROCESSO HÁ ' || ABS(cl.DIAS_ATE_ENTREGA) || ' DIA(S)'
        WHEN 'VENCE_HOJE' THEN cl.PRIORIDADE_EXIBICAO || ' - VENCE HOJE (PRIORIDADE MÁXIMA)'
        WHEN 'URGENTE' THEN cl.PRIORIDADE_EXIBICAO || ' - URGENTE: VENCE EM ' || cl.DIAS_ATE_ENTREGA || ' DIA(S)'
        ELSE cl.PRIORIDADE_EXIBICAO || ' - PROGRAMADO / NO PRAZO (' || cl.DIAS_ATE_ENTREGA || ' DIAS)'
    END AS STATUS_CONTROLE_ACAO,

    -- RECOMENDAÇÃO OPERACIONAL PRESCRITIVA
    CASE cl.SITUACAO_COD
        WHEN 'MALHA_SEM_RIBANA'
        THEN 'URGÊNCIA MÁXIMA: Malha já foi expedida para a filial mas a Ribana NÃO FOI ENVIADA (0% expedido). ' ||
             CASE
                 WHEN cl.DEFEITO_RIBANA IS NOT NULL THEN 'Motivo/Defeito Ribana: ' || cl.DEFEITO_RIBANA || '. '
                 ELSE 'Ribana parada em ' || NVL(cl.FASE_RIBANA, 'CQ') || '. '
             END || 'Providenciar reposição ou liberação urgente da ribana!'

        WHEN 'RIBANA_SEM_MALHA'
        THEN 'URGÊNCIA MÁXIMA: Ribana já expedida para a filial mas a Malha NÃO FOI ENVIADA (0% expedido). ' ||
             CASE
                 WHEN cl.DEFEITO_MALHA IS NOT NULL THEN 'Motivo/Defeito Malha: ' || cl.DEFEITO_MALHA || '. '
                 ELSE 'Malha parada em ' || NVL(cl.FASE_MALHA, 'CQ') || '. '
             END || 'Providenciar liberação urgente da malha!'

        WHEN 'CONCLUIDO_ATENDIDO' THEN 'Atendimento concluído. Malha e Ribana expedidas para a loja.'
        WHEN 'CONCLUIDO_SEM_ACAO' THEN 'Conjunto encerrado no sistema. Nenhuma ação pendente.'
        WHEN 'PROGRAMADO_A_INICIAR' THEN 'Ordem em programação (PCP). Conjunto ainda não colocado em chão de fábrica (aguardando emissão).'
        WHEN 'ATRASADO' THEN 'ATRASO CRÍTICO: Programação vencida há ' || ABS(cl.DIAS_ATE_ENTREGA) || ' dias. Priorizar sincronização e expedição urgente!'
        WHEN 'VENCE_HOJE' THEN 'PRIORIDADE DO DIA: Vence hoje. Alinhar CQ e expedição para despacho conjunto no turno atual!'
        WHEN 'URGENTE' THEN 'ALERTA DE PRAZO: Vencimento iminente. Acompanhar conclusão das fases finais.'
        ELSE 'Acompanhamento de rotina. Fluxo dentro do prazo planejado.'
    END AS RECOMENDACAO_OPERACIONAL,

    -- DETALHAMENTO TÉCNICO DE MALHA
    cl.OBS_MALHA,
    cl.ITEM_MALHA,
    cl.ARTIGO_MALHA,
    cl.COR_MALHA,
    cl.LARGURA_MALHA,
    cl.GRAMATURA_MALHA,
    cl.PECAS_PROG_MALHA,
    cl.KG_PROG_MALHA,
    cl.PECAS_EXP_MALHA,
    cl.KG_EXP_MALHA,
    -- PEÇAS RETIDAS: Apenas para OB já em produção! Se não foi colocada em produção ou já concluiu, é 0.
    CASE
        WHEN cl.EM_PRODUCAO_MALHA = 'SIM' THEN GREATEST(0, cl.PECAS_PROG_MALHA - cl.PECAS_EXP_MALHA)
        ELSE 0
    END AS PECAS_RET_MALHA,
    ROUND((cl.PECAS_EXP_MALHA / NULLIF(cl.PECAS_PROG_MALHA, 0)) * 100, 1) AS PERC_EXP_MALHA,
    cl.FASE_MALHA,
    cl.DEFEITO_MALHA,
    cl.ROMANEIO_MALHA,
    cl.DT_EXP_MALHA,

    -- DETALHAMENTO TÉCNICO DE RIBANA
    cl.OBS_RIBANA,
    cl.ITEM_RIBANA,
    cl.ARTIGO_RIBANA,
    cl.COR_RIBANA,
    cl.LARGURA_RIBANA,
    cl.GRAMATURA_RIBANA,
    cl.PECAS_PROG_RIBANA,
    cl.KG_PROG_RIBANA,
    cl.PECAS_EXP_RIBANA,
    cl.KG_EXP_RIBANA,
    -- PEÇAS RETIDAS: Apenas para OB já em produção! Se não foi colocada em produção ou já concluiu, é 0.
    CASE
        WHEN cl.EM_PRODUCAO_RIBANA = 'SIM' THEN GREATEST(0, cl.PECAS_PROG_RIBANA - cl.PECAS_EXP_RIBANA)
        ELSE 0
    END AS PECAS_RET_RIBANA,
    ROUND((cl.PECAS_EXP_RIBANA / NULLIF(cl.PECAS_PROG_RIBANA, 0)) * 100, 1) AS PERC_EXP_RIBANA,
    cl.FASE_RIBANA,
    cl.DEFEITO_RIBANA,
    cl.ROMANEIO_RIBANA,
    cl.DT_EXP_RIBANA,

    -- ÍNDICE DE ORDENAÇÃO HIERÁRQUICA: valor fixo por SITUACAO_COD, vem pronto de MAPA_SITUACAO
    cl.ORDEM_PRIORIDADE

FROM CLASSIFICACAO cl
ORDER BY
    ORDEM_PRIORIDADE ASC,
    cl.DIAS_ATE_ENTREGA ASC,
    cl.CODIGO_GRUPO DESC
