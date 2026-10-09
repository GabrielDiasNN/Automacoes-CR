# Catálogo de Consultas SQL — Produção Beneficiamento

> **Arquivo gerado — não edite à mão.** Regerar: `.venv/Scripts/python Tools/oracle/gerar_catalogo_sql.py`
> (`--evidencia <saida_validador.json>` para atualizar o status Oracle; `--check` antes do PR).
>
> Inventário = arquivos `.sql` das pastas `NN_*`; Objetivo/Categoria = linhas `OBJETIVO:`/`TIPO:` do cabeçalho;
> Binds = extraídos do SQL; Status = `validacao_status.json`, alimentado pela saída de `Tools/oracle/validar_sql_oracle.py`
> (guard + parse + execução limitada a 1 linha). Status de um arquivo alterado depois da validação é descartado.
> A referência estável de uma consulta é `pasta/arquivo.sql`.

## Resumo

**226 arquivos `.sql` em 13 pastas.**

| Status | Arquivos |
|---|---|
| ✅ validada | 209 |
| referência (DDL de view, não executada) | 10 |
| DML restrito (nunca executado) | 4 |
| ⏳ inconclusiva: sessão derrubada pela rede durante a execução | 2 |
| ⬜ alterada após validação de 09/10/2026 | 1 |

Amostra vazia: 10 consulta(s) validadas não retornaram linhas na janela/filtros padrão (sentinelas de anomalia ou filtros sem dados no momento — não é erro).

## Inventário por pasta

