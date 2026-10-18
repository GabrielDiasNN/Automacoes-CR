# Catálogo de KPIs (ERP SGT)

Mapa dos indicadores que o acervo cobre, das lacunas comprovadas contra o Oracle e do status de cada uma. Os números citam a data da medição (17/10/2026), porque as tabelas crescem e a janela de 12 meses é móvel. Os status e tempos das consultas vêm do [`CATALOGO_QUERIES.md`](CATALOGO_QUERIES.md), gerado. Regras de negócio: [`REGRAS_NEGOCIO.md`](REGRAS_NEGOCIO.md).

## 1. Cobertura atual por área

| Área | Consultas (categoria Painel/KPI) | Cobertura |
|:---|:---|:---|
| Tingimento | `bnf_painel_executivo_kpis_tingimento_mensal`, `bnf_monitora_tingimento_e_reprocesso`, `bnf_maiores_producoes_tingimento`, `bnf_ocupacao_diaria_maquina_tingimento`, `bnf_consumo_quimico_por_kg_tingido` | Produção, reprocesso, ocupação, consumo de químicos |
| Qualidade | `qld_first_pass_yield_tingimento`, `qld_auditoria_historica_rama_sem_tingimento` | FPY do tingimento, rama sem tingimento |
| Acabamento | `acb_rama_ritmo_liquido_setups_gaps`, `acb_rama_perda_artigos_desvio_engenharia`, `acb_rama_producao_mensal_sem_tingimento` | Ritmo líquido, setup, desvio de engenharia |
| Malharia | `mal_oee_aproximado_grupo`, `mal_scorecard_maquina_12m`, `mal_disponibilidade_por_maquina`, `mal_pareto_paradas_internas`, `mal_paradas_categoria_mes`, `mal_proporcao_corretiva_maquina`, `mal_producao_malha_por_maquina_mes`, `mal_agulhas_por_tonelada` | OEE, disponibilidade, paradas, corretiva, produção, consumo de agulhas |
| PCP | `pcp_aging_obs_por_fase_vs_sla`, `pcp_lead_time_obs_encerradas`, `pcp_producao_12m_matriz_pivotada`, `pcp_producao_12m_fato_serie_temporal`, `pcp_producao_mensal_por_fase_comparativo`, `pcp_sincronismo_malha_ribana`, séries TOP 5 | Aging, lead time, produção por fase e turno, sincronismo |
| Expedição | `pcp_faturamento_mensal_cliente_prazo_expedicao_v2_2` | Faturamento por comprador e atendimento ao prazo |
| Comercial e PCP | `com_monitoramento_programacoes_clientes_sintetico` | Programações de clientes e de terceiros pendentes de atendimento |
| Fechamento | `pcp_fechamento_mensal_beneficiamento` | Fechamento mensal do beneficiamento, com parâmetro de competência |
| Manutenção | `kpi_manutencao_mttr_mensal`, `kpi_manutencao_backlog_om_aberta` | OMs solicitadas, concluídas, MTTR e backlog por família |
| Custos e qualidade de montagem | `kpi_custo_nao_conformidade_reprocesso_mensal`, `kpi_reprocesso_montagem_mensal` | Custo de NC e reprocesso por setor; reprocesso na montagem |

## 2. Status das lacunas (verificado no Oracle em 17/10/2026)

