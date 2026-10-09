# Performance e anti-patterns

> Referência da skill `oracle-sql-patterns`. Leia ao otimizar consulta lenta ou antes de entregar SQL novo: tabela completa de anti-patterns medidos e o protocolo de benchmark.

## Dicas de Performance

```sql
-- RUIM: full scan de 13M linhas
SELECT * FROM SGTPRD.GERAPECASPRODUTO WHERE CODIGO_REDUZIDO_PROD = :red

-- BOM: via GERAPECAORIGEMOB filtrado por OB
SELECT GPP.*
FROM SGTPRD.GERAPECAORIGEMOB GPO
JOIN SGTPRD.GERAPECASPRODUTO GPP ON GPP.IDPECASPRODUTO = GPO.IDPECASPRODUTO
WHERE GPO.NUMERO_OB = :numero_ob
```

```python
# Sempre sincronizar arraysize e fetchmany para reduzir round-trips
cursor.arraysize = batch_size  # padrão do projeto: 5000
cursor.execute(sql, params)
rows = cursor.fetchmany(batch_size)  # 1 round-trip por batch
```

### Pré-Agregação Compartilhada em Tabelas Transacionais Massivas
Quando múltiplos consumidores (ex.: totais por turno/fluxo e contagem de dias úteis distintos) necessitam da mesma tabela física massiva (ex.: `SGTPRD.BD_PRD_MOVPROD` com 60M+ linhas), **nunca** faça varreduras independentes por CTE.
- **Padrão Canônico**: Crie uma CTE intermediária pré-agregada no grão mínimo comum estrito:
  $$\text{Grão Mínimo} = [\text{DT\_MES}, \text{STATUS\_MES}, \text{DIA}, \text{TURNO}, \text{FLUXO}, \text{IS\_ESTAMPADO}]$$
- **Consumo Aditivo e Distributivo**:
  - Métricas aditivas (`QUANTIDADE_REAL`, `QT_PECAS`): são agregadas via `SUM(SUM(...))` a partir da pré-agregação, preservando 100% da igualdade matemática com a tabela base.
  - Métricas de frequência/dias (`DIAS_PRODUTIVOS`): agregam via `COUNT(DISTINCT DIA)` a partir da mesma pré-agregação, sem nova leitura na tabela física.
- **Resultado Estrutural Comprovado no CBO**: Reduz de 2 ou 3 varreduras físicas para 1 único acesso à tabela base no plano (`EXPLAIN PLAN`), com materialização automática em cursor duration memory (`SYS_TEMP_...`).

### Comportamento do CBO e Desnecessidade do Hint `/*+ MATERIALIZE */`
- O Oracle 12c+ CBO detecta autonomamente quando uma CTE possui 2 ou mais consumidores e aplica a transformação `TEMP TABLE TRANSFORMATION / LOAD AS SELECT (CURSOR DURATION MEMORY)`.
- **Regra de Ouro (só para CTE com 2+ consumidores)**: Não force `/*+ MATERIALIZE */` preventivamente. O plano gerado pelo CBO com hint e sem hint em CTEs multi-consumidoras é rigorosamente idêntico. CTE com **um** consumidor é fundida na consulta principal e aí o hint pode ser decisivo — ver o anti-pattern correspondente. Forçar o hint artificialmente engessa o otimizador e pode induzir falhas de recursos em execuções concorrentes.

### Protocolo de Benchmark e Rigor Causal
Em ambiente produtivo com usuário `CONSULTA` (sem acesso a `V$SQL`, `V$MYSTAT` ou estatísticas internas de I/O):
- **Evidência Empírica vs. Hipótese Causal**: Separar categoricamente métricas medidas (tempo de parede monotônico, hash SHA-256 do resultado, estabilidade em N runs) de suposições sobre o kernel (PGA, Temp, buffer cache, Resource Manager), tratando estas últimas apenas como hipóteses analíticas.
- **Fresh Sessions vs. Buffer Cache Compartilhado**: Abrir nova conexão por execução (*fresh session*) reduz efeitos de estado de sessão, mas **não elimina** o buffer cache compartilhado da instância (SGA). Execuções atípicas rápidas (~1s) devem ser registradas como compatíveis com cache de blocos ou oscilação transitória, e a comparação deve ser sempre sustentada pela **mediana** de $N \ge 5$ execuções alternadas.
- **Pausa de Descompressão**: Em baterias de teste de estabilidade com múltiplas execuções de queries analíticas, inserir pausa mínima entre runs e abrir conexão isolada por iteração, evitando interferência por aquecimento de socket ou listener.

