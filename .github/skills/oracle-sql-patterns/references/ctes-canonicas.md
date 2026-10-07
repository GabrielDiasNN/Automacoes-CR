# CTEs canônicas reutilizáveis

> Referência da skill `oracle-sql-patterns`. Modelos de CTE validados no Oracle SGTPRD: copie o bloco do caso que você está implementando, não leia o arquivo inteiro.

## CTEs Canonicas Reutilizaveis

### CTE: Fase Atual de OBs

```sql
-- Preferir a view: JOIN SGTPRD.VW_BNF_FASEATUALOB FAS ON FAS.NUMERO_OB = OB.NUMERO_OB
-- Se precisar implementar manualmente com ROW_NUMBER:
WITH FASE_ATUAL AS (
  SELECT NUMERO_OB, SEQUENCIA, CODIGO_FASE, STATUS, TIPO_DESTINO,
         ROW_NUMBER() OVER (PARTITION BY NUMERO_OB ORDER BY SEQUENCIA DESC) AS RN
  FROM SGTPRD.OB_FASES
  WHERE NUMERO_OB IN (SELECT NUMERO_OB FROM SGTPRD.OB WHERE SITUACAO = :situacao)
)
SELECT * FROM FASE_ATUAL WHERE RN = 1
```

### CTE: UP Associada a OBs

```sql
-- NUMEROORDEMREAL liga UP a OB (não se chama NUMERO_OB!)
WITH UP_OB AS (
  SELECT UPO.NUMEROORDEMREAL AS NUMERO_OB,
         UPO.NUMEROUP,
         UNP.DESCRICAO AS DS_UP
  FROM SGTPRD.UP_ORDEM_MVTO UPO
  JOIN SGTPRD.UNIDADE_PROGRAMACAO UNP ON UNP.NUMEROUP = UPO.NUMEROUP
  WHERE UPO.NUMEROORDEMREAL IN (:ob_list)
)
```

### CTE: Pedido Comercial de uma OB (cadeia completa)

```sql
WITH PEDIDO_OB AS (
  SELECT OB.NUMERO_OB, IPG.PEDIDO, IPG.ITEMPEDIDO
  FROM SGTPRD.OB OB
  JOIN SGTPRD.PEDPRODUCAOOB PPOB ON PPOB.NUMEROOB = OB.NUMERO_OB
  JOIN SGTPRD.OFORDENS OFO
    ON OFO.NUMEROPEDPRODUCAO = PPOB.NUMERO
   AND OFO.REDUZIDO = PPOB.REDUZIDO
  JOIN SGTPRD.OFPEDIDO OFP ON OFP.NUMEROOF = OFO.NUMEROOF
  JOIN SGTPRD.ITENSPEDIDOQTDES IPQ ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
  JOIN SGTPRD.ITENSPEDIDOGRADE IPG ON IPG.IDITEMPEDGRADE = IPQ.IDITEMPEDGRADE
  WHERE OB.NUMERO_OB = :numero_ob
    AND ROWNUM = 1
)
```

### CTE: Produto Decodificado

```sql
-- BD_BAS_MASCPRODACAB mapeia CODIGO_REDUZIDO para campos semanticos legiveis
WITH PROD_DEC AS (
  SELECT BP.CODIGO_REDUZIDO,
         LPAD(BP.ARTIGO, 3, '0')  AS ARTIGO_3D,
         LPAD(BP.COR, 2, '0')     AS COR_2D,
         BP.DESCR_COR,
         BP.ESTRUTURA,
         BP.DESCR_CLASSIF_COR
  FROM SGTPRD.BD_BAS_MASCPRODACAB BP
)
```

### CTE: OBs com Classificacao de Cor (ORB-07)

```sql
WITH OBS_COR AS (
  SELECT V.NUMERO_OB, V.CD_CLASSIFICACAO_COR
  FROM SGTPRD.VW_EXC_OB_PROD_CLASS_COR V
  WHERE V.CD_CLASSIFICACAO_COR IN (6, 9)  -- 6=BRANCO, 9=BRANCO 2 FIBRAS
```

