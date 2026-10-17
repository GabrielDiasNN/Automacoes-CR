# Mapeamento de regras de consumo de produtos químicos

Dados verificados no Oracle SGTPRD em 17/10/2026 (somente leitura). As regras canônicas estão em [`consultas/REGRAS_NEGOCIO.md`](../consultas/REGRAS_NEGOCIO.md) (seção 6); este arquivo guarda as evidências e as pendências.

Consultas do acervo (validadas no Oracle, catalogadas):
- Sentinela: [`consultas/09_pcp_kpis_gestao/pcp_sentinela_quimicos_ruptura_compra.sql`](../consultas/09_pcp_kpis_gestao/pcp_sentinela_quimicos_ruptura_compra.sql)
- Histórico por partida e produto: [`consultas/01_beneficiamento_tingimento/bnf_consumo_quimico_historico_partida_produto.sql`](../consultas/01_beneficiamento_tingimento/bnf_consumo_quimico_historico_partida_produto.sql)
- Histórico mensal: [`consultas/01_beneficiamento_tingimento/bnf_consumo_quimico_historico_mensal_produto.sql`](../consultas/01_beneficiamento_tingimento/bnf_consumo_quimico_historico_mensal_produto.sql)

Diagnóstico auxiliar (fora do acervo, não catalogado): [`diagnostico_mapeamento_quimicos.sql`](diagnostico_mapeamento_quimicos.sql).

## 1. Conceitos separados

| Conceito | Fonte | Unidade | Situação |
|---|---|---|---|
| Consumo real (pesado) | `MOVTO_RECEITA.QUANTIDADEPESADA` com `MOVCONFIRMADO = 1` e `STATUSPESAGEMRECEITA = 3` | kg | Confirmado pelo padrão do acervo; ver item 3 |
| Previsto da receita | `MOVTO_RECEITA.QUANTIDADE` (quantidade emitida) | kg | Não é teórico calculado por fórmula; ver item 4 |
| Previsto a emitir | `MOVTO_RECEITA.QUANTIDADE` com `STATUSPESAGEMRECEITA <> 3` | kg | Demanda já emitida, sem pesagem |
| Estoque | `VW_ESTO_SALDO` (`QT_SALDO`, `QT_ESTOQUE_DISP`) no depósito 20 | kg | Confirmado; unidade KG (`UNIDADE_MEDIDA.DSSIGLA`) |
| Entrada futura | `ENTREGAS_PEDIDO_COMP` com `QTDPEDIDA - QTDRECEBIDA` e `DATAENTREGA >= hoje` | unidade do pedido | Ver item 6 |

## 2. Tabelas e chaves

- `MOVTO_RECEITA` (1,3 M linhas): receita por fase. Chave de fase `NUMEROORDEM` + `SEQUENCIAFASEOB` = `OB_FASES.NUMEROORDEMMOVIMENTO` + `SEQUENCIAORDEMMOVIME`. Insumo em `CODINSREDUZIDO` = `ITENS_ESTOQUE.CODIGO_REDUZIDO`. Data de pesagem em `DT_CONFIRMACAO` (DATE).
- `OB_FASES`: fase de tingimento com `CODIGO_FASE = 40`. Peso do tecido em `KILOS_PRODUZIDOS`. Não tem coluna de data de programação; a data prevista é `TEMPO_INICIAL_PREVIS` (minutos desde 01/01/1996).
- `VW_ESTO_SALDO`: saldo por `CD_REDUZIDO` e `CODIGO_DEPOSITO`.
- `AR_ESTOQUE_QUIMICO`: 155 produtos do setor TINTURARIA (grupos CORANTES e AUXILIARES), todos com estoque > 0 na data da consulta. Usado como universo.
- `ENTREGAS_PEDIDO_COMP` (`IDITENSPEDIDOCOMPRA`, `QTDPEDIDA`, `QTDRECEBIDA`, `DATAENTREGA` NUMBER no formato AAAAMMDD) -> `ITENS_PEDIDO_COMPRA` (`ID`, `CODINSREDUZIDO`, `IDPEDIDOCOMPRA`) -> `PEDIDO_COMPRA` (`ID`, `STATUS`, `TIPO`).
- `CADASTRO_RECEITAS` e `ITENS_CADASTRO_RECEI`: receita-mestre e itens da receita (`CONCENTRACAO`, `GRAMAS_DISSOLUCAO`, `DISSOLUCAO_LITROS`). Não contêm dosagem por kg de tecido; a base de cálculo não foi confirmada.
- `CUSTMOVICONSUMOQUIM`: registro de consumo de químicos com ajuste de data (`DATA_ORIGINAL`, `DATA_NOVA`) ligado a `GERAMOVIMENTOESTOQUE`. Não foi usado como consumo real: depende de integração de movimento, não de pesagem.