| # | Lacuna | Status | Evidência |
|:---|:---|:---|:---|
| 1 | Custo de não conformidade e reprocesso | **Coberta** (`kpi_custo_nao_conformidade_reprocesso_mensal`) | Total de kg de NC e custo de NC batem com a consulta independente (diferença de 1 kg e R$ 0,01, por arredondamento linha a linha) |
| 2 | Manutenção: tempo de execução (MTTR) | **Coberta** (`kpi_manutencao_mttr_mensal`), com ressalva da FIAÇÃO | Contagens de solicitadas, concluídas, não executadas e situação 4 batem exatamente com a consulta independente (2.419 / 1.955 / 194 / 269) |
| 3 | Manutenção: backlog de OMs abertas | **Coberta** (`kpi_manutencao_backlog_om_aberta`) | 194 OMs, das quais 41 com mais de 180 dias, batem com a consulta independente |
| 4 | Reprocesso na montagem (`BD_BNF_REPROC_UNICO`) | **Coberta** (`kpi_reprocesso_montagem_mensal`) | Fases de montagem (24.326), reprocessadas (1.922) e kg (17.025.322) batem com a consulta independente; a diferença de 3 kg no total vem do arredondamento |
| 5 | Paradas de tingimento (`BD_PRD_PARADAS_MAQ` e `PARADAS_MAQUINA`) | **Coberta** (`kpi_paradas_uniao_fontes_mensal`), com as duas fontes como oficiais | Regra de identidade: mesma máquina e sobreposição de pelo menos 50% do menor intervalo. Medido em out/2025 a out/2026: BD com 28.095 eventos, PARADAS_MAQUINA com 27 eventos sem par na BD, total de 28.122 eventos únicos. No setor 5 (tingimento), 1.668 eventos, todos na BD |
| 6 | Metas por cliente (`TCLI_META_*`) | **Fechada: a premissa estava errada.** A meta não existe por cliente | As quatro tabelas têm uma linha por dia (malharia: 2.543 linhas em 2.543 dias; tingimento: 460 em 460; fiação CN e NT da mesma forma). As views que as alimentam (`VW_TCLI_META_MALHARIA`, `VW_TCLI_META_FIACAO_*`, `AR_META_TINTURARIA`) não têm nenhum filtro de cliente. A malharia e a fiação somam `KG_DIA_EFIC` de `TB_ESP_PROD_TEOR_MAL` por dia. O nome `TCLI` é histórico. A meta é diária da empresa |
| 7 | OTIF de compras (`ENTREGAS_PEDIDO_COMP`, com nota de entrada) | **Coberta** (`kpi_otif_compras_mensal`) | Regra: no prazo = última `DATA_DA_ENTRADA` da nota até `DATAENTREGA`. Completa = `QTDRECEBIDA >= QTDPEDIDA`. Medido de 12 meses: 19.040 linhas, 994 sem nota, 18.046 avaliáveis, 17.912 completas, 7.168 no prazo, 7.131 OTIF (39,5%). Conferido com uma consulta de forma diferente, com igualdade exata |

Ressalva da lacuna 2: para FIAÇÃO, 350 de 789 OMs concluídas (44%) têm duração de pelo menos 167 h em múltiplo de 168 h. Isso indica tempo de calendário com a OM aberta, não esforço de reparo. TINTURARIA tem 201 OMs abaixo de 1 h e nenhuma no padrão de 168 h. MALHARIA tem 1 OM abaixo de 1 h.

## 3. Pontos que dependem de decisão ou confirmação

- **Paradas (lacuna 5), ressalvas da união:** dez/2025 setor 2 tem a PARADAS_MAQUINA com volume baixo, possivelmente carga incompleta, a confirmar com a TI. O setor 217 existe só na BD e o significado não está confirmado. Há 59 registros da PARADAS_MAQUINA e 91 da BD com código fora de `MOTIVOS_PARADAS`.

- **Fonte de paradas de tingimento (lacuna 5):** qual tabela é a oficial, `PARADAS_MAQUINA` ou `BD_PRD_PARADAS_MAQ`. Depois disso, criar o KPI só com a fonte escolhida.
- **Regra de prazo de compras (lacuna 7):** `DATAENTREGA` é a data programada da linha, mas ela pode ser reprogramada. Com 60% das linhas avaliáveis fora do prazo, confirmar com compras que a data programada atual é a promessa válida.
- **Regra da manutenção (lacuna 2):** se o tempo da FIAÇÃO deve ser lido como tempo de calendário ou se há um tempo de reparo real em outro campo.
- **Significado da SITUACAO 4 (250 OMs, com confirmação e sem datas reais):** ainda não confirmado.

## 4. Como manter este catálogo

Este arquivo é mantido à mão. Quando um número mudar, atualize a data da medição junto com o número. Os status e os tempos das consultas continuam vindo do `CATALOGO_QUERIES.md`, gerado a partir da evidência do validador.
