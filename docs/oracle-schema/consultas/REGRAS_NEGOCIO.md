# Regras de negócio do acervo SQL — verificadas no Oracle SGTPRD

Cada regra abaixo foi conferida no Oracle com a data indicada: as seções 1 a 3 em **29/09/2026**, exceto o status de malharia da seção 1 (reconferido em **08/10/2026**) e o resultado histórico da seção 3 (**01/10/2026**); a seção 4 não tem data única, pois traz medições de **29/09/2026** e de **08/10/2026**, indicadas nos itens que as datam; e a seção 5 entre **07/10/2026 e 09/10/2026**, com a consulta ou a contagem que a prova (cada item traz a data da sua medição). Quando uma consulta do acervo diverge de uma regra, a divergência está na seção 4, com a decisão tomada ou a pergunta em aberto. Se um valor mudar no ERP, refaça a conferência antes de confiar neste texto.

## 1. Status

### `OB.STATUS`

| Código | Significado | OBs em 29/09 |
|---:|---|---:|
| 0 | Encerrada | 178.269 |
| 1 | Emitida | 381 |
| 3 | Programada (ainda sem emissão) | 286 |
| 5 | Interditada Kanban | 1 |

O código 2 (Pré OB) existe no cadastro, mas não há OB com ele. **OB aberta = `STATUS <> 0`** (693 OBs na conferência; cerca de 20 consultas do acervo usam esta forma).

### `OB_FASES.STATUS`

| Código | Significado | Fases em 29/09 |
|---:|---|---:|
| 0 | Programada | 4.650 |
| 1 | Emitida | 381 |
| 2 | Pesada | 24 |
| 3 | Em execução | 40 |
| 4 | Confirmada (concluída) | 1.320.353 |

Os códigos 5 (Cancelada) e 6 (Consumo Estamparia) existem no cadastro, mas não há fase com eles. **Fase pendente = `STATUS <> 4`**; **fase atual** da OB = menor `SEQUENCIA` com status 1, 2 ou 3, ou a última sequência se nenhuma estiver nesse conjunto (definição de `bnf_posicao_atual_obs_em_aberto.sql`).

### `UNIDADE_PROGRAMACAO.STATUS` (UPs de tingimento, `SETOR = 5`, `CODIGOFASE = 40`)

| Código | Significado observado |
|---:|---|
| 0 | Iniciada e concluída |
| 1 | Iniciada, em execução (sem fim confirmado) |
| 2 | Programada com horário, não iniciada |
| 3 | Na fila sem horário (`DTTEMPOINIPROGRAMADO` = 30/12/1899), não iniciada |

O significado vem dos dados; o ERP não traz descrição desses códigos nas tabelas consultadas.

### `GERASTPECAPRODUTO.STPECAPRODUTO` (peça)

`0` = Normal, `4` = Utilizada, `8` = Peça origem da OB revisada, `9` = Peças de origem da OB, `12` = Peça estornada, `13` = Reservada para Romaneio de Saída, `14` = Reservada para Pedido de Venda. A tabela completa tem 54 linhas (código × situação de estoque).

### `ORDEM_PRODUCAO_MALHA.STATUS` (malharia)

`1`, `2` e `3` são ordens ativas; `0` é encerrada. Medido em **08/10/2026**, sem filtro de setor (total; setor 4; setor 7): status 0 = 15.505 (15.452; 53); status 1 = 36 (36; 0); status 2 = 9 (9; 0); status 3 = 90 (87; 3). Os valores anteriores do texto (45, 9, 87 e 15.480) não foram reproduzidos e o escopo deles não estava declarado: nesta medição, 45 = 36 + 9 (status 1 e 2), e a origem dos demais não foi identificada. Não use os valores antigos. É outra tabela: as consultas de malharia com `O.STATUS IN (1, 2, 3)` **não** usam `OB.STATUS`.

## 2. Datas e tempos seriais

A unidade depende da tabela. Regra prática: campo `TEMPO_*` de `OB` e `OB_FASES` = **minutos desde 01/01/1996**; campo `TEMPO*` de `UNIDADE_PROGRAMACAO` = **dias desde 30/12/1899**.

| Campo | Conversão | Prova |
|---|---|---|
| `OB.TEMPO_EMISSAO_OB`, `TEMPO_INICIO_PRODUCA`, `TEMPO_ENCERRAMENTO_O`, `OB_FASES.TEMPO_*` | `valor / 1440` dias somados a 01/01/1996 | OB 189383: `TEMPO_INICIO_PRODUCA` = 16.170.703 → 29/09/2026 15:43, igual à emissão. Com a época de 1899 daria 1930. |
| `UNIDADE_PROGRAMACAO.TEMPOFINAL`, `TEMPOFINALPROGRAMADO`, `TEMPOINI*` | `valor` dias somados a 30/12/1899 | valor 45.536 → 01/09/2024. |
| `DT*` de `UNIDADE_PROGRAMACAO` (`DTTEMPOINICONFIRMADO`, `DTTEMPOFINALCONFIRMA`...) | já é `DATE`; zero vem como 30/12/1899 | — |
| `PARADAS_MAQUINA.DATA_*` | `YYYYMMDD` numérico | — |
| `PARADAS_MAQUINA.HORA_*` | minutos do dia (0 a 1.439) | faixa observada 3 a 1.401 |
| `GERAPECASPRODUTO.DATA_DA_ENTRADA_PECA`, `MOVTO_RECEITA.DATAEMISSAO` | `YYYYMMDD` numérico; 0 = sem data | — |

Para filtrar por janela em campo serial, compare a coluna com um limite calculado no mesmo formato em vez de converter a coluna: assim o índice continua utilizável.

```sql
-- últimos 30 dias em campo de OB (minutos desde 01/01/1996)
WHERE OBF.TEMPO_FINAL_CONFIRMA >= (TRUNC(SYSDATE) - 30 - DATE '1996-01-01') * 1440
  AND OBF.TEMPO_FINAL_CONFIRMA <  (TRUNC(SYSDATE) + 1 - DATE '1996-01-01') * 1440
```

## 3. Chaves e definições