## 3. Consumo real: regra adotada e pendências

Regra adotada: `SUM(QUANTIDADEPESADA)` com `MOVCONFIRMADO = 1` e `STATUSPESAGEMRECEITA = 3`.

Evidências:
- `PESADA = 0` com `STATUSPESAGEMRECEITA = 3` ainda tem kg (1,53 M kg nos últimos 12 meses). Portanto `PESADA` não identifica pesagem.
- Lançamentos com `STATUSPESAGEMRECEITA = 0` e `PESADA = 1` somam 63,7 mil kg nos últimos 12 meses. Ficam fora da regra (pesagem não confirmada). Pendência: confirmar com o processo se esses kg já foram consumidos.
- Reconciliação: 01/10/2026 a 17/10/2026 dá 169.665,86 kg, com 7.090 linhas e 803 partidas. A agregação por partida e produto no histórico soma o mesmo total.
- Devoluções, estornos e ajustes: `EH_AJUSTE`, `SEQUENCIA_AJUSTE` e `REGISTROBAIXAESTOQUE` existem, mas não foram validados. Nada é subtraído. Pendência.

## 4. Consumo teórico: não validado

Hipótese testada: `QUANTIDADE = CONSUMO_UNITARIO * KILOS_PRODUZIDOS / 100` (percentual sobre o peso do tecido). Teste em 56.738 lançamentos de 3 meses:

| FATORCALCULO | Lançamentos | Bate com % do peso |
|---|---|---|
| 11 | 36.047 | 18.397 (51%) |
| 22 | 20.686 | 8.336 (40%) |

Outras bases testadas (g/L de banho, g/kg, percentual sobre volume e valor fixo) batem em menos de 1% dos casos. A fórmula não é universal. A diferença entre pesado e planejado é mediana 1,007 e média 1,023.

Conclusão: não há teórico confirmado. O histórico mostra `PREVISTO_RECEITA_KG` (quantidade emitida) e marca `BASE_COMPARAVEL = NAO` quando não há base. Pendência: identificar com o processo a base de cálculo de cada tipo de dosagem (`FATORCALCULO`, `DISSOLUCAO_LITROS`, `VW_PI_CBNFE06_RECPRD.DOSAGEM_PROP1/SEQ1`).

## 5. Previsão futura

- Não existe programação química por OB no banco. A demanda futura conhecida é só a receita já emitida e não pesada (`STATUSPESAGEMRECEITA <> 3`, emissão nos últimos 30 dias).
- Em 17/10/2026, 0 fases de tingimento abertas com previsão nos últimos 60 dias apareceram na consulta de status. O horizonte previsto fica limitado às receitas emitidas. Pendência: definir a programação por OB (`OB_FASES.TEMPO_INICIAL_PREVIS` com receita ainda não emitida).
- Receitas emitidas e não confirmadas (`MOVCONFIRMADO = 0`) ficam em coluna separada (`EMITIDO_NAO_CONFIRMADO_KG`) e não entram no saldo. O volume total não foi medido nesta sessão.

## 6. Compras

