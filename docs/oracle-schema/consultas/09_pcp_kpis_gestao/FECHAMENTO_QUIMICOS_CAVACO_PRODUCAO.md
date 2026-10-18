# Fechamento de produção, produtos químicos e cavaco

Consultas entregues (mesma lógica, período diferente):

- `pcp_fechamento_quinzena_quimicos_cavaco_producao.sql`: dias 01 a 15 do mês de `:MES_REF`.
- `pcp_fechamento_mensal_quimicos_cavaco_producao.sql`: dia 01 ao último dia do mês de `:MES_REF`.

Parâmetro: `:MES_REF = 'YYYY-MM'`. Testadas em 17/10/2026 com o Oracle de produção (somente leitura).

## 1. Fontes confirmadas

| Indicador | Fonte | Regra |
|---|---|---|
| Abertura (quantidade e valor) | `FECHAMENTO_ESTOQUE_A` + `FECHAMENTO_VALOR` do mês anterior | `SALDO_ATUAL - QUANTIDADE_BLOQUEADA` e `VLFINAL` (unitário), `TIPO_VALORIZACAO = 0`, `OPCAO_MOEDA = 0` |
| Movimentos | `GERAMOVIMENTOESTOQUE` | `STMOVIMENTO = 0`, `STGERAESTOBLOQ = 0`, `NRTIPOMOVIMENTO <> 999`; `TIOPERACAO` 1 = entrada, 2 = saída |
| Valor de entrada | `MOVIMENTACAO_VALOR.VLMOVIMENTO` (unitário) | `QTMOVIMENTO x VLMOVIMENTO`, por `NUMERO_MOVIMENTO = ID` |
| Custo da saída | Custo médio do período | `(valor inicial + valor das entradas) / (qtd inicial + qtd entradas)` |
| Classificação | `ITENS_ESTOQUE` + `ENGEITEMESTOCLASSE` | Cavaco = `TRIM(CODIGO) = 'CAV0001'` (item 1806). Químicos por `CDSUBGRUPO`: 01 Corante, 02 Auxiliares, 04 Acabamento, 05 ETA/ETE, 07 Commodities |
| Produção | `BD_BNF_PRODUCAO_FASE` por `DATA_FIM` | Ramado = Total Embalado = `KILOS` da fase 150; Tingimento = fase 40 |
| Dias de produção | `MOVIMENTO_MAQUINA` (máquinas da fase 150 no período) | União dos intervalos `TEMPO_INICIAL`–`TEMPO_FINAL`, em dias |

Na classificação, `ITENS_ESTOQUE.CODIGO` é `CHAR(50)` com espaços à direita. Por isso o `TRIM` é obrigatório.

## 2. Validações

### 2.1 Fechamento de setembro/2026 (reconstrução do próprio ERP)

Mês de referência `2026-09`, abertura = fechamento de agosto.

| Categoria | Qtd final calculada | Qtd fechamento set/2026 | Valor final calculado | Valor fechamento set/2026 |
|---|---|---|---|---|
| Cavaco | 2.592 | 2.592 | 224.282,59 | 224.282,59 |
| ETA/ETE | 27.138,01 | 27.138,01 | 69.604,19 | 69.604,19 |
| Acabamento | 10.242,97 | 10.242,97 | 64.975,50 | 64.975,50 |
| Commodities | 32.627,18 | 32.627,18 | 77.001,15 | 77.001,15 |
| Auxiliares | 117.752,07 | 117.752,07 | 300.508,43 | 300.508,43 |

Nota do corante: após a correção do saldo bloqueado, nenhum item do subgrupo 01 listado em `AR_ESTOQUE_QUIMICO` apresenta diferença entre o fechamento de set/2026 e a reconstrução. A consulta classifica 91 itens como corante e a view lista 88; a diferença de 399,85 kg (98.976,10 contra 98.576,25 de saldo do fechamento) vem desses itens fora da view. Não foi conferido o valor de corante contra o fechamento com a junção corrigida, por isso ele não entra na tabela.

O total de entradas e saídas do cavaco também fecha: entradas 7.550 e saídas 7.358, iguais ao fechamento.

### 2.2 Quinzena de outubro/2026 contra a referência

