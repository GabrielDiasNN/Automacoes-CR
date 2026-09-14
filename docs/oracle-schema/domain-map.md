# Mapa de Domínios Semânticos — Schema Oracle SGTPRD

> Curadoria humana sobre dados reais do dicionário Oracle, verificados em
> 13/09/2026 via `Tools/build_oracle_catalog.py` + `Tools/oracle_catalog.py`.
> Schema real: 3.608 tabelas, 1.729 views, 74.095 colunas, 3.921 FKs — este
> documento cobre só os ~55 objetos críticos das automações ativas.

---

## Como Usar Este Documento

Este arquivo é a camada narrativa (domínios de negócio, joins canônicos,
armadilhas conhecidas) — leia-o para entender o "porquê". Para qualquer fato
pontual (uma coluna existe? qual o tipo? quais os valores de um código?),
**não confie neste texto sem checar** — prefira o catálogo local, que reflete
o banco de verdade e não fica desatualizado silenciosamente:

```powershell
.venv\Scripts\python Tools\oracle_catalog.py table OB
.venv\Scripts\python Tools\oracle_catalog.py find "receita bloqueada"
.venv\Scripts\python Tools\oracle_catalog.py path OB ITENSPEDIDOGRADE
.venv\Scripts\python Tools\oracle_catalog.py distinct CLASSIFICACAO_COR CODIGO_CLASSIFICACAO --with-desc
```

`docs/oracle-schema/core-graph.json` traz a mesma topologia em JSON (objetos
+ FKs entre eles) para leitura programática. Nenhum dos dois documentos aqui
é gerado automaticamente — se o schema mudar, rode o build e revise este
texto; ele já continha pelo menos um valor de domínio errado (ver nota na
seção Qualidade/Receitas) que só foi pego comparando com o catálogo real.

**Regra de segurança**: sempre prefixe com `SGTPRD.` e use bind variables —
nunca interpole valores nas strings SQL.

---

## Domínios do Schema

### 🏭 Domínio Produção / Beneficiamento

Núcleo do sistema. Controla o ciclo de vida das Ordens de Beneficiamento (OBs)
desde a abertura até o encerramento, passando por todas as fases produtivas.

| Objeto | Tipo | Linhas | Papel |
|--------|------|--------|-------|
| `OB` | TABLE | 177K | Tabela central das OBs. Chave natural: `NUMERO_OB`. Contém `TIPO_ORDEM`, `SITUACAO`, `CODPRO_REDUZIDO`, `KILOS_PROGRAMADOS`. |
| `OB_FASES` | TABLE | 1.3M | Fases de cada OB no fluxo. Uma OB → muitas fases (`SEQUENCIA`). Registra `STATUS`, `CODIGO_FASE`, `CODIGO_PLACA`, `NUMEROORDEMMOVIMENTO`. |
| `OB_PRODUTO` | TABLE | 177K | Produto da OB: `CODPRO_REDUZIDO`, `KILOS_PROGRAMADOS`, `TOTAL_PECAS_CONFIRM`. |
| `FASES_FLUXO` | TABLE | 38 | Tabela referência de fases (38 linhas). Contém `CODIGO_FASE`, `DESCRICAO`, `GRUPO_FASES`. |
| `UNIDADE_PROGRAMACAO` | TABLE | 1.6M | Unidades de programação do chão de fábrica. Chave: `NUMEROUP`. |
| `UP_ORDEM_MVTO` | TABLE | 1.5M | Liga UPs a OBs: `NUMEROORDEMREAL = NUMERO_OB`. |
| `VW_BNF_FASEATUALOB` | VIEW | — | Fase atual (última) de cada OB. **Use no lugar de subquery MAX(SEQUENCIA).** |
| `VW_ENU_STATUS_OB_FASES` | VIEW | — | Enum de status de OB_FASES: `STATUS → DESCRICAO`. |
| `VW_BNF_OB_FASES_UP` | VIEW | — | OB_FASES + Unidade de Programação. |
| `VW_PI_CBPAP02_PRODBENEF` | VIEW | — | View consolidada de produção de beneficiamento. Base do snapshot. |