### 01_beneficiamento_tingimento (40)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `bnf_acumulado_montagem_tingimento_por_dia.sql` | Acumulado (Montagem-Tingimento) - Por Dia | Tingimento e Tinturaria | — | ✅ validada | com dados | 2201 ms |
| `bnf_acumulado_montagem_tingimento_por_turno.sql` | Acumulado (Montagem-Tingimento) - Por Turno | Tingimento e Tinturaria | — | ✅ validada | com dados | 1792 ms |
| `bnf_consulta_receita.sql` | Consulta Receita | Tingimento e Tinturaria | — | ✅ validada | com dados | 3 ms |
| `bnf_consumo_quimico_por_kg_tingido.sql` | Consumo de produtos químicos por kg de tecido tingido, por partida de tingimento confirmada nos últimos 30 dias (g/kg), com cor, artigo e máquina para agregação | Painel/KPI | — | ✅ validada | com dados | 160 ms |
| `bnf_fechamento_mes_obs_em_aberto_com_origens.sql` | Acompanhamento de Fechamento do Mês no Beneficiamento - Monitoramento de OBs em Aberto por Grupo de Programação, Estágio Produtivo, Macro-Setor, Origens, Avanço de Fases, Pesagem Real e Risco Operacional | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 362 ms |
| `bnf_fila_programada_por_maquina_tingimento.sql` | Fila programada por máquina de tingimento (UPs ainda não iniciadas): quantidade de partidas, kg, horas previstas à frente e atrasadas | Monitoramento operacional | — | ✅ validada | com dados | 143 ms |
| `bnf_gargalo_receitas_obs_aguardando.sql` | OBs abertas aguardando receita no tingimento (sem receita ativa, receita bloqueada ou receita não emitida), com dias de espera e kg programado | Monitoramento operacional | — | ✅ validada | com dados | 2112 ms |
| `bnf_lavacao_de_maquina_ultimas_lavacoes_feitas.sql` | Lavação de Máquina - (Últimas lavações feitas) | Tingimento e Tinturaria | — | ✅ validada | com dados | 733 ms |
| `bnf_lavacao_maquinas_historico.sql` | Histórico detalhado de todas as lavações de máquinas | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 289 ms |
| `bnf_lavacao_maquinas_ultimas.sql` | Últimas lavações realizadas por máquina | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 288 ms |
| `bnf_maiores_producoes_tingimento.sql` | Relatório "MAIORES PRODUÇÕES - TINGIMENTO" (Ranking Mensal Histórico de Produção Normal e Reprocesso) | KPI Consolidado Executivo / Gestão Fabril e Qualidade | — | ✅ validada | com dados | 3207 ms |
| `bnf_monitora_montagem_de_lote.sql` | Monitora montagem de lote | Tingimento e Tinturaria | — | ✅ validada | com dados | 916 ms |
| `bnf_monitora_tingimento_e_reprocesso.sql` | Monitora - Tingimento e Reprocesso (KPI Consolidado Oficial) | KPI Consolidado Executivo / Gestão Fabril e Qualidade | — | ✅ validada | com dados | 3728 ms |
| `bnf_monitora_tingimento_e_reprocesso_detalhado.sql` | Monitora - Tingimento e Reprocesso (Auditoria Analítica Detalhada por OB) | Auditoria Analítica Detalhada / Diagnóstico e Rastreabilidade Individual de OBs | — | ✅ validada | com dados | 612 ms |
| `bnf_monitoramento_atributos_produtos_quimicos.sql` | Monitorar Atributo Estoque (Produto Químico) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 251 ms |
| `bnf_monitoramento_maquinas_tingimento.sql` | Monitoramento Máquinas de Tingimento | Tingimento e Tinturaria | — | ✅ validada | com dados | 4 ms |
| `bnf_monitoramento_previsao_vs_realizado_tingimento.sql` | Monitoramento mensal de previsões de tingimento versus realizado | SELECT (Template Analítico / Operacional) | — | ✅ validada | com dados | 373 ms |
| `bnf_ob_fases_seleciona_ultima_sequencia_da_fase.sql` | OB_FASES - seleciona última sequência da fase | Tingimento e Tinturaria | — | ✅ validada | com dados | 5180 ms |
| `bnf_obs_abertas_por_codigo_reduzido.sql` | OB_s em aberto pelo Reduzido | Tingimento e Tinturaria | — | ✅ validada | com dados | 1641 ms |
| `bnf_obs_abertas_por_processo_corante.sql` | OB_s em aberto de determinado (processo ou corante) | Tingimento e Tinturaria | — | ✅ validada | com dados | 29 ms |
| `bnf_ocupacao_diaria_maquina_tingimento.sql` | Ocupação diária das máquinas de tingimento nos últimos 30 dias: minutos em produção, limpeza, manutenção, ajuste de planejamento, outras paradas e ocioso | Painel/KPI | — | ✅ validada | com dados | 291 ms |
| `bnf_painel_executivo_kpis_tingimento_mensal.sql` | Painel executivo mensal e dashboard consolidado de KPIs de tingimento | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1269 ms |
| `bnf_posicao_atual_obs_em_aberto.sql` | POSICAO-ATUAL-OBS-EM-ABERTO | Tingimento e Tinturaria | — | ✅ validada | com dados | 50 ms |
| `bnf_posicao_producao_fase_nativa_m019.sql` | AR M019 POSICAO PRD FASE nativa | Tingimento e Tinturaria | — | ✅ validada | com dados | 2659 ms |
| `bnf_primeiro_uso_receitas_tingimento.sql` | Primeiro uso receitas tingimento | SELECT (Consulta Somente Leitura) | — | ✅ validada | vazia | 1 ms |
| `bnf_quimico_valor_media_comparado_ao_preco_de_faturamento.sql` | Químico - valor média comparado ao preço de faturamento | Tingimento e Tinturaria | — | ✅ validada | com dados | 502 ms |
| `bnf_receitas_abertas_hidroextracao.sql` | Consulta Receitas em Aberto no Hidro | Tingimento e Tinturaria | — | ✅ validada | vazia | 8 ms |
| `bnf_receitas_bloqueadas_eps.sql` | Receitas de tingimento bloqueadas por Estrutura de Produto (EP) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 15 ms |
| `bnf_receitas_bloqueadas_por_ob.sql` | OB_s com receitas bloqueadas | Tingimento e Tinturaria | — | ✅ validada | com dados | 1434 ms |
| `bnf_receitas_bloqueadas_reduzidos.sql` | Receitas de tingimento bloqueadas por código reduzido | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 17 ms |
| `bnf_receitas_pendentes_emissao_por_ob.sql` | OB_s com receitas que faltam emitir | Tingimento e Tinturaria | — | ✅ validada | com dados | 412 ms |
| `bnf_receitas_pesadas_detalhes_inventario.sql` | OB_s com receitas pesadas (com detalhes produtos Júlio inventário) | Tingimento e Tinturaria | — | ✅ validada | com dados | 216 ms |
| `bnf_receitas_pesadas_por_ob.sql` | OB_s com receitas pesadas | Tingimento e Tinturaria | — | ✅ validada | com dados | 190 ms |
| `bnf_relacao_de_banho_calculo.sql` | RELAÇÃO DE BANHO | Tingimento e Tinturaria | — | ✅ validada | com dados | 2 ms |
| `bnf_tingimento_confirmado_consumo_produtos.sql` | OB_s com tingimento confirmado e quantidade de produtos usados | Tingimento e Tinturaria | — | ✅ validada | com dados | 37 ms |
| `bnf_tingimento_confirmado_por_processo_corante.sql` | OB_s com tingimento confirmado de determinado processo ou corante | Tingimento e Tinturaria | — | ✅ validada | com dados | 1204 ms |
| `bnf_tipos_maquinas_setor_lista.sql` | Tabela de tipos de máquinas por setor industrial | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1 ms |
| `bnf_ultimo_lote_tinto_por_maquina_reduzido.sql` | Consulta data-hora último lote tinto em cada MQ tingimento (por reduzido ou geral) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 222 ms |
| `bnf_up_ordem_movimento_vinculo.sql` | Vínculo detalhado entre Unidade de Programação (UP) e Ordem de Movimento | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 6 ms |
| `bnf_up_ordem_mvto_por_tipo_maquina.sql` | Unidades de Programação (UP) e movimentações por tipo de máquina | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1868 ms |