### CTE: Genealogia Física Multigeracional em Duas Fases (Anti-ORA-00028)

Rastreia peças entre ordens em profundidade arbitrária (N1, N2, N3...) sem estourar PGA/Temp tablespace.
No SGT:
- `SGTPRD.GERAPECADESTINOOB` = **OB Mãe / Geradora** (onde a peça foi gerada).
- `SGTPRD.GERAPECAORIGEMOB`  = **OB Filha / Consumidora** (onde a peça entrou como insumo).
- `SGTPRD.GERAPECAORIGEM`    = **Transformação / Desdobro** de peças (`IDPECASPRODUTOORIGEM` -> `IDPECASPRODUTO`).

```sql
-- Fase 1: Expansão recursiva apenas no grafo de ordens (com CYCLE de segurança)
WITH CadeiaAncestralOrdens (NUMERO_OB, NIVEL_GERACAO) AS (
    SELECT NUMERO_OB, 0 AS NIVEL_GERACAO
    FROM Candidatas
    UNION ALL
    SELECT GEN.OB_MAE, C.NIVEL_GERACAO + 1
    FROM CadeiaAncestralOrdens C
    JOIN (
        -- Continuidade de peça
        SELECT O.NUMERO_OB AS OB_FILHO, DO.NUMERO_OB AS OB_MAE
        FROM SGTPRD.GERAPECAORIGEMOB O
        JOIN SGTPRD.GERAPECADESTINOOB DO 
          ON DO.IDPECASPRODUTO = O.IDPECASPRODUTO AND DO.NUMERO_OB <> O.NUMERO_OB
        UNION
        -- Desdobro/Transformação via GERAPECAORIGEM
        SELECT O.NUMERO_OB AS OB_FILHO, DO.NUMERO_OB AS OB_MAE
        FROM SGTPRD.GERAPECAORIGEMOB O
        JOIN SGTPRD.GERAPECAORIGEM GO ON GO.IDPECASPRODUTO = O.IDPECASPRODUTO
        JOIN SGTPRD.GERAPECADESTINOOB DO 
          ON DO.IDPECASPRODUTO = GO.IDPECASPRODUTOORIGEM AND DO.NUMERO_OB <> O.NUMERO_OB
    ) GEN ON GEN.OB_FILHO = C.NUMERO_OB
)
CYCLE NUMERO_OB SET IS_CYCLE TO 1 DEFAULT 0,
-- Fase 2: Materialização do conjunto fechado de ordens (elimina Hash Join no banco inteiro)
UniversoOrdens AS (
    SELECT /*+ MATERIALIZE */ DISTINCT NUMERO_OB
    FROM CadeiaAncestralOrdens
    WHERE IS_CYCLE = 0
),
-- Fase 3: Arestas físicas forçando Nested Loops indexados
ArestasFisicasPeca AS (
    SELECT /*+ MATERIALIZE LEADING(UO O DO) USE_NL(O) USE_NL(DO) */
        DO.NUMERO_OB AS OB_ORIGEM, DO.IDPECASPRODUTO AS PECA_ORIGEM,
        O.NUMERO_OB  AS OB_DESTINO, O.IDPECASPRODUTO  AS PECA_DESTINO,
        'CONTINUIDADE' AS TIPO_LIGACAO
    FROM UniversoOrdens UO
    JOIN SGTPRD.GERAPECAORIGEMOB O ON O.NUMERO_OB = UO.NUMERO_OB
    JOIN SGTPRD.GERAPECADESTINOOB DO 
      ON DO.IDPECASPRODUTO = O.IDPECASPRODUTO AND DO.NUMERO_OB <> O.NUMERO_OB
    UNION ALL
    SELECT /*+ MATERIALIZE LEADING(UO O GO DO) USE_NL(O) USE_NL(GO) USE_NL(DO) */
        DO.NUMERO_OB AS OB_ORIGEM, DO.IDPECASPRODUTO AS PECA_ORIGEM,
        O.NUMERO_OB  AS OB_DESTINO, GO.IDPECASPRODUTO AS PECA_DESTINO,
        'TRANSFORMACAO' AS TIPO_LIGACAO
    FROM UniversoOrdens UO
    JOIN SGTPRD.GERAPECAORIGEMOB O ON O.NUMERO_OB = UO.NUMERO_OB
    JOIN SGTPRD.GERAPECAORIGEM GO ON GO.IDPECASPRODUTO = O.IDPECASPRODUTO
    JOIN SGTPRD.GERAPECADESTINOOB DO 
      ON DO.IDPECASPRODUTO = GO.IDPECASPRODUTOORIGEM AND DO.NUMERO_OB <> O.NUMERO_OB
),
-- Fase 4: Travessia CONNECT BY NOCYCLE reversa
GenealogiaCompleta AS (
    SELECT 
        CONNECT_BY_ROOT AF.OB_DESTINO   AS OB_FINAL,
        CONNECT_BY_ROOT AF.PECA_DESTINO AS PECA_FINAL,
        AF.OB_ORIGEM                    AS OB_ANCESTRAL,
        AF.PECA_ORIGEM                  AS PECA_ANCESTRAL,
        LEVEL                           AS NIVEL,
        AF.TIPO_LIGACAO
    FROM ArestasFisicasPeca AF
    START WITH AF.OB_DESTINO IN (SELECT NUMERO_OB FROM Candidatas)
    CONNECT BY NOCYCLE PRIOR AF.OB_ORIGEM = AF.OB_DESTINO 
                   AND PRIOR AF.PECA_ORIGEM = AF.PECA_DESTINO
)
```