**Joins canônicos:**
```sql
-- Fase atual sem subquery
JOIN SGTPRD.VW_BNF_FASEATUALOB FAS ON FAS.NUMERO_OB = OB.NUMERO_OB

-- OB_FASES a OB (sempre por NUMERO_OB)
JOIN SGTPRD.OB_FASES OBF ON OBF.NUMERO_OB = OB.NUMERO_OB

-- UP a OB (campo diferente!)
JOIN SGTPRD.UP_ORDEM_MVTO UPO ON UPO.NUMEROORDEMREAL = OBF.NUMERO_OB

-- Fase para descrição
JOIN SGTPRD.FASES_FLUXO FFL ON FFL.CODIGO_FASE = OBF.CODIGO_FASE

-- Status de fase com descrição
JOIN SGTPRD.VW_ENU_STATUS_OB_FASES ENS ON ENS.STATUS = OBF.STATUS
```

---

### 🧵 Domínio Peças / Rastreabilidade

Rastreia peças de entrada e saída de cada OB. Tabelas de alto volume
(5M–13M+ linhas). **Sempre use índices via NUMERO_OB ou IDPECASPRODUTO.**

| Objeto | Tipo | Linhas | Papel |
|--------|------|--------|-------|
| `GERAPECASPRODUTO` | TABLE | **13.4M** | Catálogo master de peças. Chave: `IDPECASPRODUTO`. Liga a `ITENS_ESTOQUE` via `CODIGO_REDUZIDO_PROD`. |
| `GERAPECAORIGEMOB` | TABLE | 5.1M | Peças de entrada de cada OB. FK: `NUMERO_OB → OB`, `IDPECASPRODUTO → GERAPECASPRODUTO`. |
| `GERAPECADESTINOOB` | TABLE | 5.1M | Peças de saída de cada OB. Mesmo padrão de origem. |
| `GERAPECAPEDCOMERCIAL` | TABLE | 956 | Liga peças a pedidos comerciais. FK: `NUMERO_PEDIDO_COMERC → ITENSPEDIDOCOMERCIAL`. |

**Atenção de performance**: `GERAPECASPRODUTO` tem 13M linhas. Sempre filtrar
por `NUMERO_OB` via `GERAPECAORIGEMOB`/`GERAPECADESTINOOB` antes de acessar
`GERAPECASPRODUTO`.

---

### 🧪 Domínio Qualidade / Receitas de Tingimento

Controla o processo de tingimento: receitas, bloqueios de laboratório e
movimentos de pesagem.

| Objeto | Tipo | Linhas | Papel |
|--------|------|--------|-------|
| `MOVTO_RECEITA` | TABLE | 1.3M | Movimentos de receitas. `NUMEROORDEM` = `OB_FASES.NUMEROORDEMMOVIMENTO`. Contém `IDOPE_PESAGEM`. |
| `CADASTRO_RECEITAS` | TABLE | 6.7K | Master de receitas. PK composta 6 campos. Liga a `CLASSIFICACAO_COR`. |
| `LIGA_CADREC_ITEMREC` | TABLE | 6.7K | Liga receitas ao laboratório. Contém `USUARIO_ALTEROU` (ID numérico). |
| `LABRECEITA_BLOQUEADA` | TABLE | 7.3K | Bloqueios de receita. Flag `CBRECEITALIBERADA`. |
| `CLASSIFICACAO_COR` | TABLE | — | Enum de classificações de cor. Valores reais (`CODIGO_CLASSIFICACAO`): 1=CLARA, 6=BRANCO, 9=BRANCO 2 FIBRAS. ORB-07 filtra `IN (6, 9)` para "branco" — corrigido em 13/09/2026: a versão anterior deste texto dizia "6=CORES CLARAS, 9=BRANCO", errado. |
| `COR_FINALIDADE` | TABLE | — | Liga classificação de cor a finalidades de depósito. |
| `TIPO_FINALIDADE_FIO` | TABLE | — | Finalidades de fio. **3=CORES CLARAS, 4=BRANCO** no dep. 95 (ORB-07). |
| `BENLOTEFINALIDADE` | TABLE | 30.7K | Lotes de finalidade de beneficiamento. |
| `BENDETLOTEFINALIDADE` | TABLE | 61.5K | Detalhe dos lotes. `IDLOTEFINALIDADE → BENLOTEFINALIDADE`. |
| `VW_LAC_RECPRD_RECLAB` | VIEW | — | Cruza receitas produção ↔ lab. Fonte de Receitas Bloqueadas. |
| `VW_EXC_OB_PROD_CLASS_COR` | VIEW | — | `CD_CLASSIFICACAO_COR` por OB. Fonte da ORB-07. |

**Join crítico (Receitas Emitidas):**
```sql
-- OB_FASES conecta a MOVTO_RECEITA pelo campo de nome diferente!
JOIN SGTPRD.MOVTO_RECEITA M ON M.NUMEROORDEM = OBF.NUMEROORDEMMOVIMENTO
```