- **Receita de uma fase**: `MOVTO_RECEITA.NUMEROORDEM` / `SEQUENCIAFASEOB` = `OB_FASES.NUMEROORDEMMOVIMENTO` / `SEQUENCIAORDEMMOVIME`. Partida = conjunto de OBs tingidas juntas na mesma carga (mesmo par de chaves). `QUANTIDADEPESADA` está em kg.
- **Receita cadastrada para a fase de tingimento**: processo industrial `CODIGO_FASE * 10 + TIPO_PROCESSO` (40 × 10 + 1 = 401; `TIPO_PROCESSO` é sempre 1), cor `SUBSTR(CADASTRO_RECEITAS.CODCOR, 1, 11)` = `CODIGO_COR_DESENHO`, `ESPECIFICACAO_PRODUT` e `PROCESSO_ESPECIFICO`. Sem o `PROCESSO_ESPECIFICO` todas as 541 fases pendentes casam com uma receita; com ele, 538 — as 3 restantes estão **sem receita ativa**.
- **Receita bloqueada**: `LABRECEITA_BLOQUEADA.BLOQUEIO_RECEITA = 0`.
- **Reprocesso de uma fase de tingimento**: `GRUPO_DESTINO.TIPO_DESTINO = 1` (grupos REPROCESSOS e REPROCESSOS RECLASSIFICAR), via `OB_FASES.DESTINO_RECEITA` → `DESTINO` → `GRUPO_DESTINO`. É a definição do runner (`REPROCESSO`). As fases em `OB_REPROCESSO` (451) e com `SEQUENCIA > 30` (29) são subconjunto (466 no total em 90 dias).
- **Destino da fase** (`OB_FASES.DESTINO_RECEITA` = `SGTPRD.DESTINO`): 1 Produção; 2 Reprocessos fora de cor; 3 Limpeza de máquina; 4 Reprocessos para reclassificação; 10 Consumo. O código 0 aparece em `OB_FASES` (4.937 fases), mas não existe no cadastro `DESTINO`. A consulta de produção do Beneficiamento (`bnf_producao_beneficiamento_detalhado.sql`) filtra `DESTINO_RECEITA IN (0, 1, 2, 4)`, ou seja, exclui 3 (limpeza) e 10 (consumo).
- **Ajuste de cor** (`MOVTO_RECEITA.SEQUENCIA_AJUSTE <> 0`): coluna praticamente sem uso (20 linhas em 1,3 milhão, todas antigas). Não serve como indicador.
- **Paradas de máquina** (`PARADAS_MAQUINA.CODIGO_PARADA`, descrição em `MOTIVOS_PARADAS`, setor 5): `BNF13` limpeza de máquina; `BNF20`/`BNF21` manutenção preventiva e continuação; `BNF25` **ajuste de planejamento** (reserva de agenda do PCP, 707,6 h em 30 dias, não é quebra); `BNF27` inspeção de máquina.
- **OB de `TIPO_ORDEM = 6` e Genealogia contra Dupla Contagem**: o filtro `TIPO_ORDEM <> 6` **não elimina todos os reprocessos**. A auditoria em `SGTPRD` comprovou que existem centenas de OBs com `TIPO_ORDEM = 0` (ditas normais) que consumiram peças de OBs anteriores (`GERAPECAORIGEMOB` -> `GERAPECADESTINOOB`). A hierarquia de cabeçalho `OB.NUMERO_OB_PRINCIPAL` é inativa (100% zerada). Para garantir que o mesmo material físico não seja contabilizado mais de uma vez ou que não traga contaminação de processos anteriores (ex.: tingimento), a rastreabilidade determinística deve ser feita via peça física (`IDPECASPRODUTO` em `GERAPECAORIGEMOB` / `GERAPECADESTINOOB` e linhagem em `GERAPECAORIGEM`).
- **Definição Canônica de Tingimento**: O processo de tingimento têxtil é governado exclusivamente por `CODIGO_FASE IN (40, 45, 210)` ou processo industrial `PI_REC IN (401, 451, 2101, 5001, 5002, 5003, 5004, 5005, 5006)`. O filtro por máquina `TIPO_MAQUINA IN (1, 4)` cobre apenas 51 eventos irrelevantes em todo o histórico e zera as exclusões legítimas.
- **Produção na Rama e Desempate Temporal**: Na tabela `BD_BNF_PRODUCAO_FASE`, a coluna `DATA_FIM` é truncada em `00:00:00`. Para identificar a primeira passagem física válida da OB na Rama (`TIPO_MAQUINA = 6`, `STATUS = 0`, `TIPO_DESTINO = 0`), é mandatório ordenar por `DATA_HORA_FIM, SEQUENCIA, NUMERO_MAQUINA`. A quantidade produzida é dada por `VPF.KILOS` (`QUANT_PROD` não existe nesta tabela).
- **Homologação Histórica do KPI de Rama Crua (acb_rama_producao_mensal_sem_tingimento.sql)**:
  - Ordens candidatas da Rama restritas aos fluxos têxteis de acabamento cru `(204, 302, 304, 305, 409, 412)` e sem o filtro inadequado `TIPO_ORDEM <> 6`.
  - Exclusão de tingimento na própria OB antes da Rama (`SEQUENCIA < VPF.SEQUENCIA`).
  - Exclusão multigeracional de tingimento e de Rama em qualquer nível ancestral via genealogia física em duas fases.
  - Resultado histórico consolidado em 01/10/2026: **2.102 OBs**, **1.698.172,165979 kg**, cobrindo **89 competências mensais** (07/11/2018 a 29/09/2026) com tempo de execução em sub-3s.
- **`OB_PRODUTO.KILOS_PROGRAMADOS`**: carga nominal do lote (600, 1000, 1200...), não peso real. Peso real = `OB_FASES.KILOS_PRODUZIDOS` ou a soma de `GERAPECASPRODUTO.QTLIQUIDA`.

## 4. Divergências encontradas no acervo

### Corrigidas nesta rodada