### 02_acabamento_preparacao (17)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `acb_acumulado_rama.sql` | Acumulado (RAMA) | Acabamento e Preparação | — | ✅ validada | com dados | 1707 ms |
| `acb_acumulado_tubular.sql` | Acumulado (TUBULAR) | Acabamento e Preparação | — | ✅ validada | com dados | 7257 ms |
| `acb_alterar_grupo_de_programacao_engenharia.sql` | Alterar grupo de programação (engenharia) | Acabamento e Preparação | — | ✅ validada | com dados | 7 ms |
| `acb_conferencia_pecas_embaladeira.sql` | Conferência - Peças (EMBALADEIRA) | Acabamento e Preparação | — | ✅ validada | vazia | 1737 ms |
| `acb_consulta_producao_de_artigos_ramados_de_acordo_configuracao_malharia.sql` | Consulta - produção de artigos ramados de acordo configuração malharia | Acabamento e Preparação | — | ✅ validada | com dados | 18 ms |
| `acb_entrada_de_nfs_dos_terceirizados_passar_a_programacao_da_semana.sql` | Entrada de NFs dos terceirizados (passar a programação da semana) | Acabamento e Preparação | — | ✅ validada | com dados | 39 ms |
| `acb_mix_programacoes.sql` | MIX PROGRAMAÇÕES | Acabamento e Preparação | — | ✅ validada | com dados | 217 ms |
| `acb_monitora_felpadeira_quanto_precisa_fazer_para_fechar_o_mes.sql` | Monitora - Felpadeira (quanto precisa fazer para fechar o mês) | Acabamento e Preparação | — | ✅ validada | com dados | 12 ms |
| `acb_monitora_rama_quanto_precisa_fazer_para_fechar_o_mes.sql` | Monitora - Rama (quanto precisa fazer para fechar o mês) | Acabamento e Preparação | — | ✅ validada | com dados | 984 ms |
| `acb_ordens_de_manutencao_programadas_e_planejadas.sql` | Ordens de Manutenção - Programadas e Planejadas | Acabamento e Preparação | — | ✅ validada | com dados | 4 ms |
| `acb_programacoes_em_aberto.sql` | Programações em aberto | Acabamento e Preparação | — | ✅ validada | com dados | 1317 ms |
| `acb_rama_fila_risco_expedicao_pedidos.sql` | Risco de Atraso de Pedidos e Clientes por OB Pendente nas Ramas | Monitoramento operacional | — | ✅ validada | com dados | 103 ms |
| `acb_rama_perda_artigos_desvio_engenharia.sql` | Identificação de Produtos com Maior Desvio de Tempo entre o Real e o Previsto pela Engenharia, com Minutos por Tonelada | Painel/KPI | — | ✅ validada | com dados | 197 ms |
| `acb_rama_producao_mensal_sem_tingimento.sql` | Produção mensal de malha crua na Rama (sem tingimento prévio na própria OB ou em ancestrais) | Painel/KPI | — | ✅ validada | com dados | 2372 ms |
| `acb_rama_pulmao_buffer_vs_pipeline.sql` | Monitoramento do Pulmão de Entrada das Ramas e Indicador de Autonomia em Horas | Monitoramento operacional | — | ✅ validada | com dados | 252 ms |
| `acb_rama_ritmo_liquido_setups_gaps.sql` | Diagnóstico Diário de Ritmo Líquido, Tempos de Setup e Gaps Ociosos nas Ramas | Painel/KPI | — | ✅ validada | com dados | 30 ms |
| `acb_trocar_grupo_de_programacao.sql` | Trocar grupo de programação | Acabamento e Preparação | — | ✅ validada | com dados | 4 ms |

### 03_malharia_teares (27)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `mal_agulhas_por_tonelada.sql` | Consumo de agulhas por tonelada produzida e por máquina-dia, por tear | Painel/KPI | — | ✅ validada | com dados | 7986 ms |
| `mal_calendario_producao_diaria.sql` | Calendário diário da malharia interna - máquinas com produção, kg | Monitoramento operacional | — | ⏳ inconclusiva: sessão derrubada pela rede durante a execução | — | — |
| `mal_conferencia_ob_montada_teares_e_lotes_alocados.sql` | Conferência - OB montada (teares e lotes alocados) | Malharia e Teares | — | ✅ validada | com dados | 5 ms |
| `mal_consulta_finura_dos_teares.sql` | Consulta Finura dos Teares | Malharia e Teares | — | ✅ validada | com dados | 2 ms |
| `mal_consulta_pecas_com_restricao_geradas_na_malharia_ultimos_60d.sql` | Consulta - Peças com restrição geradas na Malharia | Malharia e Teares | — | ⬜ alterada após validação de 09/10/2026 | — | — |
| `mal_disponibilidade_por_maquina.sql` | Proxy de tempo parado por tear interno do setor 4 = 1 - paradas / horas de | Painel/KPI | — | ✅ validada | com dados | 60 ms |
| `mal_eficiencia_global_engenharia.sql` | Produção e Eficiência da Malharia (Engenharia) | Malharia e Teares | — | ✅ validada | com dados | 10 ms |
| `mal_eficiencia_ordens_em_aberto.sql` | Produção e Eficiência da Malharia (Engenharia) ordens em aberto | Malharia e Teares | — | ✅ validada | com dados | 7 ms |
| `mal_eficiencia_por_grupo_maquinas.sql` | Produção e Eficiência da Malharia (Engenharia) por grupo de máquinas | Malharia e Teares | — | ✅ validada | com dados | 5 ms |
| `mal_eficiencia_teorico_vs_realizado.sql` | Teórico (engenharia do reduzido) x realizado por produto e grupo de | Conferência pontual | — | ✅ validada | com dados | 8621 ms |
| `mal_estoque_por_agulhas_tear.sql` | Estoque de malha crua agrupado por número de agulhas do tear | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 3 ms |
| `mal_estoque_por_lote_produto.sql` | Estoque de malha crua agrupado por lote | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 6 ms |
| `mal_estoque_por_tear_maquina.sql` | Estoque de malha crua agrupado por número do tear | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 8 ms |
| `mal_meta_malharia.sql` | Meta Malharia | Malharia e Teares | — | ✅ validada | com dados | 76 ms |
| `mal_necessidade_balanco_faltas_sobras.sql` | Necessidade Malharia (Faltas e Sobras) | Malharia e Teares | — | ✅ validada | com dados | 284 ms |
| `mal_necessidade_critica_somente_faltas.sql` | Necessidade Malharia (Somente Faltas) | Malharia e Teares | — | ✅ validada | com dados | 124 ms |
| `mal_obs_lotes_teares_misturados.sql` | OB_s com finalidade, lotes ou teares misturados | Malharia e Teares | — | ✅ validada | com dados | 63 ms |
| `mal_oee_aproximado_grupo.sql` | Desempenho x Qualidade nos dias produtivos, por grupo de máquinas (12 meses), | Painel/KPI | — | ✅ validada | com dados | 8392 ms |
| `mal_ordens_de_malharia_em_aberto.sql` | Ordens de Malharia em Aberto | Malharia e Teares | — | ✅ validada | com dados | 2 ms |
| `mal_paradas_categoria_mes.sql` | Paradas de teares internos por categoria e mês, com o lançamento em | Painel/KPI | — | ✅ validada | com dados | 67 ms |
| `mal_paradas_longas_eventos.sql` | Eventos de parada longa (acima de 8 horas) em teares internos, nos | Monitoramento operacional | — | ✅ validada | com dados | 8737 ms |
| `mal_pareto_paradas_internas.sql` | Pareto das paradas de teares internos por código, com participação | Painel/KPI | — | ✅ validada | com dados | 60 ms |
| `mal_producao_malha_por_maquina_mes.sql` | Produção de malha INTERNA por máquina e mês, com meta e paradas (visão gerencial) | Painel/KPI | — | ✅ validada | com dados | 8285 ms |
| `mal_proporcao_corretiva_maquina.sql` | Proporção de manutenção corretiva por tear interno, com minutos médios por | Painel/KPI | — | ✅ validada | com dados | 31 ms |
| `mal_qualidade_registro_paradas.sql` | Testes de qualidade do registro de paradas e quebras de agulha da | Auditoria/Sentinela | — | ✅ validada | com dados | 103 ms |
| `mal_quebra_agulha_mes.sql` | Quebra de agulha em teares internos por mês e máquina, com agulhas | Auditoria/Sentinela | — | ✅ validada | com dados | 69 ms |
| `mal_scorecard_maquina_12m.sql` | Scorecard de teares internos (12 meses) - produção, meta, paradas, | Painel/KPI | — | ⏳ inconclusiva: sessão derrubada pela rede durante a execução | — | — |