**Lookup de usuário (Receitas Bloqueadas):**
```sql
LEFT JOIN SGTPRD.VW_SIS_SENHA_USUARIO VSU ON VSU.CODREDUSUARIO = LCR.USUARIO_ALTEROU
```

---

### 📦 Domínio Estoque / Cadastro de Itens

| Objeto | Tipo | Linhas | Papel |
|--------|------|--------|-------|
| `ITENS_ESTOQUE` | TABLE | 24.9K | Master de itens. `CODIGO_REDUZIDO` é a chave natural do sistema. Contém `DESCRICAO`, `TIPO_ITEM`, `SITUACAO`, `LINHA_PRODUTO`. |
| `PESSOASFJ` | TABLE | — | Pessoas e fornecedores. `IDPESSOASFJ` como chave. |
| `OPERADOR` | TABLE | — | Operadores. `IDOPERADOR` como chave. |
| `BD_BAS_MASCPRODACAB` | TABLE | — | **Decodificador de produto**: mapeia `CODIGO_REDUZIDO` para `ARTIGO`, `COR`, `ESTRUTURA`, `DESCR_COR`, `DESCR_CLASSIF_COR`. |
| `VW_SIS_SENHA_USUARIO` | VIEW | — | Usuários do sistema. `CODREDUSUARIO → NOME`. |

---

### 💼 Domínio Comercial / Pedidos

Cadeia de rastreabilidade da OB até o pedido comercial do cliente.
**Cadeia**: `OB → PEDPRODUCAOOB → OFORDENS → OFPEDIDO → ITENSPEDIDOQTDES → ITENSPEDIDOGRADE → ITENSPEDIDOCOMERCIAL`

| Objeto | Tipo | Linhas | Papel |
|--------|------|--------|-------|
| `PEDPRODUCAOOB` | TABLE | 197K | Liga OB a pedido de produção. `NUMEROOB = OB.NUMERO_OB`. |
| `OFORDENS` | TABLE | 188K | Ordens de fabricação. Liga `NUMEROPEDPRODUCAO` a `OFITENS`. |
| `OFPEDIDO` | TABLE | 152K | Liga OF a `IDITENSPEDIDOQTDES`. |
| `ITENSPEDIDOQTDES` | TABLE | 190K | Quantidades por grade. Liga a `ITENSPEDIDOGRADE` via `IDITEMPEDGRADE`. |
| `ITENSPEDIDOGRADE` | TABLE | 190K | Grade de tamanhos/cores. Liga a `ITENSPEDIDOCOMERCIAL`. |
| `ITENSPEDIDOCOMERCIAL` | TABLE | 190K | Itens de pedidos comerciais. PK: (`PEDIDO`, `ITEMPEDIDO`). |
| `GERAPECAPEDCOMERCIAL` | TABLE | 956 | Liga `GERAPECASPRODUTO` a `ITENSPEDIDOCOMERCIAL`. |

**Padrão de join cadeia completa (Montagem de Terceirizados):**
```sql
JOIN SGTPRD.PEDPRODUCAOOB PPOB ON PPOB.NUMEROOB = OB.NUMERO_OB
JOIN SGTPRD.OFORDENS OFO ON OFO.NUMEROPEDPRODUCAO = PPOB.NUMERO AND OFO.REDUZIDO = PPOB.REDUZIDO
JOIN SGTPRD.OFPEDIDO OFP ON OFP.NUMEROOF = OFO.NUMEROOF
JOIN SGTPRD.ITENSPEDIDOQTDES IPQ ON IPQ.IDITENSPEDIDOQTDES = OFP.IDITENSPEDIDOQTDES
JOIN SGTPRD.ITENSPEDIDOGRADE IPG ON IPG.IDITEMPEDGRADE = IPQ.IDITEMPEDGRADE
```

---

### ⚙️ Domínio Engenharia / Equipamentos

| Objeto | Tipo | Papel |
|--------|------|-------|
| `ENG_PRODG_ACABADO` | TABLE | Especificações técnicas do produto acabado: gramatura, largura, densidade. Chave: `REDUZIDO_AGRUPADOR`. |
| `MAQUINA` | TABLE | Cadastro de máquinas: `(SETOR, NUMERO_MAQUINA)`. Parâmetros técnicos de beneficiamento, relação de banho. |
| `VARIANTE_DESENHO` | TABLE | Variantes de desenho dos produtos. `MAQ_PADRAO_PRODUCAO → MAQUINA`. |
| `VW_ENU_TIPO_DE_MAQUINAS_SETOR` | VIEW | Tipos de máquina com descrição legível. |
| `VW_F7_PRD_PROD_EXTERNA` | VIEW | Produção externa (terceirização). |

