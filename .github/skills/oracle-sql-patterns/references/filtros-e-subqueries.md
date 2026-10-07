# Filtros validados e padrões de subquery

> Referência da skill `oracle-sql-patterns`. Filtros com semântica confirmada em produção e padrões de subquery (KEEP/DENSE_RANK, precedência fabril, prazo comercial, turno principal).

## Filtros Validados em Produção

Conferidos no Oracle em 29/09/2026 (a fonte completa, com contagens e provas, é
`docs/oracle-schema/consultas/REGRAS_NEGOCIO.md`, fonte canônica das regras de negócio; só as consultas ✅ do `CATALOGO_QUERIES.md` valem como referência). `OB.SITUACAO` **não existe**; o status da OB é numérico.

```sql
-- OB aberta (OB.STATUS: 0 encerrada, 1 emitida, 3 programada, 5 interditada Kanban)
WHERE OB.STATUS <> 0

-- Fase pendente (OB_FASES.STATUS: 0 programada, 1 emitida, 2 pesada, 3 em execução, 4 confirmada)
WHERE OBF.STATUS <> 4

-- Receita bloqueada (LIGA_CADREC_ITEMREC -> LABRECEITA_BLOQUEADA; 0 = bloqueada)
WHERE LRB.BLOQUEIO_RECEITA = 0

-- Receita ativa: PROCESSO_ATIVO_PRODU é VARCHAR2 com '0'/'1' (não 'S', e não número)
WHERE CRE.PROCESSO_ATIVO_PRODU = '1'

-- Deposito 95 (fio externo) com finalidades claras/branco (não reverificado em 29/09/2026)
WHERE GPP.CODIGO_DEPOSITO = 95
  AND TFF.IDFINALIDADE IN (3, 4)
```

Datas seriais: `OB.TEMPO_*` e `OB_FASES.TEMPO_*` são **minutos desde 01/01/1996**;
`UNIDADE_PROGRAMACAO.TEMPO*` são **dias desde 30/12/1899**. Para filtrar por janela, compare a
coluna com um limite no mesmo formato em vez de converter a coluna:

```sql
-- data de um campo de OB: literal DATE em ISO, como o Oracle exige
DATE '1996-01-01' + OBF.TEMPO_FINAL_CONFIRMA / 1440
-- janela dos últimos 30 dias, sem função na coluna
WHERE OBF.TEMPO_FINAL_CONFIRMA >= (TRUNC(SYSDATE) - 30 - DATE '1996-01-01') * 1440
```

### Filtros de Beneficiamento e Acabamento (Tingimento vs Rama Crua)

```sql
-- Tingimento real no SGT (governado por fase e processo industrial, NUNCA por tipo máquina):
WHERE (VPF.CODIGO_FASE IN (40, 45, 210) 
   OR  VPF.PI_REC IN (401, 451, 2101, 5001, 5002, 5003, 5004, 5005, 5006))

-- Eventos físicos válidos na Rama (Tipo Máquina 6, RM01/RM02):
WHERE VPF.TIPO_MAQUINA = 6 
  AND VPF.STATUS = 0 
  AND VPF.TIPO_DESTINO = 0
  AND OBE.CODIGO_FLUXO IN (204, 302, 304, 305, 409, 412)

-- Primeira passagem física da OB na máquina (DATA_HORA_FIM desempata pois DATA_FIM é truncada):
ROW_NUMBER() OVER (
    PARTITION BY VPF.NUMERO_OB 
    ORDER BY VPF.DATA_HORA_FIM, VPF.SEQUENCIA, VPF.NUMERO_MAQUINA
) AS RN
```

## Padrões de Subquery

```sql
-- MAX com ROWNUM (compativel Oracle 11g+)
(SELECT OB3.TOTAL_PECAS_CONFIRM
 FROM SGTPRD.OB_PRODUTO OB3
 WHERE OB3.NUMERO_OB = OBE.NUMERO_OB
 AND ROWNUM = 1)

-- DECODE (sintaxe Oracle legada)
DECODE(O3.TOTAL_PECAS_CONFIRM, 0,
  ROUND(O3.KILOS_PROGRAMADOS / NVL(PESO_PAD, 1), 0),
  O3.TOTAL_PECAS_CONFIRM)

-- CASE WHEN (mais legivel para lógica nova)
CASE WHEN SGTPRD.FNC_ESP_REC_PES(BASE.NUMERO_OB) = 0 THEN 'NAO' ELSE 'SIM' END AS PESADA

-- Agregacao de strings (padrão do projeto)
(SELECT SGTPRD.optstraggrsemvirgula(TRIM(UPPER(C.TEXTO)))
 FROM SGTPRD.OBSERVACAO C
 WHERE C.CODIGO = OBE.CODIGO_OBSERVACAO) AS OBS_OB
```

### Padrão: Coerência de Tuplas Atômicas via KEEP (DENSE_RANK FIRST)