### CTE: Rastreabilidade de Lotes de Entrada e Classificação Física de Peças (Facção / Terceirização)

Rastreia peças recebidas em lotes de facção (`LOTE_ITENS_NOTA_ENTR`) com apuração exata de quantidade gerada vs volumes e classificação física mutuamente exclusiva de cada peça.
Regras fundamentais:
- **Origem histórica**: determinada estritamente por `GPN.IDLOTEITENSNFE = LOT.ID` (NUNCA por `PADRAO_QUALIDADE_SIN`).
- **Quantidade da NF**: se lote finalizado (`STFINALIZACAO = 2`) e com peças geradas, usar `COUNT(GPN.IDPECASPRODUTO)`; se pendente de etiquetagem (`STFINALIZACAO <> 2`), usar `LOT.VOLUMES`.
- **Precedência física estrita**: (1) `TEM_OB = 1` -> `UTIL_OB` (prioridade absoluta sobre reclassificação); (2) `STPECAPRODUTO = 0 AND PADRAO_QUALIDADE_SIN = 1` -> `SALDO_DISPONIVEL`; (3) movimentos causais específicos (145/670/945 saída inv, 157 com NF remessa, 50 com NF transf, 695 troca qualidade, 23 com NF fat, 55 transf item); (4) reclassificação residual `PADRAO_QUALIDADE_SIN <> 1` -> `TROCA_QUALIDADE`; (5) `OUTRAS_BAIXAS`.