---

## Functions Relevantes para Automações

| Função | Uso |
|--------|-----|
| `SGTPRD.FNC_ESP_REC_PES(NUMERO_OB)` | Retorna 0 (não pesada) ou 1 (pesada). Usado em Receitas Emitidas. |
| `SGTPRD.optstraggrsemvirgula(texto)` | Agrega strings sem vírgula (similar LISTAGG). Usado em Montagem de Terceirizados. |
| `SGTPRD.optstraggr(texto)` | Versão com separador. |
| `SGTPRD.WM_CONCAT(coluna)` | Concatenação de valores. |

---

## Mapa de Automação × Domínio

| Automação | Domínios Principais | Tabelas-Chave |
|-----------|---------------------|---------------|
| Receitas Emitidas | Produção + Qualidade | OB_FASES, MOVTO_RECEITA, UP_ORDEM_MVTO, ITENS_ESTOQUE |
| Receitas Bloqueadas | Qualidade + Cadastro | VW_LAC_RECPRD_RECLAB, LIGA_CADREC_ITEMREC, LABRECEITA_BLOQUEADA |
| OBs Paradas Fase | Produção | OB, OB_FASES, GERAPECAORIGEMOB, PEDPRODUCAOOB |
| OBs Fluxo Sem Tingimento | Produção + Peças + Estoque | OB, OB_FASES, GERAPECASPRODUTO, TIPO_FINALIDADE_FIO |
| OBs Restrição Branco (ORB-07) | Qualidade + Peças | VW_EXC_OB_PROD_CLASS_COR, GERAPECASPRODUTO, COR_FINALIDADE |
| Montagem de Terceirizados | Produção + Comercial + Peças | OB, OB_FASES, PEDPRODUCAOOB, OFORDENS, OFPEDIDO, ITENSPEDIDOGRADE |
| Produção Beneficiamento | Produção + Engenharia | VW_PI_CBPAP02_PRODBENEF, OB_FASES, FASES_FLUXO, MAQUINA |

---

## Convenções de Nomenclatura do ERP

| Prefixo/Padrão | Significado |
|----------------|-------------|
| `OB_*` | Entidades de Ordens de Beneficiamento |
| `VW_BNF_*` | Views de Beneficiamento |
| `VW_PI_*` | Views de Produção Industrial |
| `VW_ENU_*` | Enumerações (tabelas de código→descrição) |
| `VW_EXC_*` | Views de exceção/regra de negócio |
| `VW_LAC_*` | Views do Laboratório de Cores |
| `VW_SIS_*` | Views de sistema |
| `VW_ESP_*` | Views de especificações |
| `VW_F7_*` | Views do módulo F7 (engenharia) |
| `BD_*` | Data Warehouse / BigData interno |
| `BEN*` | Beneficiamento (tabelas operacionais) |
| `CF*` | Configuração de processos (confecção/corte) |
| `COML_*` | Módulo Comercial |
| `ENG_*` | Engenharia do produto |
| `FNC_*` | Funções (scalars) |
| `GERAPECA*` | Rastreabilidade de peças |
| `UP_*` | Unidade de Programação |

---

## Regras Críticas de SQL

1. **Prefixo obrigatório**: sempre `SGTPRD.<objeto>` — nunca sem prefixo de schema.
2. **Bind variables**: sempre `WHERE NUMERO_OB = :numero_ob`, nunca interpolação.
3. **ROWNUM**: para `MAX` sem subquery use `ROWNUM = 1` no WHERE ou `FETCH FIRST 1 ROWS ONLY`.
4. **Colunas com nome diferente**: `OB_FASES.NUMEROORDEMMOVIMENTO ≠ MOVTO_RECEITA.NUMEROORDEM` — são o mesmo dado mas com nomes distintos.
5. **NUMERO_OB × NUMEROOB**: alguns objetos usam `NUMERO_OB` (com underline) outros `NUMEROOB` (sem). Ver cadeia comercial.
6. **Agregação de strings**: use `SGTPRD.OPTSTRAGGRSEMVIRGULA` em vez de `LISTAGG` para compatibilidade com versões legadas.