### 04_fiacao_fios (12)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `fia_consulta_lotes_de_fios_e_cor_dos_cones.sql` | Consulta - Lotes de fios e cor dos cones | Fiação e Fios | — | ✅ validada | com dados | 81 ms |
| `fia_consumo_fios_movimento_estoque.sql` | Movimentação de estoque de fios na fiação | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 2 ms |
| `fia_consumo_fios_reserva_baixa.sql` | Reserva de fios para baixa por ficha técnica | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 5 ms |
| `fia_estoque_de_fibras_disponiveis_atual.sql` | Estoque de fibras disponíveis atual | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 729 ms |
| `fia_estoque_de_fios_disponiveis_atual.sql` | Estoque de fios disponiveis atual | Fiação e Fios | — | ✅ validada | com dados | 7061 ms |
| `fia_fios_consumos_ficha_tecnica.sql` | Fios consumos ficha técnica | Fiação e Fios | — | ✅ validada | com dados | 3 ms |
| `fia_lotes_fios_fornecedor.sql` | Lotes de fios agrupados por fornecedor/pessoa | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 501 ms |
| `fia_lotes_fios_por_deposito.sql` | Lotes de fios distribuídos por depósito | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 88 ms |
| `fia_ob_s_que_usaram_fio_vortex.sql` | OB_s que usaram fio Vórtex | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1025 ms |
| `fia_pecas_no_estoque_que_foram_usados_fio_com_residuo.sql` | Peças no estoque que foram usados fio com resíduo | Fiação e Fios | — | ✅ validada | vazia | 16 ms |
| `fia_producao_fiacao.sql` | Produção Fiação (por Turno e Filial) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 32 ms |
| `fia_top_5_producao_diaria_fiacao.sql` | TOP 5 - Produção Diária Fiação | Fiação e Fios | — | ✅ validada | com dados | 251 ms |

### 05_estoque_armazenagem (12)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `est_conferencia_furo_estoque_peca_peca.sql` | Auditoria de furo de estoque detalhado peça a peça (terceirizados) | SELECT (Consulta Somente Leitura) | — | ✅ validada | vazia | 2376 ms |
| `est_conferencia_furo_estoque_por_ob.sql` | Auditoria de furo de estoque consolidado por Ordem de Beneficiamento | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 2413 ms |
| `est_conferencia_ob_montada_deposito_90_direto_para_o_100.sql` | Conferência - OB montada (depósito 90 direto para o 100) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1149 ms |
| `est_falta_pesar_peca_peca.sql` | Falta pesar (peça-peça) | Estoque e Depósitos | — | ✅ validada | com dados | 330 ms |
| `est_pecas_com_restricoes_estoque.sql` | Peças com restrições - Estoque | Estoque e Depósitos | — | ✅ validada | com dados | 30 ms |
| `est_pecas_com_status_normal.sql` | Peças com status normal | Estoque e Depósitos | — | ✅ validada | vazia | 14 ms |
| `est_pecas_para_restringir_verificando_estoque_disponivel_e_em_processo.sql` | Peças para restringir, verificando estoque disponível e em processo | Estoque e Depósitos | — | ✅ validada | com dados | 293 ms |
| `est_posicao_acumulada_estoque_total.sql` | Posição Acumulada de Estoque / Fluxo Diário (Entradas vs Acabamento) | SELECT (Consulta Analítica / Operacional) | — | ✅ validada | com dados | 1096 ms |
| `est_transferencias_deposito_por_artigo.sql` | Transfência Depósito (Por Artigo) | Estoque e Depósitos | — | ✅ validada | com dados | 199 ms |
| `est_transferencias_deposito_total_geral.sql` | Transferência de Depósito (Total) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 373 ms |
| `estoque_total_de_malha_crua.sql` | Estoque total de malha crua | Estoque e Depósitos | — | ✅ validada | com dados | 5223 ms |
| `estoques_totais.sql` | Estoques Totais | Estoque e Depósitos | — | ✅ validada | com dados | 89 ms |

