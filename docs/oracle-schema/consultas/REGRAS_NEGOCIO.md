# Regras de negócio do acervo SQL — verificadas no Oracle SGTPRD

Cada regra abaixo foi conferida no Oracle em **29/09/2026**, com a consulta ou a contagem que a prova. Quando uma consulta do acervo diverge de uma regra, a divergência está na seção final, com a decisão tomada ou a pergunta em aberto. Se um valor mudar no ERP, refaça a conferência antes de confiar neste texto.

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

`1`, `2` e `3` são ordens ativas (45, 9 e 87 ordens); `0` é encerrada (15.480). É outra tabela: as consultas de malharia com `O.STATUS IN (1, 2, 3)` **não** usam `OB.STATUS`.

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

### Em aberto (decisão da área)

1. **`fia_top_5_producao_diaria_fiacao`**: a soma diária da LPM (~34 mil/dia, 84 linhas fixas) não bate com `BD_PRD_MOVPROD` (10 a 58 mil kg/dia). `PRODUCAO_MTROS_TURNO` parece apontamento de máquina, não kg produzidos. Além disso, 01/10/2024 lidera o TOP 5 por uma única linha de 354.451.
2. **`bnf_tingimento_confirmado_por_processo_corante`**: os químicos 54 e 14381 são uma sonda pontual (últimos usos em 04/2024 e 06/2023).
3. **`qtd_ajustes_cor`** de `bnf_monitoramento_previsao_vs_realizado_tingimento`: coluna morta (depende de `SEQUENCIA_AJUSTE`).
4. **Custo por kg de químico**: não há fonte de custo validada; a consulta de preço existente compara com preço de venda.
5. **Vazios explicados** (`Tools/oracle/auditar_acervo_sql.py`): `est_pecas_com_status_normal` retorna 0 linhas e está certo (confirmado pela área: não há peça em status Normal nos depósitos 100/110/111). `bnf_primeiro_uso_receitas_tingimento` (cor 00004 + EP 40) e `bnf_receitas_abertas_hidroextracao` (cliente 3111 + cor 10325) são sondas com literal fixo: o cliente 3111 não tem OB desde a 102.702. Os defeituosos já foram corrigidos (`qld_ob_s_com_peso_menor_que_8kg`, `fia_top_5_producao_diaria_fiacao`). Sem revisão ainda: `mal_consulta_pecas_com_restricao_geradas_na_malharia_ultimos_60d`, `fia_pecas_no_estoque_que_foram_usados_fio_com_residuo`, `qld_conferencia_tubetes_plasticos_romaneio`, `com_precos_carteira_pedidos_abertos` e `fac_desenho_estamparia`.
6. **Tetos de linhas (`FETCH FIRST`)**: removidos em 5 consultas com menos de 1.000 linhas; seguem com teto, truncando, `bnf_up_ordem_mvto_por_tipo_maquina` (1,6 milhão de linhas), `com_liga_romaneio_na_nota_fiscal` (232 mil), `com_acondicionamento_*` (~19,5 mil), `eng_custo_real_materia_prima_fechamento_mensal` (6.220 contra teto de 500), `com_obs_e_romaneios_historico_completo` (3.775), `qld_ob_s_com_peso_20...` (2.107), `com_pecas_destino_ob_romaneio` e `com_rastreabilidade_ob_romaneio_nfe` (2.947).

7. **Views `VW_ESP_OB_PED_ROM`** (pasta 11; conferido nas variantes `_ajuste`, `_com_prefixo` e `_sgtprd`): `NM_USU_LIBERACAO` recebe exatamente a mesma expressão de `NM_USU_BLOQUEIO` (`CODREDUSU_BLOQUEIO`), e essas views não têm coluna de usuário de liberação. O campo "liberação" é, portanto, sempre igual ao de bloqueio. É achado do DDL de referência do ERP; nada foi alterado.