| Consulta | Problema | Correção e efeito |
|---|---|---|
| `com_consulta_pedidos_atrasados`, `com_obs_e_romaneios_em_aberto`, `com_obs_e_romaneios_historico_completo` | `OB.TEMPO_INICIO_PRODUCA` convertido com a época de 1899 (dava 1930) | Época 1996. Efeito latente: só entra no ramo de fallback (OB sem nenhuma confirmação), que nenhuma das 100 linhas devolvidas exercitava. |
| `qld_ob_s_com_peso_menor_que_8kg` | Filtro de 60 dias com época errada: limite ~66 milhões de minutos contra valores ~16 milhões; **nunca casava** | Época 1996. Passou de 0 para **58 OBs** (o "vazio" escondia anomalias reais). |
| `fia_top_5_producao_diaria_fiacao` | `JOIN` com `GRUPO_MAQUINAS` por `GRUPO`, mas `LPM_TECELAGEM.GRUPO` é vazio nas ~300 mil linhas: retornava 0 sempre | `JOIN` removido (tabela não alimentava nenhuma coluna). Passou de 0 para 5 linhas. Ressalva: a LPM não bate com `BD_PRD_MOVPROD` (ver abaixo). |
| `acb_monitora_felpadeira_quanto_precisa_fazer_para_fechar_o_mes` | Tempo disponível terminava às 00:00 do último dia do mês (o `+ INTERVAL '1' DAY` estava comentado): meta de kg/h inflada, negativa no último dia | Vai até o fim do mês. Em 29/09: 7,6 h → 31,6 h; 14,07 → 3,39 kg/h. Mesmo defeito já corrigido na rama em 1.3.102. |
| `bnf_lavacao_de_maquina_ultimas_lavacoes_feitas` | `DIAS_SEM_LAVAR = MAX(início) - SYSDATE` (sempre negativo) | `SYSDATE - MAX(início)`. MQ03: −28,71 → +28,71. |
| `bnf_tingimento_confirmado_consumo_produtos`, `..._por_processo_corante` | Datas fixas de 2022 | Janelas relativas (30 dias e 3 anos). |
| `bnf_obs_abertas_por_processo_corante` | `STATUS NOT IN (0, 3)` deixava de fora as OBs programadas (status 3) | `STATUS <> 0`, decisão da área (só encerradas ficam de fora). 227 → 569 OBs em 29/09; as 342 novas são todas programadas e nenhuma linha antiga saiu. |
| `com_vendas_lojas_mensal_faturamento`, `com_vendas_lojas_por_pedido` | Filtravam `CD_SUBTIPOPED = 11`, uma campanha única (346 pedidos de 58 lojas, todos até 30/06/2022): vazias desde então. As lojas Costa Rica agora pedem pelo subtipo 1 (e 12), misturadas com a matriz | Loja identificada pelo nome da filial de cobrança (`CR-%`, menos `CR-MATRIZ%` e `CR-TEX%`) e janela de 12 e 3 meses. Conferido: 78 pedidos e 1.290 itens em 12 meses, iguais a uma contagem independente; a consulta por pedido soma igual à mensal nos mesmos meses. |
| `acb_consulta_producao_de_artigos_ramados...`, `acb_entrada_de_nfs_dos_terceirizados...`, `com_vendas_lojas_por_pedido`, felpadeira | Divisão sem proteção contra zero | `NULLIF` no divisor; saída idêntica onde o divisor era diferente de zero. |
| `mal_estoque_por_agulhas_tear`, `mal_conferencia_ob_montada_teares_e_lotes_alocados` | Junção de `GRUPO_MAQUINAS` só por `GRUPO`: os grupos 0G020 e 0G021 existem no setor 4 e no setor 7, e a peça contava duas vezes (a segunda vez com agulhas 0) | Junção por (`SETOR`, `GRUPO`). Efeito medido em 08/10/2026: agulhas, escopo 133, 30 linhas para 21 peças (bucket de agulhas 0: 9 peças e 187,45 kg fantasmas); conferência, OB 190112, 60 para 30 peças e 1.247,22 para 623,61 kg; OB 97199 sem mudança (1.009,51 kg). |

### Em aberto (decisão da área)

1. **`fia_top_5_producao_diaria_fiacao`**: a soma diária da LPM (~34 mil/dia, 84 linhas fixas) não bate com `BD_PRD_MOVPROD` (10 a 58 mil kg/dia). `PRODUCAO_MTROS_TURNO` parece apontamento de máquina, não kg produzidos. Além disso, 01/10/2024 lidera o TOP 5 por uma única linha de 354.451.
2. **`bnf_tingimento_confirmado_por_processo_corante`**: os químicos 54 e 14381 são uma sonda pontual (últimos usos em 04/2024 e 06/2023).
3. **`qtd_ajustes_cor`** de `bnf_monitoramento_previsao_vs_realizado_tingimento`: coluna morta (depende de `SEQUENCIA_AJUSTE`).
4. **Custo por kg de químico**: não há fonte de custo validada; a consulta de preço existente compara com preço de venda.
5. **Vazios explicados** (`Tools/oracle/auditar_acervo_sql.py`): `est_pecas_com_status_normal` retorna 0 linhas e está certo (confirmado pela área: não há peça em status Normal nos depósitos 100/110/111). `bnf_primeiro_uso_receitas_tingimento` (cor 00004 + EP 40) e `bnf_receitas_abertas_hidroextracao` (cliente 3111 + cor 10325) são sondas com literal fixo: o cliente 3111 não tem OB desde a 102.702. Os defeituosos já foram corrigidos (`qld_ob_s_com_peso_menor_que_8kg`, `fia_top_5_producao_diaria_fiacao`). `mal_consulta_pecas_com_restricao_geradas_na_malharia_ultimos_60d` retornava 0 linhas por defeito de consulta, e não por falta de dados: usava `CODIGO_REGISTRO = 2` com `INNER JOIN` em `GERAPECACRU`, que nunca casa, porque o registro 2 não tem `GERAPECACRU`. Corrigida em 08/10/2026: `CODIGO_REGISTRO = 1`, base por ordem de malha, `FINALIDADE NOT IN (1, 8)`, sem teto de 100 linhas e janela de 60 dias. Foto de 08/10/2026: 6.396 linhas em 30 dias e 11.725 em 60 dias (linhas = peças distintas). Sem revisão ainda: `fia_pecas_no_estoque_que_foram_usados_fio_com_residuo`, `qld_conferencia_tubetes_plasticos_romaneio`, `com_precos_carteira_pedidos_abertos` e `fac_desenho_estamparia`.
6. **Tetos de linhas (`FETCH FIRST`)**: removidos em 5 consultas com menos de 1.000 linhas; seguem com teto, truncando, `bnf_up_ordem_mvto_por_tipo_maquina` (1,6 milhão de linhas), `com_liga_romaneio_na_nota_fiscal` (232 mil), `com_acondicionamento_*` (~19,5 mil), `eng_custo_real_materia_prima_fechamento_mensal` (6.220 contra teto de 500), `com_obs_e_romaneios_historico_completo` (3.775), `qld_ob_s_com_peso_20...` (2.107), `com_pecas_destino_ob_romaneio` e `com_rastreabilidade_ob_romaneio_nfe` (2.947).