```sql
WITH lotes_elegiveis AS (
    SELECT /*+ MATERIALIZE */
        LOT.ID AS ID_LOTE,
        LOT.NUMERO_NOTA,
        LOT.SERIE_NOTA,
        LOT.IDPESSOAFJ,
        LOT.CODINSREDUZIDO,
        LOT.VOLUMES,
        LOT.STFINALIZACAO,
        COUNT(GPN.IDPECASPRODUTO) AS TOTAL_PECAS_LOTE
    FROM SGTPRD.LOTE_ITENS_NOTA_ENTR LOT
    INNER JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = LOT.CODINSREDUZIDO
    INNER JOIN SGTPRD.MESTRE_NOTA_ENTRADA MNE 
        ON MNE.NUMERO_NOTA = LOT.NUMERO_NOTA
       AND MNE.SERIE_NOTA = LOT.SERIE_NOTA
       AND MNE.IDPESSOAFJ_CLIENTE = LOT.IDPESSOAFJ
    INNER JOIN SGTPRD.PESSOASFJ PES ON PES.IDPESSOAFJ = MNE.IDPESSOAFJ_CLIENTE
    LEFT JOIN SGTPRD.GERAPECANOTAENTRADA GPN ON GPN.IDLOTEITENSNFE = LOT.ID
    LEFT JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.IDPECASPRODUTO = GPN.IDPECASPRODUTO
    WHERE PES.IDCATEGORIFORNECEDOR = 1
      AND ITE.TIPO_ITEM = 9
      AND LOT.QUALIDADE = 1
      AND EXISTS (
          SELECT 1 FROM SGTPRD.ITENS_NOTA_ENTRADA INE
          WHERE INE.NUMERO_NOTA = LOT.NUMERO_NOTA
            AND INE.SERIE_NOTA = LOT.SERIE_NOTA
            AND INE.IDPESSOAFJ = LOT.IDPESSOAFJ
            AND INE.CODINSREDUZIDO = LOT.CODINSREDUZIDO
            AND INE.DEPOSITO = 95
      )
    GROUP BY LOT.ID, LOT.NUMERO_NOTA, LOT.SERIE_NOTA, LOT.IDPESSOAFJ, LOT.CODINSREDUZIDO, LOT.VOLUMES, LOT.STFINALIZACAO
),
itens_lote_resumo AS (
    SELECT
        LE.NUMERO_NOTA,
        LE.SERIE_NOTA,
        LE.IDPESSOAFJ,
        LE.CODINSREDUZIDO,
        SUM(CASE 
            WHEN LE.STFINALIZACAO = 2 AND LE.TOTAL_PECAS_LOTE > 0 THEN LE.TOTAL_PECAS_LOTE
            ELSE LE.VOLUMES
        END) AS QT_PECA_NF
    FROM lotes_elegiveis LE
    GROUP BY LE.NUMERO_NOTA, LE.SERIE_NOTA, LE.IDPESSOAFJ, LE.CODINSREDUZIDO
),
pecas_elegiveis AS (
    SELECT /*+ MATERIALIZE */
        GPN.NUMERO_NOTA,
        GPN.SERIE_NOTA,
        GPN.IDPESSOAFJ,
        GPN.CODINSREDUZIDO,
        GPN.IDPECASPRODUTO,
        GPP.STPECAPRODUTO,
        GPP.PADRAO_QUALIDADE_SIN,
        CASE WHEN EXISTS (
            SELECT 1 FROM SGTPRD.GERAPECAORIGEMOB ORI WHERE ORI.IDPECASPRODUTO = GPN.IDPECASPRODUTO
        ) THEN 1 ELSE 0 END AS TEM_OB
    FROM SGTPRD.GERAPECANOTAENTRADA GPN
    INNER JOIN lotes_elegiveis LE ON LE.ID_LOTE = GPN.IDLOTEITENSNFE
    INNER JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.IDPECASPRODUTO = GPN.IDPECASPRODUTO
),
classificacao_pecas AS (
    SELECT 
        PE.NUMERO_NOTA,
        PE.SERIE_NOTA,
        PE.IDPESSOAFJ,
        PE.CODINSREDUZIDO,
        PE.IDPECASPRODUTO,
        CASE 
            WHEN PE.TEM_OB = 1 THEN 'UTIL_OB'
            WHEN PE.STPECAPRODUTO = 0 AND PE.PADRAO_QUALIDADE_SIN = 1 THEN 'SALDO_DISPONIVEL'
            WHEN MC.ULTIMO_MOV IN (145, 670, 945) THEN 'SAIDA_INV'
            WHEN MC.ULTIMO_MOV = 157 AND MC.MOV_NF = 1 THEN 'REM_INDUS'
            WHEN MC.ULTIMO_MOV = 50 AND MC.MOV_NF = 1 THEN 'TRANSF_FILIAL'
            WHEN MC.ULTIMO_MOV = 695 THEN 'TROCA_QUALIDADE'
            WHEN MC.ULTIMO_MOV = 23 AND MC.MOV_NF = 1 THEN 'FAT'
            WHEN MC.ULTIMO_MOV = 55 THEN 'TRANSF_ITEM'
            WHEN PE.PADRAO_QUALIDADE_SIN <> 1 THEN 'TROCA_QUALIDADE'
            ELSE 'OUTRAS_BAIXAS'
        END AS CATEGORIA_FISICA
    FROM pecas_elegiveis PE
    LEFT JOIN movimentos_causais MC ON MC.IDPECASPRODUTO = PE.IDPECASPRODUTO
)
```

