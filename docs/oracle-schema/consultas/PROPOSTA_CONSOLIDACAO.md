# Proposta de consolidação de consultas duplicadas ou com nome enganoso

Nenhum arquivo foi removido nem renomeado: remover arquivo do acervo depende de decisão da área. Cada item abaixo foi **conferido lendo os SQLs (e, quando indicado, no Oracle) em 29/09/2026**; o que não foi conferido está na última seção e não deve ser tratado como duplicata.

## Conferidos

### 1. Estoque de malha crua: `mal_estoque_por_lote_produto`, `mal_estoque_por_tear_maquina`, `mal_estoque_por_agulhas_tear`

- `lote` e `tear` são o **mesmo SQL** (mesmos filtros e o mesmo `ITE.CODIGO_REDUZIDO IN (11852)`), com `GROUP BY` diferente. Podem virar uma consulta com as colunas `LOTE` e `TEAR` (grão = lote + tear); cada original sai por soma de `PEAS` sobre uma das colunas.
- `agulhas` filtra o reduzido **133**, não o 11852. Não é a mesma consulta com outro agrupamento: alguém testou outro artigo. Consolidar exigiria decidir qual reduzido vale (ou passar a ser bind).
- Os três fazem `JOIN` com `TIPO_FINALIDADE_FIO`, que não alimenta nenhuma coluna. Pode ser removido sem mudar o resultado (a validar com `Tools/oracle/comparar_equivalencia.py`).
- **Decisão necessária:** qual reduzido é o do dia a dia; se quer o reduzido como bind.

### 2. `com_obs_e_romaneios_em_aberto` e `com_obs_e_romaneios_historico_completo`

- Diferem em **um único predicado**: `OB.STATUS <> 0` (em aberto, sem janela) contra `OB.DATA_ENTREGA_PEDIDO >= hoje - 30` (histórico, com janela, inclui OBs encerradas).
- Por isso o "histórico completo" **não é completo** (só entregas dos últimos 30 dias) e o "em aberto" não tem janela. Uma consulta única com a coluna `OB_ABERTA` (S/N) e o predicado `STATUS <> 0 OR entrega >= hoje - 30` reproduz as duas: em aberto = `OB_ABERTA = 'S'`; histórico = entrega dentro dos 30 dias.
- **Decisão necessária:** se o histórico deve mesmo ser de 30 dias.

### 3. `bnf_lavacao_maquinas_ultimas`

- O nome promete a última lavação por máquina, mas o SQL devolve **todo o histórico** das máquinas dos grupos `TG001`, `TG002` e `TG003`, com a recorrência até a lavação seguinte (`LEAD`). O `DISTINCT` tem um comentário pedindo agregação.
- A "última por máquina" de verdade já existe em `bnf_lavacao_de_maquina_ultimas_lavacoes_feitas.sql`, que teve o sinal de `DIAS_SEM_LAVAR` corrigido nesta rodada.
- **Sugestão:** renomear para `bnf_lavacao_maquinas_historico_recorrencia` ou fundir em `bnf_lavacao_maquinas_historico.sql`.

### 4. `pcp_top5_producao_mensal_media_diaria`

- O `OBJETIVO` diz "média de kg/dia", mas o SQL soma kg por mês (`SUM(QT_PROD)`) e ordena pelo total: é volume bruto, não média diária.
- A média diária de verdade está em `pcp_top5_producao_mensal_media_kg_dia.sql`.
- **Sugestão:** corrigir o `OBJETIVO` (ou renomear) e conferir se sobra diferença em relação a `pcp_top5_producao_mensal_volume_bruto.sql` antes de decidir entre manter e remover.

## Não conferidos (não trate como duplicata sem verificar)

Um levantamento automático apontou também: `mal_necessidade_balanco_faltas_sobras` × `mal_necessidade_critica_somente_faltas` (diferindo só no `WHERE` final), `acb_alterar_grupo_de_programacao_engenharia` × `acb_trocar_grupo_de_programacao` (mesma consulta com `'046'` × `'024'`), `pcp_quantidade_de_kgs_em_cada_fase` × `bnf_posicao_producao_fase_nativa_m019` e os pares `est_conferencia_furo_estoque_*`, `qld_conferencia_sku_*` e `com_pecas_destino_ob_romaneio` × `com_rastreabilidade_ob_romaneio_nfe`. Uma conferência por `diff` mostrou que `acb_alterar_*` e `acb_trocar_*` **não** são a mesma consulta com outro literal, então esse levantamento não é confiável sem conferência caso a caso.

## Como executar (após a decisão)

1. Criar a consulta consolidada com `GRÃO:` no cabeçalho.
2. Medir cada original e a consolidada com `Tools/oracle/medir_sql_oracle.py --dump` e provar a equivalência com `Tools/oracle/comparar_equivalencia.py` (a saída de cada original tem de sair da consolidada por filtro ou soma).
3. Só então remover ou arquivar os originais em `backup_legado_sql.zip`, regenerar o catálogo (`Tools/oracle/gerar_catalogo_sql.py`) e o grafo (`Tools/oracle/gerar_core_graph.py`). **Atenção:** `*.zip` é ignorado pelo `.gitignore`, então `backup_legado_sql.zip` existe só nesta máquina e fora de qualquer backup do Git; se os originais forem removidos, versione-os antes (ex.: pasta `_legado/`) ou faça cópia externa.