### 06_qualidade_auditoria_obs (30)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `qld_auditoria_cadastros_maquinas_familias.sql` | Auditoria e Investigação de Coerência dos Cadastros de Máquinas e Famílias | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 14 ms |
| `qld_auditoria_detalhada_peca_rama_sem_tingimento.sql` | Auditoria analítica da linhagem física e motivos de exclusão ancestral de ordens candidatas da Rama | Auditoria/Sentinela | — | ✅ validada | com dados | 2069 ms |
| `qld_auditoria_grupos_maquinas_layout.sql` | Auditoria e Investigação de Coerência dos Grupos de Máquinas com Foco no Campo Nome do Layout | Auditoria e Qualidade de Grupos e Cadastros Industriais | — | ✅ validada | com dados | 10 ms |
| `qld_auditoria_historica_rama_sem_tingimento.sql` | Validação histórica sintética do KPI de Rama sem tingimento (totais de OBs, kg, datas e meses) | Auditoria/Sentinela | — | ✅ validada | com dados | 2403 ms |
| `qld_conferencia_composicao_acabado_x_cru.sql` | Conferência - Composição (acabado x cru) | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 97 ms |
| `qld_conferencia_entrada_de_nf_x_pesagem_das_pecas_data_entrada_x_pesagem.sql` | Conferência - Entrada de NF x Pesagem das peças (DATA ENTRADA x PESAGEM) | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 1010 ms |
| `qld_conferencia_grupoitem_gerargrupodinamico_no_pedidocomercial.sql` | Conferência - GrupoItem (gerargrupodinamico) no PedidoComercial | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 2 ms |
| `qld_conferencia_ob_montada_conferir_se_usaram_as_pecas_com_restricao.sql` | Conferência - OB montada (conferir se usaram as peças com restrição) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 150 ms |
| `qld_conferencia_ob_montada_consulta_nf_de_entrada_das_pecas_faccao.sql` | Conferência - OB montada consulta NF de entrada das peças (facção) | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 2 ms |
| `qld_conferencia_ob_montada_status_peca_e_ob_s_alocadas_por_nf.sql` | Conferência - OB montada (status peça e OB_s alocadas, por NF) | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 756 ms |
| `qld_conferencia_pecas_com_peso_menor_que_17kg.sql` | Conferência - Peças com peso menor que 17kg | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 461 ms |
| `qld_conferencia_pecas_faturadas_acima_do_padrao_zimmermann.sql` | Conferência - Peças faturadas acima do padrão (ZIMMERMANN) | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 490 ms |
| `qld_conferencia_pecas_usadas_atender_pedido_comercial_pecas_alocadas_no_pedido.sql` | Conferência - Peças usadas atender pedido comercial (peças alocadas no pedido) | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 6 ms |
| `qld_conferencia_pesos_carregamento_faccao.sql` | Conferência de pesos no carregamento para facção (versão analítica) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 5 ms |
| `qld_conferencia_reduzidos_que_faltam_incluir_no_contrato_de_industrializacao.sql` | Conferência - Reduzidos que faltam incluir no contrato de industrialização | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 16 ms |
| `qld_conferencia_reduzidos_que_faltam_sku.sql` | Conferência - Reduzidos que faltam SKU | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 26 ms |
| `qld_conferencia_sku_alternativo.sql` | Conferência de SKU TOTVS por código alternativo | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1649 ms |
| `qld_conferencia_sku_composicao.sql` | Conferência de SKU TOTVS com composição detalhada | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 67 ms |
| `qld_conferencia_sku_reduzido_agrupador.sql` | Conferência de SKU TOTVS por reduzido agrupador | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1 ms |
| `qld_conferencia_testes_qualidade_artigo.sql` | Testes de qualidade laboratoriais agrupados por artigo cru | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 41 ms |
| `qld_conferencia_testes_qualidade_ob.sql` | Testes de qualidade laboratoriais por OB e lote | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 2 ms |
| `qld_conferencia_tubetes_plasticos_reduzido.sql` | Conferência de tubetes e plásticos por código reduzido (por nota fiscal) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 30 ms |
| `qld_conferencia_tubetes_plasticos_romaneio.sql` | Conferência de tubetes e plásticos por romaneio | SELECT (Consulta Somente Leitura) | — | ✅ validada | vazia | 28 ms |
| `qld_first_pass_yield_tingimento.sql` | First-pass yield do tingimento por cor nos últimos 90 dias: percentual de fases de tingimento concluídas sem reprocesso, em quantidade e em kg | Painel/KPI | — | ✅ validada | com dados | 31 ms |
| `qld_monitoramento_nf_entrada_ciclo_completo.sql` | Monitoramento completo de nota fiscal de entrada na produção, qualidade e expedição | SELECT (Template Analítico / Operacional) | `:filial`, `:nf_entrada` | ✅ validada | com dados | 1028 ms |
| `qld_ob_s_com_peso_20_maior_ou_menor_comparado_a_peca_crua.sql` | Auditoria de OBs com quebra/divergência de peso crítica (Delta > 20% ou < -20%) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 2466 ms |
| `qld_ob_s_com_peso_maior_que_a_carga_maquina.sql` | OB_s com peso maior que a carga máquina | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 128 ms |
| `qld_ob_s_com_peso_menor_que_8kg.sql` | OB_s com peso menor que 8kg | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 3157 ms |
| `qld_ob_s_com_pesos_iguais_nas_pecas.sql` | OB_s com pesos iguais nas peças (Auditoria de Balança e Pesagem) | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 691 ms |
| `qld_obs_montadas_fora_da_regra_de_separacao.sql` | OBs montadas fora da regra de separação | Auditoria e Qualidade de OBs | — | ✅ validada | com dados | 73 ms |