| Indicador | Referência | Consulta | Diferença | Situação |
|---|---|---|---|---|
| Ramado (kg) | 703.520,97 | 703.520,97 | 0 | Reproduzido |
| Total Embalado (kg) | 703.520,97 | 703.520,97 | 0 | Reproduzido |
| Dias de Produção | 11,979167 | 11,593750 | -0,385417 (cerca de 9h15) | Aproximado, não reproduzido |
| Químicos ETA/ETE: estoque inicial | 69.604,19 | 69.604,19 | 0 | Reproduzido |
| Químicos ETA/ETE: compras | 58.551,50 | 58.561,50 | +10,00 | Quase igual |
| Químicos ETA/ETE: estoque final | 49.979,45 | 128.165,69 | +78.186,24 | Não reproduzido |
| Químicos ETA/ETE: consumo | 78.176,24 | 0,00 | -78.176,24 | Não reproduzido |
| Cavaco: qtd inicial | 2.592,00 | 2.592,00 | 0 | Reproduzido |
| Cavaco: qtd comprada | 3.400,00 | 3.714,00 | +314,00 | Não reproduzido (ver 3.1) |
| Cavaco: qtd final | 2.500,00 | 4.066,00 | +1.566,00 | Não reproduzido (ver 3.2) |
| Cavaco: qtd consumida | 3.492,00 | 2.240,00 | -1.252,00 | Não reproduzido (ver 3.2) |
| Cavaco: valor inicial | 224.282,59 | 224.282,59 | 0 | Reproduzido |
| Cavaco: valor compras | 295.180,00 | 322.410,00 | +27.230,00 | Ver 3.1 |
| Cavaco: valor final | 216.731,72 | 352.497,95 | +135.766,23 | Ver 3.2 |
| Cavaco: custo unitário final | 86,69 | 86,694 | 0,004 | Reproduzido |
| Cavaco: consumo por kg (R$) | 0,4303 | 0,2760 | | Depende do valor final |
| Cavaco: qtd consumida por dia | 291,51 | 193,21 | | Usa qtd consumida registrada e dias acima |

## 3. Pendências (não comprovadas com os dados do banco)

**3.1 Compras de cavaco (+314 unidades, +R$ 27.230,00).** A referência bate exatamente se excluirmos duas entradas de 15/10/2026: IDs 123349502 (134 unid. a R$ 85,00) e 123349503 (180 unid. a R$ 88,00). Não há regra visível no banco que as separe das demais entradas do dia. A hipótese mais provável é lançamento posterior à extração da referência. Não foi aplicada nenhuma exclusão fixa, porque não há critério comprovado.

**3.2 Estoque final e consumo de cavaco e ETA/ETE.** A referência calcula o consumo como inicial + compras − final, e o final (2.500 unid. de cavaco e R$ 49.979,45 de ETA/ETE) não existe em nenhuma tabela consultada. O saldo contábil do ERP em 15/10 é de 4.066 unid. de cavaco. O consumo registrado de cavaco no período é de 2.240 unid., com dois documentos de saída (tipo 20). Para ETA/ETE, as saídas do período estão em 0. As saídas aparecem no ERP com data de 16/10 e 17/10 (22.825 unid. de ETA/ETE). Esse atraso de lançamento faz a quinzena subestimar o consumo e a mensal o capturar. Para reproduzir a referência, é preciso o saldo físico (medição de silo ou contagem), que não está no banco.

**3.3 Dias de produção (11,979167 na referência).** Três definições testadas para as duas máquinas da fase 150 (EB03 e EB04):
- soma de `MIN_REAL / 1440`: 18,981944 (conta em dobro as horas em que as duas máquinas rodam ao mesmo tempo);
- soma dos intervalos de operação de `MOVIMENTO_MAQUINA`: 18,297222;
- união dos intervalos (tempo com pelo menos uma máquina produzindo): 11,593750. É a definição usada nas consultas, por ser a mais coerente com "dias de produção" e a mais próxima da referência.

A diferença restante (0,385417 dia, cerca de 9h15) não foi explicada. Nenhuma das variações testadas (`MIN_PREV`, filtro por status, por código de movimento, por início ou fim no período) fecha esse valor.

**3.3.1 Saldo físico de cavaco (buscado em 17/10/2026).** Não há fonte no banco para o saldo físico de cavaco em 15/10:
- `INVENTARIO_GENERICO` / `PROD_DEP_INV_GEN`: o último inventário genérico com o item 1806 no depósito 125 é de 30/06/2020. O inventário de 26/09/2026 (nº 378) é do depósito 160, sem cavaco.
- `GERAPECAINVENTARIO`: sem registros do item 1806.
- `CONTROLECUBCAMINHAO`: cubagem por caminhão (placa e dimensões), sem registros de cavaco em outubro.
- `VW_ESP_CONTCAVACO`: nenhum registro entre 25/09 e 17/10/2026.
- `BALANCA`: configuração de equipamento, sem medição de cavaco.
- Não há tabela de medição de silo; o sensor ultrassônico do silo é um item de manutenção, não uma série histórica.