7. **Views `VW_ESP_OB_PED_ROM`** (pasta 11; conferido nas variantes `_ajuste`, `_com_prefixo` e `_sgtprd`): `NM_USU_LIBERACAO` recebe exatamente a mesma expressão de `NM_USU_BLOQUEIO` (`CODREDUSU_BLOQUEIO`), e essas views não têm coluna de usuário de liberação. O campo "liberação" é, portanto, sempre igual ao de bloqueio. É achado do DDL de referência do ERP; nada foi alterado.
8. **`mal_conferencia_ob_montada_teares_e_lotes_alocados`**: no catálogo, "✅ validada" significa só parse Oracle e smoke de 1 linha (`Tools/oracle/validar_sql_oracle.py`). Não é homologação da regra. A validação de 09/10/2026 (validador 2.2.0) cobre o conteúdo atual do arquivo (sha8 28153e62, igual ao registrado), e o catálogo mostra "validada". Segue pendente a equivalência com o controle legado. Se o SQL mudar, o catálogo volta a mostrar "alterada após validação" até nova validação.
9. **Status 18 no estoque** (`mal_estoque_por_lote_produto`, `mal_estoque_por_tear_maquina`, `mal_estoque_por_agulhas_tear`): contagem correta para peça física (ver seção 5.10). Pergunta de negócio aberta: romaneio de transferência tira a peça do estoque?
10. **Destino 0 e NULO de `OB_FASES.DESTINO_RECEITA`**: o código 0 não existe no cadastro `SGTPRD.DESTINO` (seção 3), e o acervo o trata de duas formas. `mal_obs_lotes_teares_misturados` e `qld_obs_montadas_fora_da_regra_de_separacao` rotulam 0 e NULO como "Sem destino cadastrado". `bnf_maiores_producoes_tingimento` os classifica como Produção Normal (`NVL(GDX.TIPO_DESTINO, 0) = 0`, via `GRUPO_DESTINO`), ou seja, em `QTD_PRODUZIDA`. O cabeçalho de `mal_obs_lotes_teares_misturados.sql` registra "Divergência pendente de decisão", e não há decisão da área registrada. Até a decisão, cada consulta segue a sua própria regra.

## 5. Malharia (teares) — regras verificadas no banco (07/10/2026 a 09/10/2026)

Verificadas por SELECT no SGTPRD em 07/10/2026, 08/10/2026 e 09/10/2026, cada item com a data da sua medição. Quando a regra depende de dado incompleto, o status diz o que é seguro usar.

### 5.1 Escopo e jornada
- **Teares internos**: `MAQUINA.TIPO_MAQUINA IN (145, 146)` com `UNIDADE_FABRIL.EH_FACCAO = 'N'`, pela junção `MAQUINA` → `GRUPO_MAQUINAS` → `UNIDADE_FABRIL`. Em 08/10/2026: 87 máquinas tipo 145 internas no setor 4; 3 máquinas tipo 146, todas no setor 7; o setor 4 tem ainda 15 máquinas de outros tipos (150 e 167), fora do critério. Facção: grupos `0T…` (0T001 a 0T013), máquinas `TCT01` a `TCT13`, `EH_FACCAO = 'S'`. Decisão de negócio pendente: a malharia é só o setor 4 (seção 5.4) ou também o setor 7? Hoje as duas regras se contradizem.
- **Jornada**: `TABELA_PRD_TURNOS` define 3 turnos nas duas filiais (1 e 2, idênticas): T1 05:00–13:29 (8 h 29 min), T2 13:30–21:59 (8 h 29 min) e T3 22:00–04:59 (6 h 59 min). Os intervalos cadastrados somam 23 h 57 min; faltam três transições de 1 min (13:29–13:30, 21:59–22:00 e 04:59–05:00). **Seguro usar 24 h como jornada de operação**, arredondando as transições.
- `CALSEMANATURNO`: INICIO e FIM são data-hora seriais (parte inteira = dia, fração = hora do dia; ex.: INICIO 2,20903 = 05:01 e FIM 2,5625 = 13:30). Os horários diferem de `TABELA_PRD_TURNOS` em 1 minuto. **Não usar** sem confirmação da engenharia.
- Filial 1 e 2 têm os mesmos turnos (`TABELA_PRD_TURNOS`).
- Grupo de máquina: a chave de `GRUPO_MAQUINAS` é (SETOR, GRUPO), não GRUPO (índice único `GRUPOMAQ_IND_GRUPO_MAQUINAS`). Os códigos 0G020 e 0G021 existem nos setores 4 e 7; no setor 7 o número de agulhas é 0. Junção só por GRUPO duplica peças (conferido em 08/10/2026). Usar sempre `GRM.SETOR = MQ.SETOR AND GRM.GRUPO = MQ.GRUPO`.
- Estado da correção de junção, arquivo por arquivo (medido em **08/10/2026**):
  - Aplicada em 5 consultas: `mal_conferencia_ob_montada_teares_e_lotes_alocados.sql`, `mal_estoque_por_agulhas_tear.sql`, `mal_obs_lotes_teares_misturados.sql`, `qld_obs_montadas_fora_da_regra_de_separacao.sql` (estas quatro juntam por SETOR e GRUPO) e `fia_fios_consumos_ficha_tecnica.sql` (ressalva abaixo).
  - `mal_obs_lotes_teares_misturados.sql` e `qld_obs_montadas_fora_da_regra_de_separacao.sql`: a subconsulta de grupos passou de 95 para 87 linhas. A correção do join não mudou a saída (27 e 40 linhas em 08/10/2026). Os rótulos de `TP_ORDEM` mudaram por outra correção: em 08/10/2026, as 27 linhas de `mal_obs_lotes_teares_misturados.sql` saíam como `'Produo'` no HEAD e `'Produção'` na árvore. Em 09/10/2026, HEAD e árvore dão 23 linhas cada, com o mesmo conjunto de OBs, e a única coluna que muda é `TP_ORDEM` (só a grafia); a contagem varia com o dia porque o conjunto depende do status das OBs (`OBE.STATUS <> 0`). A saída de `qld_obs_montadas_fora_da_regra_de_separacao.sql` é byte a byte igual, pois só traz `'Produção'` e `'Reclassificação'`, rótulos que não mudaram. O defeito era latente: os flags `TEARES_SIMILARES` e `REGRA_AGULHAS` poderiam errar se surgisse OB com peças só em TC076, TC077, TC082 ou TC083.
  - Ressalva de `fia_fios_consumos_ficha_tecnica.sql`: a ficha de fio (`FIOS_FICHA_MALHARIA_`) não tem SETOR. Por isso a subconsulta traz uma linha por GRUPO, com as descrições dos setores unidas por ' | ' (ordem de SETOR). A consulta passou de 597 para 554 linhas (43 duplicatas removidas dos grupos 0G020 e 0G021). Para esses dois grupos, `DESCRICAO_GRUPO` traz as descrições dos setores 4 e 7; qual setor vale é decisão de negócio em aberto (seção 5.11).
  - `mal_oee_aproximado_grupo.sql` agrega por GRUPO, sem SETOR, nas CTEs de grupo. Medido: 0G020 tem 5 máquinas (4 no setor 4 e 1 no setor 7) e 0G021 tem 6 (4 e 2). Decisão em aberto, seção 5.11.
  - `mal_agulhas_por_tonelada.sql` junta por (SETOR, GRUPO) e não agrega por grupo.