### 07_expedicao_pedidos_comercial (24)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `com_acondicionamento_grade_quantidades.sql` | Acondicionamento por grade e quantidades de peças | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 309 ms |
| `com_acondicionamento_itens_pedido.sql` | Acondicionamento e embalagem de itens consumidos em pedidos | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 3 ms |
| `com_acondicionamento_pipeline_completo.sql` | Pipeline completo de pesagem e acondicionamento por OB e Pedido | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 747 ms |
| `com_consulta_pedidos_atrasados.sql` | Consulta de pedidos em atraso com OBs vinculadas e status de produção | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 188 ms |
| `com_consulta_pedidos_e_romaneios.sql` | Cruzamento operacional entre pedidos comerciais e romaneios de saída | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 574 ms |
| `com_consulta_peso_bruto_e_liquido.sql` | Consulta Peso Bruto e Líquido | Comercial, Pedidos e Expedição | — | ✅ validada | com dados | 3 ms |
| `com_liga_ob_no_pedido_comercial.sql` | Liga OB no Pedido Comercial | Comercial, Pedidos e Expedição | — | ✅ validada | com dados | 12 ms |
| `com_liga_romaneio_na_nota_fiscal.sql` | Vínculo de Romaneio com Nota Fiscal de Saída (NFC -> NFI -> GRI -> ROM) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 853 ms |
| `com_monitoramento_programacoes_clientes_analitico.sql` | Monitoramento Analítico de Programações de Terceiros, Andamento por OB e Chão de Fábrica | Consulta Analítica / Detalhamento Operacional de Chão de Fábrica, PCP e Comercial | — | ✅ validada | com dados | 304 ms |
| `com_monitoramento_programacoes_clientes_sintetico.sql` | Monitoramento Sintético de Programações de Terceiros e Chão de Fábrica | Consulta Executiva / Painel Sintético de Gestão Comercial, PCP e Diretoria | — | ✅ validada | com dados | 179 ms |
| `com_ob_s_disponiveis_para_montar_cores_criticas_por_pedido_comercial.sql` | OB_s disponíveis para montar, cores críticas por pedido comercial | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 197 ms |
| `com_obs_e_romaneios_em_aberto.sql` | Romaneios e status de expedição para OBs em aberto no processo | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 57 ms |
| `com_obs_e_romaneios_historico_completo.sql` | Histórico consolidado de OBs e Romaneios de expedição | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 5944 ms |
| `com_pecas_destino_ob_romaneio.sql` | Rastreabilidade de peças de destino da OB vinculadas a romaneio | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 795 ms |
| `com_precos_carteira_pedidos_abertos.sql` | Preços dos Pedidos em Aberto (Sentinela de Integridade de Preço R$ 0,01) | Comercial, Pedidos e Expedição (Auditoria / Sentinela de Preços) | — | ✅ validada | vazia | 69 ms |
| `com_rastreabilidade_ob_romaneio_nfe.sql` | Rastreabilidade ponta-a-ponta entre OB, Romaneio e Nota Fiscal | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 860 ms |
| `com_romaneados_artigos.sql` | Romaneados - Artigos | Comercial, Pedidos e Expedição | — | ✅ validada | com dados | 191 ms |
| `com_romaneados_pecas_e_kg.sql` | Romaneados - Peças e (kg) | Comercial, Pedidos e Expedição | — | ✅ validada | com dados | 681 ms |
| `com_saldo_kgs_acabados_pendentes_faturamento.sql` | Quantidade de KGs acabados (não faturados ainda) | Comercial, Pedidos e Expedição | — | ✅ validada | com dados | 584 ms |
| `com_tabela_precos_comunicacao_comercial.sql` | Cadastro de Preços (Informar pro e-mail) | Comercial, Pedidos e Expedição | — | ✅ validada | com dados | 291 ms |
| `com_tabela_precos_itens_servico_tingimento.sql` | Tabela da Verdade e Auditoria de Itens, Artigos, Cores e Preços de Serviços (Tingimento) | Comercial, Auditoria de Cadastros e Preços ERP (Fonte Única de Conferência) | — | ✅ validada | com dados | 17 ms |
| `com_tipos_romaneios_classificacao.sql` | Classificação de tipos de romaneios do sistema SGT | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 2 ms |
| `com_vendas_lojas_mensal_faturamento.sql` | Itens dos pedidos das lojas Costa Rica dos últimos 12 meses, com ano-mês (detalhe por item de pedido) | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 19 ms |
| `com_vendas_lojas_por_pedido.sql` | Vendas das lojas Costa Rica detalhadas por número de pedido | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 5 ms |

### 08_faccao_terceirizacao (5)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `fac_desenho_estamparia.sql` | Desenho Estamparia | Facção e Serviços Terceiros | — | ✅ validada | vazia | 2 ms |
| `fac_diagnostico_programacao_ambigua.sql` | Diagnóstico contábil de ordens de programação de terceirização com ambiguidade ativa de NF | Auditoria/Sentinela | — | ✅ validada | vazia | 5252 ms |
| `fac_faltas_e_sobras_faccao.sql` | Faltas e Sobras (Facção) | Facção e Serviços Terceiros (Consulta Somente Leitura) | — | ✅ validada | com dados | 842 ms |
| `fac_saldo_nf_faccao.sql` | Controle consolidado de saldo físico e disponível de NFs de terceirização/facção | Monitoramento operacional | — | ✅ validada | com dados | 5198 ms |
| `fac_tabela_reduzidos_com_servicos_em_terceiros.sql` | Tabela - Reduzidos com serviços em terceiros | Facção e Serviços Terceiros | — | ✅ validada | com dados | 52 ms |