Conclusão: o saldo físico da referência (2.500 unid. de cavaco) não está no banco. Só pode ser obtido com a área (medição de silo ou contagem).

**3.3.2 Tabelas de movimento e saldo (investigadas em 17/10/2026).**
- `GERASALDOESTOQUE`: o saldo atual do item 1806 é de 4.066 unid. no depósito 125 (único depósito), sem parcela bloqueada. É o mesmo número do cálculo por movimentos, então o ERP não tem saldo físico diferente do contábil.
- `GERAMOVIESTOFECH`: guarda `QTFECHAMENTO` nos movimentos de abertura (tipo 999). Para o item 1806, reproduz exatamente os saldos de abertura de janeiro a outubro/2026 (2.592 em 01/10, 2.400 em 01/09). Não traz nenhum saldo físico.
- `GERAMOVIESTOLIGAESTO`: liga estornos (`IDESTORNO`) aos movimentos estornados (`IDESTORNADO`). Confirma que os pares de status 1/2 são estorno e estornado, então se anulam como assumido nas consultas. As duas entradas excluídas na referência (IDs 123349502 e 123349503) não têm vínculo de estorno.
- `ITENS_NOTA_ENTRADA`: as notas fiscais de entrada do item 1806 têm preço de R$ 85,00 ou R$ 88,00 e quantidades coerentes com os movimentos, mas a soma por data de entrada (4.718,5 unid., R$ 388.282,74 no período 01/10 a 15/10) não bate com as entradas de estoque (3.714 unid.). Não foi possível conciliar essa diferença sem conhecer o critério de lançamento.
- `GERAREQUESTOITEM`: 285 linhas de requisição para o item 1806, sem vínculo claro com a saída do dia 15 nem com os 2.500 da referência. Não conferido com profundidade.
- `CONTROLECUBCAMINHAO`, `VW_ESP_CONTCAVACO`, `INVENTARIO_GENERICO`, `BALANCA`: sem medição física de cavaco em outubro (ver 3.3.1).

Conclusão: nenhuma tabela de movimento ou saldo do banco registra uma quantidade física de 2.500 unid. de cavaco em 15/10/2026. O número da referência deve vir de medição externa.

**3.4 Químicos de corante, auxiliares, acabamento e commodities.** A referência só preenche a linha ETA/ETE. A consulta calcula todas as categorias, mas as entradas de corante não têm valor gravado em `MOVIMENTACAO_VALOR` (25.225 unid. com valor zero), o que distorce o custo médio dessa categoria. A categoria "COMMODITIES" (subgrupo 07) é uma hipótese de nomenclatura.

**3.5 Mês em andamento.** Outubro/2026 só tem movimentos até 17/10. A consulta mensal de outubro é parcial. Para validar um mês fechado, use setembro (seção 2.1).

## 4. Dicionário dos campos principais

| Campo | Fórmula | Unidade |
|---|---|---|
| QT_INI / VL_INI | Fechamento do mês anterior (`SALDO_ATUAL - QUANTIDADE_BLOQUEADA`) e valor unitário | unid. / R$ |
| QT_COMPRAS / VL_COMPRAS | Soma das entradas do período; valor = `QTMOVIMENTO x VLMOVIMENTO` | unid. / R$ |
| QT_CONSUMO / VL_CONSUMO | Soma das saídas do período; valor = saídas x custo médio | unid. / R$ |
| QT_FIM / VL_FIM | `QT_INI + QT_COMPRAS - QT_CONSUMO`; valor = qtd final x custo médio | unid. / R$ |
| VL_UNIT_* | Recalculado como valor / quantidade (nunca somado) | R$/unid. |
| VL_CONSUMO_POR_KG | `VL_CONSUMO / KG_RAMADO` | R$/kg |
| QT_CONSUMO_POR_DIA | `QT_CONSUMO / DIAS_PROD` | unid./dia |
| QT_CONSUMO_POR_TON | `QT_CONSUMO / (KG_RAMADO / 1000)` | unid./t |

## 5. Performance

Execução de referência: cerca de 5 segundos por consulta, medida com o MCP. Os movimentos são filtrados por `DTDOCUMENTO` (índice temporal `IDX_GME_01`). As agregações são feitas antes dos joins com as classificações, para evitar duplicação. A junção com `MOVIMENTACAO_VALOR` é 1:1 por `NUMERO_MOVIMENTO`, o que foi verificado nos itens testados.

## 6. Como usar

```sql
-- Quinzena de outubro/2026
:MES_REF = '2026-10'
-- Mensal de setembro/2026 (validação contra o fechamento)
:MES_REF = '2026-09'
```
