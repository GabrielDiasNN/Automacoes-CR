/* =============================================================================
OBJETIVO: Relatório "MAIORES PRODUÇÕES - TINGIMENTO" (Ranking Mensal Histórico de Produção Normal e Reprocesso)
DOMÍNIO: 01_beneficiamento_tingimento
ARQUIVO: bnf_maiores_producoes_tingimento.sql
TIPO: KPI Consolidado Executivo / Gestão Fabril e Qualidade
PARÂMETROS / BINDS: Nenhum (corte histórico completo mensal dos apontamentos)
TABELAS PRINCIPAIS:
  - SGTPRD.UNIDADE_PROGRAMACAO (UPR)
  - SGTPRD.UP_ORDEM_MVTO (UOM)
  - SGTPRD.MAQUINA (MAQ)
  - SGTPRD.OB_FASES (OBF)
  - SGTPRD.DESTINO (DEX)
  - SGTPRD.GRUPO_DESTINO (GDX)
DESTINO: Ingestão Power BI / Power Query / Modelagem Tabular Fabril
GRANULARIDADE: 1 linha por competência mensal (Ano + Mês)
CAMPOS RETORNADOS:
  1. RANKING (Int64): Posição ordinal decrescente por volume produzido normal
  2. DATA_MES (Date): Primeiro dia do mês (TRUNC DTPRODFIM 'MM'). Substitui a coluna
     textual "Descr. Mês Ano" da referência original, cuja formatação é delegada ao Power Query / DAX.
  3. QTD_PRODUZIDA (Decimal): Produção normal de tingimento confirmada em kg
  4. QTD_REPROCESSO (Decimal): Reprocesso de tingimento confirmado em kg
  5. PERC_REPROCESSO (Decimal): Percentual relativo de reprocesso sobre a produção normal
  6. MES (Int64): Mês numérico (1 a 12)
  7. ANO (Int64): Ano numérico com 4 dígitos
  8. DATA_REFERENCIA (Date): Último dia do mês (LAST_DAY DATA_MES)
REGRAS DE NEGÓCIO E COMPROVAÇÃO CADASTRAL:
  - Filtro Operacional de Tingimento:
    * UPR.SETOR = 5 (Tinturaria / Beneficiamento)
    * OBF.CODIGO_FASE = 40 (Fase de Tingimento)
    * UPR.TIPOUP = 0 (Unidade de Programação Normal de Produção)
    * UPR.EXCLUIDA = 0 (Expurgo de apontamentos cancelados)
    * OBF.STATUS = 4 (Fase de tingimento confirmada/concluída)
  - Produção Normal (QTD_PRODUZIDA):
    * Fases confirmadas com NVL(GDX.TIPO_DESTINO, 0) = 0.
    * Engloba DESTINO_RECEITA = 1 (cadastrado em DESTINO como "PRODUCAO", grupo "PRODUCAO")
      e apontamentos sem destino cadastrado (DESTINO_RECEITA = 0 / TIPO_DESTINO IS NULL).
  - Reprocesso (QTD_REPROCESSO):
    * Fases confirmadas com GDX.TIPO_DESTINO = 1.
    * Comprovado no cadastro do ERP SGT:
      - DESTINO = 2 ("REPROCESSOS FORA DE COR", grupo "REPROCESSOS", TIPO_DESTINO = 1)
      - DESTINO = 4 ("REPROCESSOS PARA RECLASSIFICACAO", grupo "REPROCESSOS RECLASSIFICAR", TIPO_DESTINO = 1)
    * Ausência de filtro por defeito: a consulta apura todos os apontamentos de reprocesso
      (TIPO_DESTINO = 1) sem restringir a coluna OBF.GRUPO_DEFEITO, diferindo de outros
      indicadores que filtram apenas defeitos internos 1, 3 e 4.
  - Índice de Reprocesso (PERC_REPROCESSO):
    * Calculado estritamente como (QTD_REPROCESSO / QTD_PRODUZIDA) * 100, com proteção
      contra divisão por zero via NULLIF.
CARDINALIDADE E INTEGRIDADE DE JOINS (COMPROVADA NO ORACLE):
  - UPR -> UOM: 1:N (uma UP agrupa de 1 a N ordens de benefício tingidas na mesma partida da barca).
  - OBF -> UOM: 1:1 estrita por chave (NUMERO_OB, SEQUENCIA). Cada fase concluída está vinculada
    a exatamente uma UP, garantindo que o peso KILOS_PRODUZIDOS não sofra duplicação.
  - OBF -> DEX -> GDX: 1:1 através de DESTINO_RECEITA e CODIGO_GRUPO.
  - Sintaxe ANSI 100% pura: sem uso de operadores legados (+).
HISTÓRICO DE REVISÃO:
  - 01/10/2026: Engenharia reversa e consolidação oficial no catálogo de queries.
    Validação histórica integral em 96 competências (Novembro/2018 até Outubro/2026)
    com equivalência matemática determinística aos números de chão de fábrica do SGT.
    Aprovada no guard_sql (exit 0) e validada via Tools/validar_sql_oracle.py.
============================================================================= */

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
    ROW_NUMBER() OVER (ORDER BY PM.QTD_PRODUZIDA DESC) AS RANKING,
    PM.DATA_MES,
    PM.QTD_PRODUZIDA,
    PM.QTD_REPROCESSO,
    ROUND(NVL(PM.QTD_REPROCESSO * 100.0 / NULLIF(PM.QTD_PRODUZIDA, 0), 0), 2) AS PERC_REPROCESSO,
    CAST(EXTRACT(MONTH FROM PM.DATA_MES) AS NUMBER(2)) AS MES,
    CAST(EXTRACT(YEAR FROM PM.DATA_MES) AS NUMBER(4)) AS ANO,
    LAST_DAY(PM.DATA_MES) AS DATA_REFERENCIA
FROM PRODUCAO_MENSAL PM
ORDER BY RANKING