### 09_pcp_kpis_gestao (29)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `pcp_aging_obs_por_fase_vs_sla.sql` | Aging das OBs montadas em aberto por fase atual, em faixas de dias parados, com quantidade fora do SLA | Painel/KPI | — | ✅ validada | com dados | 42 ms |
| `pcp_balanco_fluxo_cru_facao_processo.sql` | Balanço e Proporção de Fluxo de Malha (Cru, Facção Pendente e Em Processo) | PCP / Gestão de Fluxo e Pipeline Produtivo | — | ✅ validada | com dados | 120 ms |
| `pcp_calendario_planejamento_horas_trabalhadas.sql` | Calendario Planejamento (horas trabalhadas) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 4 ms |
| `pcp_consulta_paradas_de_maquinas_por_numero.sql` | Consulta - Paradas de Máquinas (por número ou histórico recente) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 2 ms |
| `pcp_consulta_status_peca.sql` | Consulta Status Peça | PCP e Produção | — | ✅ validada | com dados | 1 ms |
| `pcp_faturamento_mensal_cliente_prazo_expedicao_v2_2.sql` | Faturamento mensal por comprador com atendimento ao prazo de expedicao fisica | Painel/KPI | — | ✅ validada | com dados | 3232 ms |
| `pcp_fechamento_mensal_beneficiamento.sql` | Consulta Canônica Permanente de Fechamento Mensal do Beneficiamento | SELECT (Painel Analítico / Operacional / Diretoria) | — | ✅ validada | com dados | 2288 ms |
| `pcp_lead_time_obs_encerradas.sql` | Lead time das OBs encerradas nos últimos 90 dias por mês de encerramento, fluxo e tipo de ordem: média, mediana, P90, e divisão em espera até o primeiro início e tempo de processo | Painel/KPI | — | ✅ validada | com dados | 171 ms |
| `pcp_liga_reduzido_nas_classes_e_sub_grupos.sql` | Liga Reduzido nas Classes e Sub-Grupos | PCP e Produção | — | ✅ validada | com dados | 8 ms |
| `pcp_producao_12m_fato_serie_temporal.sql` | Série Temporal Histórica de Produção por Fase e Indicadores Fabris (Últimos 12 Meses + Mês Aberto) | SELECT (Painel Analítico / Histórico Contínuo) | — | ✅ validada | com dados | 5490 ms |
| `pcp_producao_12m_matriz_pivotada.sql` | Matriz Pivotada Executiva de Produção por Fases e KPIs Fabris (Últimos 12 Meses + Mês Aberto) | SELECT (Painel Analítico / Matriz Comparativa) | — | ✅ validada | com dados | 5464 ms |
| `pcp_producao_acabado_mensal_atual.sql` | Produção Acabado Mensal (atual) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 42 ms |
| `pcp_producao_mensal_pecas_kg_mov37.sql` | Produção Mensal por Peça e KG - Movimento 37 (Produto Acabado) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 618 ms |
| `pcp_producao_mensal_por_fase_comparativo.sql` | Consulta Mensal de Produção por Fase (Comparativo Mês Atual vs Mesmo Mês Ano Anterior - YoY) | SELECT (Painel Analítico / Operacional) | — | ✅ validada | com dados | 3216 ms |
| `pcp_producao_mensal_por_idpfj.sql` | Produção Mensal por IDPFJ | PCP e Indicadores Fabris | — | ✅ validada | com dados | 1286 ms |
| `pcp_producao_mensal_por_operador.sql` | Produção Mensal por Operador nas Fases do Beneficiamento | PCP e Indicadores Fabris / Ranking Operacional Consolidado | — | ✅ validada | com dados | 105 ms |
| `pcp_producao_mensal_produdo_acabado.sql` | Produção Mensal (Produdo Acabado) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 452 ms |
| `pcp_producao_por_fases_diario.sql` | Produção por Fases Diário | PCP e Indicadores Fabris | — | ✅ validada | com dados | 124 ms |
| `pcp_producao_por_fases_e_turnos_diario.sql` | Produção por fases e turnos (diário) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 4 ms |
| `pcp_quantidade_de_kgs_em_cada_fase.sql` | Quantidade de KGs em cada fase | PCP e Indicadores Fabris | — | ✅ validada | com dados | 1456 ms |
| `pcp_quantidade_de_kgs_em_cada_fase_antigo.sql` | Quantidade de KGs em cada fase (antigo) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 407 ms |
| `pcp_sincronismo_malha_ribana.sql` | Monitoramento analítico e operacional do sincronismo entre malha principal e ribana para rede de lojas | SELECT (Painel Analítico / Operacional PCP) | — | ✅ validada | com dados | 4270 ms |
| `pcp_top5_faturamento_matriz_mensal.sql` | TOP 5 - Faturamento Matriz Mensal | PCP e Indicadores Fabris | — | ✅ validada | com dados | 656 ms |
| `pcp_top5_producao_diaria_por_data.sql` | TOP 5 - Produção Diária por Data | PCP e Indicadores Fabris | — | ✅ validada | com dados | 402 ms |
| `pcp_top5_producao_diaria_por_operador.sql` | TOP 5 - Produção Diária por Operador | PCP e Indicadores Fabris | — | ✅ validada | com dados | 286 ms |
| `pcp_top5_producao_mensal_media_diaria.sql` | TOP 5 Produção Mensal por média de kg/dia | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 354 ms |
| `pcp_top5_producao_mensal_media_kg_dia.sql` | TOP 5 - Produção Mensal (Média kg por dia) | PCP e Indicadores Fabris | — | ✅ validada | com dados | 428 ms |
| `pcp_top5_producao_mensal_volume_bruto.sql` | TOP 5 Produção Mensal por volume bruto total | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 406 ms |
| `pcp_top5_producao_por_processo_industrial.sql` | TOP 5 - Produção por PI | PCP e Indicadores Fabris | — | ✅ validada | com dados | 136 ms |