### 5.2 Produção e pesagem
- `GERAPECASPRODUTO.DATA_DA_ENTRADA_PECA` é a **data da pesagem** (não de produção). Conhecimento de domínio já estabelecido; não é provado só pelos dados do banco.
- Peso líquido: `GERAPECASPRODUTO.QTLIQUIDA`. Conferido com `GERAPECACOMPLPECA.PESO_PECA` nas 163.723 peças de malha de jul–set/2026: diferença média absoluta de 0,003 kg (com sinal, -0,003 kg). **Seguro usar**, exceto as 30 peças com diferença acima de 5 kg (máximo de 20 kg), que devem ser excluídas ou conferidas.
- Vínculo peça → ordem: `GERAPECAORDEMMALHA` (`IDPECASPRODUTO` → `NUMERO_ORDEM_MALHA`). Em jul–set/2026, cada peça aparece uma vez (sem duplicidade de `IDPECASPRODUTO`). A cardinalidade de peças por ordem não foi medida.
- **Máquina por peça**: `GERAPECACRU.NUMERO_MAQUINA` confere com a máquina da ordem em 100% das peças (163.723 peças com ordem de malha, jul–set/2026, de 237.073 peças de GERAPECACRU no período). **Seguro usar** como alternativa à ordem.
- Peça estornada: `STPECAPRODUTO = 12`.
- Status da ordem de malha (`XX2_ENUMITEM`, enum `TESTATUSORDEMMALHA`): 0 encerrada, 1 emitida, 2 programada, 3 iniciada.

### 5.3 Metas e tempos padrão
- Meta diária (`TB_ESP_PROD_TEOR_MAL.KG_DIA_100`) vs. kg/h da ficha × 24: **não reproduzida**. Com a fórmula de `mal_oee_aproximado_grupo.sql` e o valor vigente de cada par produto+grupo, 13 de 74 produtos em comum batem a ±0,01 kg e 45 a ±0,5 kg. O histórico tem 81 produtos (40 na janela de 12 meses); nenhum recorte dá 85. Há desvios de até +19,7% (produto 46, grupo 0G012). A meta muda no tempo: reduzido 152 (grupo 0G014) vai de 266 a 1.012 kg/dia na janela de 12 meses. Definir o método e a janela antes de declarar seguro.
- Uma linha por máquina/dia em `TB_ESP_PROD_TEOR_MAL` na janela de 01/10/2025 a 30/09/2026: 32.418 linhas, 90 máquinas, nenhuma máquina-dia duplicada (no histórico completo há 2 pares repetidos). Chave de negócio: `NR_MAQUINA` + `DT_META`, com `NR_OPM` e `CD_REDUZIDO` como atributos.
- `KG_DIA_EFIC` = `KG_DIA_100` × `FICHA_MALHA.PERCPRODUCAOPREVISTO` / 100 (o campo vem em percentual, 26 a 85). Na janela de 01/10/2025 a 30/09/2026 (32.418 linhas): 1.095 sem ficha; das 31.323 com ficha, 689 divergem em mais de 0,5 kg (97,8% conferem). **Seguro usar** para a meta agregada; para um produto específico, conferir antes.
- Velocidade: a faixa de 99% a 106% **não se sustenta**. Pela junção máquina → grupo → ficha (14.507 ordens de malha com RPM, setor 4), 51,6% ficam dentro da faixa, 30,6% abaixo de 99% e 17,8% acima de 106%. Não usar a faixa como premissa, ou definir a regra de tolerância. O uso prático do RPM da ficha não é verificável pelo banco.
- `MALHPARAMETROSFILIAL`: os parâmetros de eficiência padrão (`PCEFICPADRAESTIMRETI`), tempo de troca de artigo e de peças (`TPPADRAOTROCAARTIGO`, `TPPADRAOTROCAPECAS`) e lubrificação (`QTVOLTASLUBRIFICACAO`, `QTVOLTASLIMPEZA`) estão zerados nas duas filiais. A filial 1 tem outros 13 campos preenchidos (ex.: `STUSAHORADOMICROCIRC` = '1', `PCTOLERACEITSUPERPES` = 10). **Não usar** para eficiência, troca e lubrificação.
- `MALHPARAMETROSGERAL` (tempos de troca de **circular**): agulha 30, fio 30, ponto 15, finura 240, entre circular 40 e troca de ordem 60 (`TPTROCAORDEMCIRCULA`; unidade 'min' não consta no dicionário). **Seguro usar como referência**, com ressalva: o motivo configurado para troca de artigo circular (`CDMOTIPARADATROCACIR`) é **MLC08** (REGULAGEM DE MÁQUINA/AMOSTRA, 30 min), e não MLC15 (TROCA DE ARTIGO, 390 min). Confirmar com a engenharia qual é o tempo oficial de troca de artigo.
- `MOTIVOS_PARADAS.TEMPO_PADRAO_PARADA` por código (setor 4): MLC02 390, MLC04 30, MLC07 90, MLC15 390, MLC16 40, MLC23 15, MLC31 10, MLC39 10 etc. **Seguro usar como referência de tempo padrão**.
- `MOTIVOS_PARADAS.CALCULA_EFICIENCIA = '1'` para todos os códigos MLC01–MLC43, exceto MLC18, MLC19, MLC26, MLC27 e MLC28 (valor `'0'`). Esses cinco não entram na perda de eficiência.