### CTE: Decomposição Temporal em Intervalos Disjuntos via UNION ALL (Anti-ORA-00028 em Janelas Longas)

Estabiliza consultas analíticas com janelas temporais amplas (12 a 13 meses) sobre tabelas massivas do SGT (`SGTPRD.NOTAFISCALCAPA` e joins de faturamento/expedição).
Quando filtros contínuos sobre índices com range intermediário (`IDFILIAL, DTEMISSAO, STNOTAFATURAMENTO`) causam instabilidade no CBO e queda intermitente de sessão (`ORA-00028` na 4ª/5ª execução consecutiva sob concorrência), a decomposição em intervalos matematicamente disjuntos particiona a varredura sem alterar o grão nem os resultados.

Regras e garantias fundamentais:
- **Disjunção Estrita**: $[DT\_INICIO, DT\_CORTE) \cap [DT\_CORTE, DT\_FIM) = \emptyset$ (elimina risco de linhas duplicadas no grão analítico).
- **Cobertura Total**: $[DT\_INICIO, DT\_CORTE) \cup [DT\_CORTE, DT\_FIM) = [DT\_INICIO, DT\_FIM)$ (nenhum evento temporal é perdido).
- **Projeção Idêntica**: Ambos os ramos do `UNION ALL` projetam exatamente a mesma lista tipada de colunas.
- **Ponto de Corte Dinâmico**: Definido na CTE `JANELA`, tipicamente dividindo o histórico em dois blocos de ~6 meses (`ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -6)`).

```sql
WITH JANELA AS (
    SELECT
        ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12) AS DT_INICIO,
        ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -6)  AS DT_CORTE,
        TRUNC(SYSDATE)                        AS DT_FIM
    FROM DUAL
),
FATOS_FILTRADOS AS (
    -- Ramo 1: Historico [DT_INICIO, DT_CORTE)
    SELECT
        NFC.IDNOTAFISCAL,
        NFC.IDFILIAL,
        NFC.DTEMISSAO,
        NFC.IDPESSOAFJ_CLIENTE,
        INF.IDPRODUTO,
        INF.IDPEDIDO,
        INF.IDITENSPEDIDO,
        INF.QTDFATURADA,
        INF.VLTOTALITEM
    FROM SGTPRD.NOTAFISCALCAPA NFC
    JOIN SGTPRD.ITENSNOTAFISCAL INF ON INF.IDNOTAFISCAL = NFC.IDNOTAFISCAL
    CROSS JOIN JANELA J
    WHERE NFC.IDFILIAL = 1
      AND NFC.DTEMISSAO >= J.DT_INICIO
      AND NFC.DTEMISSAO <  J.DT_CORTE
      AND NFC.STNOTAFATURAMENTO = 2
    UNION ALL
    -- Ramo 2: Recente [DT_CORTE, DT_FIM)
    SELECT
        NFC.IDNOTAFISCAL,
        NFC.IDFILIAL,
        NFC.DTEMISSAO,
        NFC.IDPESSOAFJ_CLIENTE,
        INF.IDPRODUTO,
        INF.IDPEDIDO,
        INF.IDITENSPEDIDO,
        INF.QTDFATURADA,
        INF.VLTOTALITEM
    FROM SGTPRD.NOTAFISCALCAPA NFC
    JOIN SGTPRD.ITENSNOTAFISCAL INF ON INF.IDNOTAFISCAL = NFC.IDNOTAFISCAL
    CROSS JOIN JANELA J
    WHERE NFC.IDFILIAL = 1
      AND NFC.DTEMISSAO >= J.DT_CORTE
      AND NFC.DTEMISSAO <  J.DT_FIM
      AND NFC.STNOTAFATURAMENTO = 2
)
```