### 10_engenharia_custos (6)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `eng_auditoria_fixador_receita_acabamento.sql` | Auditoria de Receitas de Acabamento, Grupos de Programação e OBs em Aberto (Trava SGT) | Auditoria/Sentinela | — | ✅ validada | com dados | 172 ms |
| `eng_custo_real_materia_prima_fechamento_mensal.sql` | Custo Real da Matéria-Prima dos produtos (fechamento do mês) | Engenharia e Ficha Técnica (Consulta Somente Leitura) | — | ✅ validada | com dados | 525 ms |
| `eng_peso_padrao_cru_e_acabado.sql` | Peso padrão (cru e acabado) | Engenharia e Ficha Técnica | — | ✅ validada | com dados | 54 ms |
| `eng_valida_ficha_tecnica_mct_bnt.sql` | Validação de Ficha Técnica Cru (MCT) e Acabado (BNT) de Clientes | SELECT (Auditoria e Validação de Engenharia de Produto) | — | ✅ validada | com dados | 30 ms |
| `eng_verifica_composicao_dos_itens.sql` | Verifica composição dos itens | Engenharia e Ficha Técnica | — | ✅ validada | com dados | 5 ms |
| `eng_verifica_largura_ob_engenharia.sql` | Verifica largura (OB engenharia) | Engenharia e Ficha Técnica | — | ✅ validada | com dados | 17 ms |

### 11_views_referencia_sgt (10)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `vw_bnf_ob_fases_up.sql` | View - VW_BNF_OB_FASES_UP | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_consulta___geracao_de_residuo_fiacao.sql` | Consulta - Geração de Resíduo (Fiação) | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_esp_ob_ped_rom_ajuste.sql` | VW_ESP_OB_PED_ROM (Ajuste) | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_esp_ob_ped_rom_com_prefixo.sql` | VW_ESP_OB_PED_ROM_com_prefixo | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_esp_ob_ped_rom_sgtprd.sql` | VW_ESP_OB_PED_ROM_sgtprd | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_pi_cbpap01_procbenef.sql` | VW_PI_CBPAP01_PROCBENEF | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_pi_cbpap02_prodbenef.sql` | VW_PI_CBPAP02_PRODBENEF | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_pi_cenga03_prodaca.sql` | vw_pi_cenga03_prodaca | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_pi_cfatc01_fat.sql` | VW_PI_CFATC01_FAT | DDL / Definição de View | — | referência (DDL de view, não executada) | — | — |
| `vw_sql_px015.sql` | SQL-PX015 | Consulta Fonte / View PX015 | — | referência (DDL de view, não executada) | — | — |

### 12_manutencao_dml_restrito (4)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `dml_alterar_grupo_de_programacao_pontos_de_controle.sql` | Alterar grupo de programação (pontos de controle) | DML - Atualização Controlada | — | DML restrito (nunca executado) | — | — |
| `dml_alterar_grupos_e_tipos_de_defeitos_ob_qualidade_ob_fases.sql` | Alterar grupos e tipos de defeitos (OB_QUALIDADE, OB_FASES) | DML - Atualização Controlada | — | DML restrito (nunca executado) | — | — |
| `dml_update_engenharia_grupos_de_programacao.sql` | Update Engenharia (grupos de programação) | DML - Atualização Controlada | — | DML restrito (nunca executado) | — | — |
| `dml_update_grupo_de_programacoes___observacoes_da_fase.sql` | Update Grupo de Programações - Observações da Fase | DML - Atualização Controlada | — | DML restrito (nunca executado) | — | — |

### 13_utilitarios_snippets (10)

| Arquivo | Objetivo | Categoria | Binds | Status Oracle | Amostra | Tempo |
|---|---|---|---|---|---|---|
| `util_ajuste_operadores.sql` | Ajuste Operadores | Segurança e Usuários | — | ✅ validada | com dados | 4 ms |
| `util_consulta_tabelas_do_oracle.sql` | Consulta Tabelas do Oracle | Snippet / Utilitário SQL | — | ✅ validada | com dados | 7 ms |
| `util_formatar_numeros_inteiros_em_data_ou_hora_min.sql` | Formatar números inteiros em data ou hora-min | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1 ms |
| `util_formatar_numeros_no_sql.sql` | Formatar números no SQL | Snippet / Utilitário SQL | — | ✅ validada | com dados | 1 ms |
| `util_grupos_seguranca_usuarios_ativos.sql` | Consulta de usuários por ID de grupo de segurança | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 3 ms |
| `util_listagg_unir_linhas_moderno.sql` | Padrão moderno com LISTAGG no Oracle | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1 ms |
| `util_optstraggr_unir_linhas_legado.sql` | Unir filiais distintas em uma única coluna com LISTAGG nativo | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1 ms |
| `util_permissoes_atividades_usuarios.sql` | Consulta de permissões de atividades liberadas para usuários | SELECT (Consulta Somente Leitura) | — | ✅ validada | com dados | 1 ms |
| `util_tabelas_de_monitoramento_rapida_performace.sql` | Tabelas de monitoramento (rápida performace) | Snippet / Utilitário SQL | — | ✅ validada | com dados | 2 ms |
| `util_usuarios_ativos.sql` | Usuários ativos | Segurança e Usuários | — | ✅ validada | com dados | 3 ms |