### 5.4 Paradas
- `PARADAS_MAQUINA`: `DATA_*` em `YYYYMMDD` numérico; `HORA_*` em minutos do dia. Setor da malharia = 4.
- `NUMEROORDEMMANUTENCA` e `OBSERVACAO` estão zerados em todas as paradas de malharia (99.335 registros). **Não há vínculo com ordem de manutenção**: das 8.475 ordens de manutenção de máquinas do setor 4, nenhuma tem `NUMERO_PARADA_MAQUIN` preenchido (no cadastro inteiro são 150 com esse campo). **Não usar** para tempo de reparo.
- `LOTE_FIO_PRODUTO` e `GRUPO_PRODUTO` estão vazios/zerados nas paradas de malharia. **Não usar** para causa por lote ou produto.
- `CODIGO_OPERADOR`: em 2026, 5 códigos; um deles aparece em 56% dos registros (valor padrão). No histórico completo do setor 4 são 17 códigos e o principal cai para 46%. **Não usar** para análise por operador.
- **Lote de início de turno (MLC07)**: em 2025 (ano-calendário), 44 dias têm MLC07 em 80 ou mais máquinas do setor 4, pela data de início da parada (3.712 registros de máquina-dia, média de 58,5 min por registro, soma de 217.196 min). Em 2026, até 08/10, são 34 dias com o mesmo critério. Medido em 09/10/2026; com o filtro de teares internos o número não muda. Nenhuma consulta do acervo calcula esse critério. `mal_qualidade_registro_paradas.sql` (teste `LOTE_INICIO_TURNO`) usa 80% das máquinas internas (0,8 × 90 = 72 teares, sem filtro de setor no denominador) numa janela móvel de 12 meses (01/10/2025 a 30/09/2026); em 09/10/2026 ela também devolve 44 dias, mas é outra janela e outro critério. **Tratar como lançamento em lote**, não como parada operacional diária.
- Paradas não começam majoritariamente nas trocas de turno: só 6% a 24% dos códigos (setor 4, histórico: MLC02 24,2%, MLC04 13,1%, MLC12 17,3%, MLC14 6,2%, MLC23 10,8%) iniciam exatamente às 05:00, 13:30 ou 22:00.

### 5.5 Agulhas
- `QUEBRA_AGULHA_MALHAR`: `DATA_QUEBRA` em `YYYYMMDD`. `QUANTIDADE_AGULHAS` por registro.
- `COD_AGULHA` é a chave de `AGULHAS.CODIGO_AGULHA` (cadastro com `DESCRICAO` e `PE_AGULHA`). Medido em **08/10/2026**: 144 dos 153 códigos distintos de `QUEBRA_AGULHA_MALHAR` existem no cadastro, e 132 linhas do histórico completo não casam. Na janela de 12 meses de `mal_agulhas_por_tonelada.sql` não há linha sem cadastro. O significado de `PE_AGULHA` não está no dicionário (na amostra aparecem os valores 1 e 2).
- `COD_QUEBRA` é constante (`MLC39`, 100% dos registros de 2026). **Não usar**.
- `OPERADOR` padrão em 96% dos registros (96,4% em 2026); `TURNO` padrão (3) em 97% (97,2% em 2026). **Não usar** para análise por operador ou turno.
- Mudança de registro: a média de agulhas por registro foi 7,6 em 2025 e 14,8 em 2026 (até 08/10), e os registros caíram cerca de 60% de janeiro a setembro (11.603 em 2025 para 4.562 em 2026). Comparar anos com cautela.

### 5.6 Qualidade e refugo (malharia)
- `OB_QUALIDADE` (25.793 registros em 08/10/2026) registra não conformidade **por OB de beneficiamento** (`NUMERO_OB`). Nenhum número bate com ordem de malha. **Não serve para refugo de malha**.
- `GRUPO_DEFEITO_QUALID`: grupos de malharia no setor 4 são `MALHARIA` (código 2), `MALHARIA (FACÇÃO)` (6) e `MALHARIA (RESTRIÇÕES)` (8); `MALHARIA RETILÍNEA` (5) está no setor 13. Não foi encontrada tabela de registro de defeito por peça de malha preenchida. **Investigar antes de usar**.
- Em `GERAPECACOMPLPECA`, para peças de malha (jul–set/2026): `PECA_DE_REPROCESSO` = 0 em 100%, `QTPESOCONSUMOQUEBRA` = 0, `PERC_UMIDADE_MALHA` = 0, `PECA_REPESADA` = '0' em todas, e em `GERAPECACRU`: `PECA_MARCADA_REVISAO` = '0' e `TEMPO_REVISAO` = 0. **Esses campos não são usados para malha. Não usar para refugo nem qualidade.**
- Valor `'1'` em `PECA_DE_REPROCESSO` existe (3.238 peças de jul–set/2026 pela data de pesagem), mas em peças de outros setores, não de malha.
- Convenção de flags: `'1'` = sim, `'0'` = não, nulo = não informado. Não usar `'S'`/`'N'`.