### CTE: Janela Temporal Parametrizada Multi-Período (Atual, MoM, YoY) com Hint INLINE (Anti-ORA-00028)

Padrão arquitetural canônico para relatórios gerenciais e fechamentos mensais automatizados. Permite execução automática mensal (`NULL` = mês anterior fechado via `SYSDATE`) e reprocessamento histórico retroativo (`'YYYY-MM'`).
**Cuidado de Engenharia CBO**: Quando `JANELA` possui múltiplos consumidores (fases, paradas, dias, estoque), o CBO 12c pode tentar materializar a CTE (`TEMP TABLE TRANSFORMATION`), perdendo o predicate pushdown de datas nas tabelas físicas indexadas (`UNIDADE_PROGRAMACAO`, `BD_PRD_MOVPROD`), gerando full scans e timeout `ORA-00028`. O hint `/*+ INLINE */` na CTE `JANELA` combinado com `/*+ LEADING(J UPR) USE_NL(UPR UOM OBF) */` nos fatos garante que os limites temporais sejam injetados diretamente nos index range scans.

```sql
WITH PARAMETROS AS (
    SELECT CAST(NULL AS VARCHAR2(7)) AS MES_HISTORICO FROM DUAL
),
JANELA AS (
    SELECT /*+ INLINE */
           -- Limites da Competencia Principal (Atual ou Reprocessada)
           CASE 
             WHEN P.MES_HISTORICO IS NOT NULL THEN TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD')
             ELSE ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1)
           END AS DT_INICIO,
           CASE 
             WHEN P.MES_HISTORICO IS NOT NULL THEN ADD_MONTHS(TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD'), 1)
             ELSE TRUNC(SYSDATE, 'MM')
           END AS DT_FIM,
           -- Limites do Mes Anterior (MoM)
           CASE 
             WHEN P.MES_HISTORICO IS NOT NULL THEN ADD_MONTHS(TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD'), -1)
             ELSE ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -2)
           END AS DT_INICIO_MOM,
           CASE 
             WHEN P.MES_HISTORICO IS NOT NULL THEN TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD')
             ELSE ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1)
           END AS DT_FIM_MOM,
           -- Limites do Mesmo Mes do Ano Anterior (YoY)
           CASE 
             WHEN P.MES_HISTORICO IS NOT NULL THEN ADD_MONTHS(TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD'), -12)
             ELSE ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -13)
           END AS DT_INICIO_YOY,
           CASE 
             WHEN P.MES_HISTORICO IS NOT NULL THEN ADD_MONTHS(TO_DATE(P.MES_HISTORICO || '-01', 'YYYY-MM-DD'), -11)
             ELSE ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)
           END AS DT_FIM_YOY,
           -- Rotulo YYYY-MM
           CASE 
             WHEN P.MES_HISTORICO IS NOT NULL THEN P.MES_HISTORICO
             ELSE TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1), 'YYYY-MM')
           END AS MES_REFERENCIA
      FROM PARAMETROS P
)
```

### CTE: Métricas Globais da Tinturaria e Acabado sem Fragmentação

Contagem distinta objetiva e desvinculada de subgrupos de máquina, equipamento, turno ou defeito:

```sql
-- Dias com Tinturaria Normal e Partidas Globais Distintas
BASE_TING_GLOBAIS AS (
    SELECT /*+ LEADING(J UPR) USE_NL(UPR UOM OBF) */
           'ATUAL' AS PERIODO,
           COUNT(DISTINCT TRUNC(UPR.DTPRODFIM)) AS DIAS_COM_TINGIMENTO,
           COUNT(DISTINCT OBF.NUMERO_OB || '-' || TO_CHAR(OBF.SEQUENCIA)) AS PARTIDAS_COM_TINGIMENTO
      FROM JANELA J
      JOIN SGTPRD.UNIDADE_PROGRAMACAO UPR ON UPR.DTPRODFIM >= J.DT_INICIO AND UPR.DTPRODFIM < J.DT_FIM
      JOIN SGTPRD.UP_ORDEM_MVTO       UOM ON UOM.NUMEROUP = UPR.NUMEROUP AND UOM.SETOR = UPR.SETOR
      JOIN SGTPRD.OB_FASES            OBF ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL
                                         AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
     WHERE UPR.SETOR = 5
       AND UPR.EXCLUIDA = 0
       AND UPR.TIPOUP = 0
       AND UPR.STATUS = 0
       AND OBF.CODIGO_FASE = 40
       AND OBF.DESTINO_RECEITA = 1
)
```

### CTE: Decomposição Shapley (Efeito Calendário × Efeito Ritmo Diário)

Reconciliação matemática exata de variações de volume entre dois períodos (resíduo 0,00 kg). Isola a parcela de crescimento oriunda de variação de dias úteis/trabalhados da parcela decorrente de produtividade horária/diária:

```sql
-- Efeito Calendario (kg) e Participacao (%)
ROUND((REF.DIAS_EMB_ATU - REF.DIAS_EMB_MOM) *
      (((REF.KG_EMB_ATU / NULLIF(REF.DIAS_EMB_ATU, 0)) + (REF.KG_EMB_MOM / NULLIF(REF.DIAS_EMB_MOM, 0))) / 2), 2) AS EFEITO_CALENDARIO_KG,

ROUND(
    ((REF.DIAS_EMB_ATU - REF.DIAS_EMB_MOM) *
     (((REF.KG_EMB_ATU / NULLIF(REF.DIAS_EMB_ATU, 0)) + (REF.KG_EMB_MOM / NULLIF(REF.DIAS_EMB_MOM, 0))) / 2))
    / NULLIF(REF.KG_EMB_ATU - REF.KG_EMB_MOM, 0) * 100, 2) AS EFEITO_CALENDARIO_PCT,

-- Efeito Ritmo Diario (kg) e Participacao (%)
ROUND(((REF.KG_EMB_ATU / NULLIF(REF.DIAS_EMB_ATU, 0)) - (REF.KG_EMB_MOM / NULLIF(REF.DIAS_EMB_MOM, 0))) *
      ((REF.DIAS_EMB_ATU + REF.DIAS_EMB_MOM) / 2), 2) AS EFEITO_RITMO_KG,

ROUND(
    (((REF.KG_EMB_ATU / NULLIF(REF.DIAS_EMB_ATU, 0)) - (REF.KG_EMB_MOM / NULLIF(REF.DIAS_EMB_MOM, 0))) *
     ((REF.DIAS_EMB_ATU + REF.DIAS_EMB_MOM) / 2))
    / NULLIF(REF.KG_EMB_ATU - REF.KG_EMB_MOM, 0) * 100, 2) AS EFEITO_RITMO_PCT
```

### CTE: Apuração Mensal de Produção e Reprocesso de Tingimento (Chão de Fábrica SGT)

Padrão canônico validado contra o relatório oficial corporativo "MAIORES PRODUÇÕES - TINGIMENTO" (96 meses históricos comprovados no Oracle SGTPRD com 100% de equivalência matemática):
- **Grão de agregação**: `OB_FASES` (1:1 com `UP_ORDEM_MVTO` para fases concluídas `STATUS = 4`). Uma barca (`UNIDADE_PROGRAMACAO`) pode tingir até 15 ordens (`MAX_OBS_POR_UP = 15`) na mesma partida; somar no nível da UP duplicaria quilos.
- **Classificação Cadastral**: `DESTINO_RECEITA` liga a `SGTPRD.DESTINO.DESTINO` e `SGTPRD.GRUPO_DESTINO.CODIGO_GRUPO`.
  - Produção Normal: `NVL(GDX.TIPO_DESTINO, 0) = 0` (inclui `DESTINO = 1` 'PRODUCAO' e apontamentos operacionais com destino 0/nulo).
  - Reprocesso: `NVL(GDX.TIPO_DESTINO, 0) = 1` (inclui `DESTINO = 2` 'REPROCESSOS FORA DE COR' e `DESTINO = 4` 'REPROCESSOS PARA RECLASSIFICACAO').