## Anti-Patterns Conhecidos

| Anti-Pattern                                                   | Problema                                | Correcao                                          |
| -------------------------------------------------------------- | --------------------------------------- | ------------------------------------------------- |
| `FROM SGTPRD.GERAPECASPRODUTO WHERE CODIGO_REDUZIDO_PROD = :x` | Full scan 13M                           | Filtrar via `GERAPECAORIGEMOB.NUMERO_OB` primeiro |
| `WHERE NUMERO_OB = '12345'` (string)                           | Conversao implicita, inibicao de índice | `WHERE NUMERO_OB = 12345` (NUMBER)                |
| `LISTAGG` sem limite                                           | ORA-01489 se resultado > 4000 chars     | `LISTAGG(x, ',' ON OVERFLOW TRUNCATE) WITHIN GROUP (...)` (padrão do acervo, 12.2+); `OPTSTRAGGR*` só em código legado: é função PL/SQL por linha e foi o gargalo removido de `vw_sql_px015.sql` em 20/09/2026 |
| `SELECT *` em OB_FASES                                         | 1.3M x 30+ colunas = overhead           | Selecionar apenas colunas necessarias             |
| `NUMEROORDEMREAL = NUMERO_OB` no código                        | Confusao de nomes                       | `UP_ORDEM_MVTO.NUMEROORDEMREAL = OB.NUMERO_OB`    |
| `OB.SITUACAO = 'A'`, `OB.CODPRO_REDUZIDO`, `FFL.DESCRICAO`     | Colunas inexistentes (ORA-00904)        | `OB.STATUS <> 0`, `OB.CODIGO_REDUZIDO`, `FFL.DESCRICAO_FASE` |
| Somar `OB.TEMPO_* / 1440` à data de 30/12/1899                 | Data de 1930 (época errada), filtros que nunca casam | Usar 01/01/1996 para OB e OB_FASES; 1899 só em UNIDADE_PROGRAMACAO |
| `CRE.PROCESSO_ATIVO_PRODU = 1` ou `= 'S'`                      | Coluna VARCHAR2 '0'/'1': conversão implícita na coluna ou zero linhas | `= '1'` |
| `TRUNC(col)`, `TO_CHAR(col)` ou `TRIM(col)` em `WHERE`/`JOIN`  | Inibe índice                            | Faixa direta na coluna (`col >= :ini AND col < :fim + 1`) |
| `JOIN` interno com tabela que não alimenta nenhuma coluna      | Pode zerar o resultado: em `fia_top_5_producao_diaria_fiacao` a junção com `GRUPO_MAQUINAS` por `GRUPO` zerava a consulta (`LPM_TECELAGEM.GRUPO` é vazio); junção removida em 29/09/2026 | Remover, ou `LEFT JOIN` se for opcional |
| `JOIN` em `GRUPO_MAQUINAS` só por `GRUPO` | A chave é (`SETOR`, `GRUPO`): os grupos 0G020 e 0G021 existem nos setores 4 e 7 e duplicam linhas | Usar `GRM.SETOR = MQ.SETOR AND GRM.GRUPO = MQ.GRUPO` (exemplo: `mal_conferencia_ob_montada_teares_e_lotes_alocados.sql`) |
| Dividir sem `NULLIF(divisor, 0)`                               | ORA-01476 no fim do mês/sem produção    | `x / NULLIF(y, 0)` |
| Aceitar "0 linhas" como conformidade                           | Filtro quebrado escondeu 58 OBs (`qld_ob_s_com_peso_menor_que_8kg`) | Provar com uma variante relaxada que retorne linhas |
| `FETCH FIRST N ROWS ONLY` em consulta de auditoria             | Truncamento silencioso de anomalias     | Devolver tudo, ou avisar o teto no cabeçalho (`Tools/oracle/auditar_acervo_sql.py` marca TETO_ATINGIDO) |
| Supor que `TIPO_ORDEM <> 6` elimina todo reprocesso            | Existem centenas de OBs `TIPO_ORDEM = 0` com peças de OBs anteriores | Rastrear genealogia física via `GERAPECAORIGEMOB` -> `GERAPECADESTINOOB` e `GERAPECAORIGEM` |
| `TIPO_MAQUINA IN (1, 4)` para tingimento                       | Cobre apenas 51 eventos irrelevantes e zera exclusões legítimas | Usar `CODIGO_FASE IN (40, 45, 210)` ou `PI_REC IN (401, 451, 2101, 5001...)` |
| Recursão de genealogia sem `UniversoOrdens` materializado      | Full Hash Join sobre 5,5M linhas estoura Temp e derruba sessão (`ORA-00028`) | Arquitetura em duas fases: expandir ordens com `CYCLE`, materializar e forçar `USE_NL` |
| Usar `DATA_FIM` para desempate da primeira passagem na máquina | `DATA_FIM` é truncada em 00:00:00, gerando empates e distorções | Ordenar por `DATA_HORA_FIM, SEQUENCIA, NUMERO_MAQUINA` |
| Consultar `SGTPRD.OB_EXPEDICAO` ou `QUANT_PROD` em fases       | Objetos/colunas inexistentes no Oracle 12c | Usar `SGTPRD.OB` e `VPF.KILOS` |
| `COUNT(CASE WHEN PADRAO_QUALIDADE_SIN = 1 ...)` em lote de NF | Peças reclassificadas (mov 695) somem do lote, acionando fallback para VOLUMES e gerando saldo fantasma | Contar `COUNT(GPN.IDPECASPRODUTO)` em lotes `STFINALIZACAO = 2`; a origem é `GPN.IDLOTEITENSNFE = LOT.ID` |
| `WHERE GPP.PADRAO_QUALIDADE_SIN = 1` no join de peças de entrada | Peças reclassificadas não entram na classificação física e suas baixas (OB/695) deixam de abater a NF | Trazer todas as peças do lote e classificar a reclassificação na hierarquia física (`TEM_OB -> SALDO -> MOVIMENTOS -> TROCA`) |
| Supor que `/*+ MATERIALIZE */` sempre acelera CTEs             | Pode forçar escrita em TEMP e piorar o plano CBO       | Testar benchmark intercalado sem hints; deixar CBO livre salvo ganho comprovado |
| Calcular "média de médias" ponderadas com `ROUND` intermediário | Distorção decimal cumulativa (0,01 h) em cortes agregados | Transportar `POND_X` e `KG_X_VALIDO` e dividir só no nível final |
| Tratar linha condicional de auditoria como estática            | Linha 94 (FLUXO N/C) só existe quando há anomalia       | Validar presença condicional a ocorrências com emissão de WARN |
| `MAX(...)` independente para atributos físicos correlacionados (largura, gramatura, artigo) | Gera "tuplas artificiais" (quimeras): largura de um lote com gramatura de outro | Usar `MAX(...) KEEP (DENSE_RANK FIRST ORDER BY ...)` com a mesma ordenação em todos os campos da tupla |
| `STATUS_OB <> 0` isolado para definir ordens ativas em produção | Trata OB apenas programada (`EH_PROGRAMADA = 1`) em igualdade com OB no chão de fábrica (`EH_PROGRAMADA = 0`) | Hierarquia estrita: (1) `STATUS_OB <> 0 AND EH_PROGRAMADA = 0`; (2) `STATUS_OB <> 0 AND EH_PROGRAMADA = 1`; (3) `STATUS_OB = 0` |
| `MIN(DT_ENTREGA)` genérico em painel com `PEDIDO` exibido      | Dissocia o prazo de entrega do pedido comercial exibido quando há fatias/componentes distintos | Calcular `DT_ENTREGA_PROMETIDA` com `KEEP (DENSE_RANK FIRST ...)` alinhado à escolha de `PEDIDO` (Regra B) |
| Sessões contínuas longas no Oracle 12.2 sem loop de retry      | Queda de rede/timeout do listener (`ORA-00028` / `DPY-4011` / `DPI-1080` em 4-6s) | Implementar loop de retry (3 a 5 tentativas) reabrindo `oracledb.connect` a cada tentativa com delay de 3s |
| Range contínuo longo (12+ meses) em transacionais massivas (`NOTAFISCALCAPA`) | CBO gera planos instáveis sob concorrência, acumula recursos e dispara `ORA-00028` na 4ª/5ª execução | Decompor temporalmente em ramos disjuntos via `UNION ALL` com `DT_CORTE` na CTE `JANELA` (`[DT_INICIO, DT_CORTE) UNION ALL [DT_CORTE, DT_FIM)`) |
| Múltiplas CTEs varrendo a mesma tabela massiva (`BD_PRD_MOVPROD` 60M+) | Varreduras físicas redundantes de índices/tabela no plano CBO | Criar CTE única pré-agregada no grão mínimo (`DIA + TURNO + FLUXO...`) e agregá-la aditivamente nos consumidores |
| Forçar `/*+ MATERIALIZE */` preventivo em CTE com múltiplos consumidores | Engessa plano CBO sem ganho real; planos com e sem hint são idênticos | Deixar o CBO transformar em `TEMP TABLE TRANSFORMATION` automaticamente; validar sempre com `EXPLAIN PLAN` |
| Várias CTEs de **um consumidor cada** sobre tabelas grandes, unidas por `LEFT JOIN` a um calendário | O CBO funde (merge) as CTEs na consulta principal e escolhe um plano conjunto pior que as partes: em `acb_acumulado_tubular` cada CTE rodava em 0,3-2 s sozinha e o conjunto passava de 6 s (`ORA-00028`) | `/*+ MATERIALIZE */` em cada CTE de fato **é** o remédio aqui (3,0 s medido em 07/10/2026). A regra "não force MATERIALIZE" vale só para CTE com 2+ consumidores |
| Checagem correlacionada por `NUMERO_OB` em `BD_BNF_PRODUCAO_FASE` (`EXISTS`/subquery por linha) | A tabela não tem índice iniciado por `NUMERO_OB` (PK é `NUMEROUP, NUMERO_OB, SEQUENCIA`; índices em `DATA_FIM`/`DATA_HORA_FIM`): cada avaliação varre 1,3M linhas | Montar antes o conjunto pequeno de OBs (CTE materializada) e checar uma vez com `NUMERO_OB IN (SELECT ...)`: `est_posicao_acumulada_estoque_total` caiu de >6 s para 0,9 s |
| Juntar cadastro (`ITENS_ESTOQUE`, `ENGEITEMESTONIVELGE9`, `LIKE`) linha a linha antes de agregar movimentos | O join e o `UPPER(...) LIKE` rodam por peça (12 meses = centenas de milhares de linhas) | Agregar o movimento primeiro por (dia, turno, reduzido, ...) e só então juntar o cadastro: os atributos derivam do reduzido, então é equivalente |
| Usar `OPERADOR`, `PESO_PADRAO` ou `CODIGO_MAQUINA` em `BD_BNF_PRODUCAO_FASE` | Colunas inexistentes (ORA-00904) | Usar `OPERADOR_FINAL` (responsável pelo encerramento), `KILOS` e `NUMERO_MAQUINA` |
| Chave física de partida simplificada como `OB + SEQUENCIA` | Ignora reentradas de OB e reprocessos em UPs distintas | Grão físico mínimo: `TO_CHAR(NUMEROUP) || '|' || TO_CHAR(NUMERO_OB) || '|' || TO_CHAR(SEQUENCIA)` |
| Incluir Fase 40 (Tinturaria) em rankings de operadores | Apontamentos automáticos do usuário técnico `ORGATEX` distorcem métricas | Excluir Fase 40 e filtrar `UPPER(NOME) NOT LIKE '%ORGATEX%'` |
| Duplicar operadores em ranking agrupado por máquina/turno | Mescla conceitos de produção nominal por operador com detalhamento de turnos | Determinar `TURNO_PRINCIPAL` via `MAX(TURNO) KEEP (DENSE_RANK LAST ORDER BY KG_TURNO, TURNO)` |
| `/*+ INLINE */` omitido em CTE de parâmetros consumida por múltiplos ramos | CBO materializa `TEMP TABLE TRANSFORMATION`, perde predicate pushdown nas tabelas massivas, estoura TEMP e gera `ORA-00028` | Inserir hint `/*+ INLINE */` na CTE de parâmetros e forçar `/*+ LEADING(J UPR) USE_NL(UPR) */` nos consumidores de fatos |
| `MAX(DIAS_PRODUTIVOS)` de base agregada por máquina/turno para dias fabris globais | Subestimação silenciosa dos dias de operação da fábrica (ex.: barcas individuais rodaram 27 dias enquanto a fábrica operou 29) | Apurar dias fabris em CTE global dedicada no grão puro de data civil (`COUNT(DISTINCT TRUNC(DATA))`) sem atributos particionadores |
| `NVL(DESTINO_RECEITA, 1)` presumindo nulos sem auditoria empírica | Assume implicitamente dados nulos inexistentes ou mascara a regra cadastral do ERP | Auditar empiricamente no banco: em tingimento, `DESTINO_RECEITA` 0/nulo totaliza dezenas de milhares de kg históricos e pertence à produção normal via `NVL(GDX.TIPO_DESTINO, 0) = 0` |
| Assumir relação 1:1 entre `UNIDADE_PROGRAMACAO` e `UP_ORDEM_MVTO` no tingimento | Uma única UP (partida em barca) pode agrupar até 15 ordens (OBs) simultaneamente (`MAX_OBS_POR_UP = 15`) | Agregar volume no grão de `OB_FASES` (`STATUS = 4`), que possui relação comprovada de 1:1 com `UP_ORDEM_MVTO` para evitar multiplicação de kg |
| Exigir `DESTINO_RECEITA = 1` estrito para produção normal de tingimento | Exclui apontamentos operacionais com `DESTINO_RECEITA = 0` ou nulo (ex.: 951 kg em Out/2021, 1.489 kg em Mar/2020) que pertencem ao fechamento oficial | Classificar via `NVL(GDX.TIPO_DESTINO, 0) = 0` através do join com `DESTINO` e `GRUPO_DESTINO` |
| Filtrar `GRUPO_DEFEITO IN ('1', '3', '4')` em relatórios consolidados globais de fechamento de tingimento | Restringe o escopo a KPIs específicos de auditoria da qualidade interna e omite outros defeitos (ex.: 2, 6, 7, 8 e nulos), divergindo do fechamento corporativo | Fechamento global de tingimento apura a totalidade de reprocessos via `NVL(GDX.TIPO_DESTINO, 0) = 1` sem restrição em `GRUPO_DEFEITO` |
| Exportar rótulos formatados em texto ("Outubro de 2025", "1.500 kg", "2,07%") em queries analíticas | Inibe relacionamentos temporais e ordenações cronológicas corretas em ferramentas de BI (Power BI / Power Query / DAX) | Expor `DATA_MES` como `DATE` truncado (`TRUNC(..., 'MM')`) e valores numéricos puros em maiúsculas sem aspas, delegando a formatação visual à camada do relatório |
| Rótulo informal manual em vez do cadastro oficial (`MOTIVOS_PARADAS`) | Divergência entre nomenclaturas do relatório e o cadastro do ERP (ex.: "Planejamento" vs "AJUSTE DE PLANEJAMENTO") | Fazer join com `SGTPRD.MOTIVOS_PARADAS` pela chave `(SETOR, CODIGO_PARADA)` (cardinalidade 1:1 comprovada) e usar `DESCRICAO_PARADA` oficial |
| Decomposição de volume sem método Shapley balanceado | Resíduo de interação ($\Delta D \cdot \Delta R$) alocado arbitrariamente, distorcendo atribuição executiva | Aplicar Decomposição Shapley: $(\Delta D \cdot \bar{R}) + (\Delta R \cdot \bar{D}) = \Delta KG$, reconciliando 100% da variação com resíduo zero |