### 5.7 Resumo do que é seguro implementar
| Indicador | Status | Base |
|---|---|---|
| Jornada 24 h (3 turnos, 23 h 57 min cadastrados) | Seguro | `TABELA_PRD_TURNOS` |
| Teórico kg/h e meta | **Não reproduzido** (método a definir; ver seção 5.3) | `FICHA_MALHA`, `FIOS_FICHA_MALHARIA_`, `TB_ESP_PROD_TEOR_MAL` |
| Desempenho × qualidade nos dias produtivos (`mal_oee_aproximado_grupo`) | Usar com a leitura da coluna: **não é OEE** (sem disponibilidade real; Q = 100%). A coluna A (informativa) inclui o MLC07 e não tem versão sem ele; a P não usa paradas. Validada no Oracle em 09/10/2026 (parse + smoke de 1 linha, após 5 tentativas por quedas de rede; ver `validacao_status.json`) | `DIA_MAQ`, `TEO_DIA`, `PRODUCAO_GRUPO` |
| OEE completo | **Não calculável** com os dados atuais (falta horas programadas por máquina; máquina sem pedido não é parada) | — |
| Desempenho (realizado ÷ teórico, dias com 1 produto) | **Não validado como % absoluto**: usar para comparar grupos (nota abaixo) | `mal_oee_aproximado_grupo.sql` |
| Máquina por peça | Seguro | `GERAPECACRU.NUMERO_MAQUINA` |
| Tempo padrão por parada | Seguro como referência | `MOTIVOS_PARADAS.TEMPO_PADRAO_PARADA` |
| Tempo padrão de troca (circular) | Seguro com ressalva | `MALHPARAMETROSGERAL` |
| Pareto de paradas e corretiva (frequência e duração das paradas) | Seguro com cautela: o MLC07 (início de turno, lote; seção 5.4) é o primeiro do ranking, com 20,1% dos minutos, praticamente empatado com o MLC04 (19,8%). Ele entra sem exclusão em `MINUTOS` e `RANK`; o cabeçalho de `mal_pareto_paradas_internas.sql` o sinaliza, mas a consulta não o separa, e `EVT_CURTAS` não ajuda, pois esse código não tem paradas de até 15 min (222.946 min em 3.770 eventos, medido em 09/10/2026, janela 01/10/2025 a 30/09/2026). Para priorizar manutenção, excluir o MLC07 do ranking ou usar `mal_paradas_categoria_mes.sql`, que o separa em categoria própria | `PARADAS_MAQUINA`, `mal_pareto_paradas_internas.sql` |
| Agulhas por tonelada | Seguro com cautela de registro (totais conferidos, nota abaixo) | `QUEBRA_AGULHA_MALHAR`, pesagem; `mal_agulhas_por_tonelada.sql` |
| Proxy de tempo parado (1 − paradas ÷ 24 h de calendário, setor 4) | **Não é disponibilidade**: parada registrada não distingue máquina parada de máquina sem pedido; usar só como proxy. `DISPONIBILIDADE_PCT` inclui o MLC07 (lote de início de turno, seção 5.4); `DISPONIBILIDADE_SEM_INICIO_PCT` exclui e deve ser lida junto, como sensibilidade (`mal_disponibilidade_por_maquina.sql`) | `TABELA_PRD_TURNOS`, `PARADAS_MAQUINA` |
| Eficiência padrão da filial | **Não usar** (zerado) | `MALHPARAMETROSFILIAL` |
| Refugo, reprocesso, quebra em kg | **Não usar** (não registrado para malha) | `GERAPECACOMPLPECA` |
| Causa por lote de fio / produto | **Não usar** (vazio) | `PARADAS_MAQUINA` |
| Análise por operador / turno real | **Não usar** (padrão) | `PARADAS_MAQUINA`, `QUEBRA_AGULHA_MALHAR` |
| Tempo de reparo real e MTTR | **Não usar** (sem vínculo OM) | `PARADAS_MAQUINA`, `ORDEMMANUTENCAO` |

**Notas de verificação (08/10/2026 e 09/10/2026):**

- *Desempenho*: o P usa só máquina-dia com um produto (`NRED = 1`) e com teórico não nulo. Medido em 09/10/2026, na janela de 12 meses (01/10/2025 a 30/09/2026), somando os trimestres: 90 teares internos; kg real de todas as máquina-dia (coluna `KG_REAL` da consulta) 12.272.334 kg (25.792 máquina-dia); com `NRED = 1`, 12.107.220 kg (25.475); com `NRED = 1` e teórico não nulo, a base de P, 11.843.966 kg (24.100). Em 08/10/2026, o percentual por grupo ia de 43,9% a 76,5%, com estorno zero (Q = 100%); essa faixa não foi refeita em 09/10. O teórico é a fórmula de ficha (kg/h a 100% × 24 h), a mesma que a seção 5.3 mostrou não bater com a meta da engenharia. Por isso o percentual absoluto não é seguro; serve para comparar grupos entre si.
- *Agulhas por tonelada*: AGULHAS somam 91.282, igual ao total de quebras da janela (todas de teares internos). KG soma 12.272.339 contra 12.272.334 da base por ordem (diferença de arredondamento por máquina). Não há peça duplicada em `GERAPECAORDEMMALHA` nem máquina ou ordem duplicada. Continua valendo a cautela de registro de 2026 (seção 5.5).