Evita a geração de "tuplas artificiais" (quimeras) onde campos correlacionados de uma mesma entidade física (ex.: produto, pedido, fase, expedição) vêm de ordens ou lotes distintos por uso ingênuo de `MAX()` ou `MIN()` independentes.

```sql
-- RUIM: MAX() independente mistura largura de uma OB e gramatura de outra
MAX(d.LARGURA)   AS LARGURA,
MAX(d.GRAMATURA) AS GRAMATURA

-- BOM: Tupla atômica indivisível vinculada rigorosamente à mesma OB representativa
MAX(d.LARGURA) KEEP (
    DENSE_RANK FIRST ORDER BY 
        CASE 
            WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
            WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
            ELSE 3
        END ASC,
        CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
        CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
        d.NUMERO_OB ASC
) AS LARGURA,
MAX(d.GRAMATURA) KEEP (
    DENSE_RANK FIRST ORDER BY 
        CASE 
            WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 0 THEN 1
            WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 AND d.EH_PROGRAMADA = 1 THEN 2
            ELSE 3
        END ASC,
        CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.STATUS_OB <> 0 THEN d.CODIGO_FASE END ASC NULLS LAST,
        CASE WHEN d.TIPO_PRODUTO = 'MALHA' AND d.DESCR_OBSERVACAO IS NOT NULL THEN 1 ELSE 2 END ASC,
        d.NUMERO_OB ASC
) AS GRAMATURA
```

### Padrão: Precedência Operacional Estrita Fabril (Gargalo / Chão de Fábrica)

Para identificar a OB representativa ou gargalo operacional de um grupo fabril:
1. **Nível 1 (Produção Real / Chão de Fábrica):** `STATUS_OB <> 0 AND EH_PROGRAMADA = 0` (ordem física já emitida e em processo).
2. **Nível 2 (Programação em Carteira):** `STATUS_OB <> 0 AND EH_PROGRAMADA = 1` (ordem planejada/aguardando emissão).
3. **Nível 3 (Encerradas / Histórico):** `STATUS_OB = 0` (apenas se não houver nenhuma ordem ativa).
4. **Desempate Técnico:** `CODIGO_FASE ASC NULLS LAST` (gargalo de fluxo), presença de apontamento de defeito (`DESCR_OBSERVACAO IS NOT NULL`) e `NUMERO_OB ASC`.

### Padrão: Alinhamento Comercial Indivisível de Prazo de Entrega (Regra B - PCP)

Em agrupamentos onde coexistem múltiplos pedidos ou componentes desmembrados (ex.: Malha e Ribana):
- A data de entrega (`DT_ENTREGA_PROMETIDA`) e os dias até a entrega (`DIAS_ATE_ENTREGA`) devem ser calculados com o **mesmo critério de seleção do PEDIDO comercial exibido**.
- Isso garante que `(ID_LOJA, NOME_LOJA, PEDIDO, PEDIDOCLIENTE, DT_ENTREGA_PROMETIDA)` formem uma única referência comercial auditável, eliminando o risco de exibir o pedido de um cliente com a data de entrega de outro.

### Padrão: Determinação Determinística de Turno Principal via KEEP (DENSE_RANK LAST)

Em análises de operadores agrupadas por grupo operacional ou máquina onde o operador trabalhou em múltiplos turnos:
- Para preservar 1 linha por operador (evitando duplicar o operador no ranking), o turno de maior volume de produção deve ser determinado deterministicamente sem quebrar a agregação.
- **Técnica em 2 passos**:
  1. Pré-calcular o volume do operador por turno via Window Function na CTE de fatos:
     `SUM(VPF.KILOS) OVER (PARTITION BY COD_GRUPO, CODIGO_OPERADOR, VPF.TURNO_FIM) AS KG_TURNO`
  2. Projetar o turno vencedor na agregação usando `MAX() KEEP (DENSE_RANK LAST)` ordenado pelo volume do turno e pelo número do turno como critério de desempate:
     ```sql
     MAX(TURNO) KEEP (DENSE_RANK LAST ORDER BY KG_TURNO, TURNO) AS TURNO_PRINCIPAL
     ```
- Isso elimina subqueries correlacionadas lentas e assegura estabilidade total no Oracle 12c.
```

## Template: OBs com Status de Fase

```sql
SELECT
  OB.NUMERO_OB,
  OB.CODIGO_REDUZIDO,
  ITE.DESCRICAO AS DS_PRODUTO,
  OBF.SEQUENCIA,
  OBF.CODIGO_FASE,
  FFL.DESCRICAO_FASE AS DS_FASE,
  OBF.STATUS AS ST_FASE,
  OBF.CODIGO_PLACA AS NR_KANBAN
FROM SGTPRD.OB OB
JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OB.NUMERO_OB
JOIN SGTPRD.ITENS_ESTOQUE ITE ON ITE.CODIGO_REDUZIDO = OB.CODIGO_REDUZIDO
LEFT JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE
WHERE OB.STATUS <> 0
  AND OBF.CODIGO_FASE IN (:fases)
ORDER BY OB.NUMERO_OB, OBF.SEQUENCIA
```