- **Escopo de Defeitos**: Fechamentos globais de reprocesso NÃO filtram `GRUPO_DEFEITO`, apurando a totalidade das perdas fabris.
- **Modelagem para Ingestão Analítica (Power BI / Power Query)**:
  - Expor `DATA_MES` como `DATE` truncado (`TRUNC(UPR.DTPRODFIM, 'MM')`), permitindo relacionamentos diretos com tabelas calendário (`dCalendario`) e inteligência temporal DAX sem parsing de strings.
  - Expor valores numéricos puros com nomes em maiúsculas sem aspas (`RANKING`, `DATA_MES`, `QTD_PRODUZIDA`, `QTD_REPROCESSO`, `PERC_REPROCESSO`, `MES`, `ANO`, `DATA_REFERENCIA`), delegando a formatação visual à camada do relatório.

```sql
WITH BASE_PRODUCAO AS (
    SELECT
        TRUNC(UPR.DTPRODFIM, 'MM') AS DATA_MES,
        OBF.KILOS_PRODUZIDOS,
        NVL(GDX.TIPO_DESTINO, 0)   AS TIPO_DESTINO
    FROM SGTPRD.UNIDADE_PROGRAMACAO UPR
    JOIN SGTPRD.UP_ORDEM_MVTO UOM 
        ON UOM.NUMEROUP = UPR.NUMEROUP
    JOIN SGTPRD.MAQUINA MAQ 
        ON MAQ.NUMERO_MAQUINA = UPR.NUMERO_MAQUINA
    JOIN SGTPRD.OB_FASES OBF 
        ON OBF.NUMERO_OB = UOM.NUMEROORDEMREAL 
       AND OBF.SEQUENCIA = UOM.SEQUENCIAORDEMREAL
    LEFT JOIN SGTPRD.DESTINO DEX 
        ON DEX.DESTINO = OBF.DESTINO_RECEITA
    LEFT JOIN SGTPRD.GRUPO_DESTINO GDX 
        ON GDX.CODIGO_GRUPO = DEX.CODIGO_GRUPO
    WHERE UPR.SETOR = 5
      AND UPR.EXCLUIDA = 0
      AND UPR.TIPOUP = 0
      AND OBF.CODIGO_FASE = 40
      AND OBF.STATUS = 4
),
PRODUCAO_MENSAL AS (
    SELECT
        BP.DATA_MES,
        ROUND(SUM(CASE WHEN BP.TIPO_DESTINO = 0 THEN BP.KILOS_PRODUZIDOS ELSE 0 END), 2) AS QTD_PRODUZIDA,
        ROUND(SUM(CASE WHEN BP.TIPO_DESTINO = 1 THEN BP.KILOS_PRODUZIDOS ELSE 0 END), 2) AS QTD_REPROCESSO
    FROM BASE_PRODUCAO BP
    GROUP BY BP.DATA_MES
)
SELECT
    DENSE_RANK() OVER (ORDER BY PM.QTD_PRODUZIDA DESC) AS RANKING,
    PM.DATA_MES,
    PM.QTD_PRODUZIDA,
    PM.QTD_REPROCESSO,
    ROUND((PM.QTD_REPROCESSO / NULLIF(PM.QTD_PRODUZIDA, 0)) * 100, 2) AS PERC_REPROCESSO,
    TO_CHAR(PM.DATA_MES, 'MM') AS MES,
    TO_CHAR(PM.DATA_MES, 'YYYY') AS ANO,
    PM.DATA_MES AS DATA_REFERENCIA
FROM PRODUCAO_MENSAL PM
ORDER BY RANKING;
```