### 5.8 Peças de reagrupamento (filhas de linhagem sem ordem de malha)
Investigadas em setembro/2026, em teares internos, peças não estornadas. Resultado:
- **458 peças** (7.317 kg, cerca de 0,65% do kg do mês) estão em `GERAPECACRU` (máquina interna), **não têm** `GERAPECAORDEMMALHA`, e **têm** `GERAPECAORIGEM` (linhagem de outra peça).
- São **filhas**: cada uma tem de 1 a 7 peças-mãe (média de 2,6). As mães são peças de ordem de malha, em 1.000 dos 1.176 vínculos, na mesma máquina em 753 deles.
- **Peso conservado**: em 414 das 458, o peso da filha é igual à soma das mães (±0,5 kg). Ou seja, é um reagrupamento físico, não produção nova.
- Todas têm movimento de geração (`GERAPECAMOVIMENTO.TIGERACAO = '1'`), o mesmo tipo das peças de malha normais, e 268 estão em `GERAPECAROMATRAN` (romaneio de transferência). Nenhuma em romaneio de saída (o recorte "para venda" não foi conferido no banco: não há tabela de pedido ligada).
- Status das filhas (enumerado `TSTATUSPECAPRODUTO`): 256 com 18 = "Reservada p/ Romaneio Transfer"; 130 com 4 = "Utilizada"; 51 com 8 = "Origem da OB já revisada"; 21 com 0 = "Normal". Nenhuma com 13 ou 14.
- **Decisão:** a base de produção deve continuar sendo **a peça com ordem de malha** (`GERAPECAORDEMMALHA` → `ORDEM_PRODUCAO_MALHA`). Ela exclui as filhas automaticamente. Medido em **08/10/2026** (set/2026, pela data de pesagem, teares internos, peças não estornadas): as 458 filhas somam 7.316,96 kg, exatamente a diferença entre a base por `GERAPECACRU` (56.321 peças, 1.122.980 kg) e a base por ordem de malha (55.863 peças, 1.115.663 kg). Nenhum total de equivalência foi encontrado no acervo para conferir este resultado. Partir de `GERAPECACRU` **dobraria** o peso das filhas, a menos que se exclua quem tem linhagem e não tem ordem.
- Se for preciso mostrar o transporte de reagrupamento como indicador, usar essas 458 peças separadamente, nunca somadas à produção.

### 5.9 Status de peça relevantes para malharia (cadastro `TSTATUSPECAPRODUTO`)
0 Normal · 4 Utilizada · 7 Revisada · 8 Origem da OB já revisada · 12 Peça Estornada · 13 Reservada p/ Romaneio Saída · 14 Reservada p/ Pedido Venda · 17 Emendada · 18 Reservada p/ Romaneio Transfer · 43 Em processo na Malharia pela OPM · 42 Reservada para OPM.

### 5.10 Estoque de malha por status (depósito 95)

Foto do momento, medida no Oracle em 08/10/2026. O depósito muda a todo instante: os números não são fixos.

- Cadastro (`GERASTPECAPRODUTO`): 0 Normal (situação 0); 16 Alocada Inventario (situação 1); 18 Reserva p/ Romaneio Transfer (situação 1).
- Escopo reduzido 11852, depósito 95: 1.334 peças com status 0 e 27.307,8 kg na primeira medição; 1.326 peças e 27.142,0 kg em nova medição, minutos depois. Status 4 (Utilizada): 35 peças. Zero peças com status 16 ou 18.
- Escopo reduzido 133, depósito 95: 21 peças distintas, todas com status 0 e com ordem de malha. Zero peças com status 16 ou 18.
- Depósito 95, histórico inteiro (com `CODIGO_REGISTRO = 1`): zero peças com status 16 ou 18.
- Depósito 90, desde 01/09/2026, status 18: 317 peças com ordem (6.524,5 kg), 276 filhas sem ordem e com linhagem (5.455,3 kg) e 33 sem ordem e sem linhagem (707,1 kg, não explicadas pela seção 5.8).
- Mães das 276 filhas de status 18 (depósito 90, desde 01/09/2026): todas com status 4 (Utilizada), no mesmo reduzido.

### 5.11 Decisões de negócio em aberto (dono: área/engenharia)

- **Romaneio de transferência (status 18)**: a reserva tira a peça do estoque? A resposta muda os três `mal_estoque_por_*` citados na seção 4 (ver seção 5.10).
- **Meta de eficiência da malharia**: `mal_eficiencia_ordens_em_aberto` usa o fator fixo de 68% (`KG_HORA_EFIC`, malha e retilínea). A meta deve ser esse 68% ou o percentual do produto (seção 5.3)?
- **FICHA_RETILINEA na meta**: produtos de `FICHA_RETILINEA` (14 linhas) devem entrar na meta de `mal_eficiencia_teorico_vs_realizado`? Hoje ficam fora do comparado, porque a CTE `TEO` usa só `FICHA_MALHA`.
- **FINALIDADE 8**: o cadastro `TIPO_FINALIDADE_FIO` a descreve como "FIO C/ RESÍDUO", e o acervo a trata como sem restrição (`FINALIDADE IN (1, 8)`). A escolha muda o resultado só quando há peça com FINALIDADE 8 no escopo da consulta. Na revisão de 08/10/2026, nenhuma peça com ordem de malha tem FINALIDADE 8 nas janelas de 30 e 60 dias de `mal_consulta_pecas_com_restricao_geradas_na_malharia_ultimos_60d.sql` (a diferença cresce a partir de 90 dias). Em 09/10/2026, zero peças com FINALIDADE 8 nos escopos das três `mal_estoque_*`, que não têm janela.
- **OBs fora da demanda**: 58 OBs (39.076,00 kg) saem da demanda de `mal_necessidade_*` pelo filtro de `TIPOPEDIDO` (2 ou 3) ou de cliente terminado em T, S ou R. Esse corte é intencional?
- **Peças internas sem ordem de malha e não estornadas**: ficam fora da base de produção (seção 5.8). Confirmar se a exclusão é intencional.
- **Setores 4 e 7 dos grupos 0G020 e 0G021**: os dois grupos existem nos dois setores (o setor 7 tem 3 teares internos, tipo 146, com 0 agulhas no cadastro de grupo). Agregados por GRUPO sem SETOR misturam os setores em `mal_oee_aproximado_grupo.sql`. Em `fia_fios_consumos_ficha_tecnica.sql` a junção já não duplica linhas, mas `DESCRICAO_GRUPO` une as descrições dos setores 4 e 7 (seção 5.1). Decidir se o agregado é por (SETOR, GRUPO) e se o setor 7 entra na malharia (decisão de escopo da seção 5.1).