- `PRAZOENTREGA` é 0 em todas as linhas de `ITENS_PEDIDO_COMPRA` (84.964 linhas). Não há prazo de reposição no banco. O sentinela não inventa prazo: usa `:PRAZO_PADRAO_DIAS`, que está nulo, e classifica como `DADOS_INCOMPLETOS`.
- `DATAENTREGA` é a data prometida. Mediana de `DATAENTREGA - DATAPEDIDO` por insumo fica entre 0 e 6 dias. Não é prazo real de fornecedor; não foi usada.
- Entregas pendentes com data já vencida somam 111.560 kg (decorrentes de pedidos antigos sem baixa). O sentinela mostra em coluna separada e não conta como entrada.
- `PEDIDO_COMPRA.STATUS` tem valores 0, 1 e 2 nos pedidos pendentes. Significado não confirmado. O sentinela não filtra por status.
- Reservas: `QT_PED_ABERTO` é zero e `QT_ESTOQUE_DISP` é igual a `QT_SALDO` nos itens observados. Não há reserva descontada no disponível; o previsto é descontado uma vez.

## 7. Parâmetros pendentes (não são valores operacionais)

| Parâmetro | Valor no controle | Motivo |
|---|---|---|
| `DEPOSITO` | 20 | Observado nos dados; confirmar |
| `JANELA_DIAS` | 90 | Janela de análise, não política |
| `HORIZONTE_DIAS` | 30 | Janela de receitas emitidas |
| `SEGURANCA_KG` | 0 | PENDENTE: estoque de segurança não existe no banco |
| `COBERTURA_MIN_DIAS` | 0 | PENDENTE: desabilitado |
| `PRAZO_PADRAO_DIAS` | nulo | PENDENTE: prazo de reposição real. Sem ele, o item é DADOS_INCOMPLETOS |

## 8. Resultado observado (17/10/2026, controle com o prazo nulo)

| Situação | Produtos | Consumo real na janela (kg) | Disponível (kg) | Entrada futura (kg) | Observação |
|---|---|---|---|---|---|
| CRITICO | 10 | 46.196 | 0 | 0 | Estoque zero, consumo ativo, sem entrada futura |
| DADOS_INCOMPLETOS | 156 | 957.413 | 331.469 | 135.300 | Sem prazo de reposição; 98 com consumo |

Os 10 CRITICO são ruptura certa, independente de prazo. Os 156 DADOS_INCOMPLETOS só saem dessa classe quando houver prazo cadastrado ou definido em `PRAZO_PADRAO_DIAS`.

## 9. Validações feitas

- Reconciliação de consumo real: total direto e total agregado por partida e produto batem (169.665,86 kg).
- Sentinela: a consulta foi executada em forma resumida (mesma lógica de CTEs e critérios). O arquivo `.sql` completo não foi executado de ponta a ponta nesta sessão; a execução integral é o próximo passo.
- Histórico: a consulta de detalhe não foi executada integralmente; o total foi reconciliado.
- Diagnósticos D1 a D9: executados em forma equivalente durante a investigação. D7 e D8 não foram rodados literalmente.
- Caso com e sem histórico: produtos sem consumo na janela aparecem como DADOS_INCOMPLETOS (não somem).

## 10. Limitações e próximos passos

1. Confirmar com o processo a base de cálculo do teórico por tipo de dosagem (item 4).
2. Confirmar o significado de `PEDIDO_COMPRA.STATUS` e a fonte de prazo real de fornecedor (item 6).
3. Definir `SEGURANCA_KG`, `COBERTURA_MIN_DIAS` e `PRAZO_PADRAO_DIAS` com compras e PCP (item 7).
4. Decidir o tratamento de `PESADA = 1` com `STATUS = 0` (63,7 mil kg/12 meses).
5. Definir a programação futura por OB para o horizonte além de 30 dias.
6. Desempenho: as consultas usam `CROSS JOIN` com a CTE de parâmetros e agregações por produto. `MOVTO_RECEITA` (1,3 M) filtra por `DT_CONFIRMACAO` e `DT_EMISSAO`; índices nessas colunas não foram verificados por falta de acesso ao plano (`get_query_plan`). Medir antes de publicar.
