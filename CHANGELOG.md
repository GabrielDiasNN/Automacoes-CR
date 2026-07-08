# Changelog

## [1.1.2] - 08/07/2026
### Corrigido
- **`comTimeout()` (`lib/WhatsApp-Core.js`) causava crash silencioso do processo Node em lotes com menções**: o helper de timeout adicionado em `82ca31be` usava `Promise.race([promise, timeout])` sem descartar a promise perdedora. Quando `client.getNumberId()` (chamado por `resolverMencoes()` para cada `@numero` na caption) rejeitava *depois* que o timeout de 15s já havia "vencido" a corrida, essa rejeição tardia não tinha `.catch` anexado — unhandled rejection que, a partir do Node 15+ (ambiente roda Node 24), derruba o processo inteiro. Afetava apenas automações que geram menções em volume no modo `BATCH` (OBP-04/OBs Paradas Fase, com até ~17 fases por execução), nunca `Receitas Bloqueadas` (modo `AUTO`, sem menções) — explicando por que só a primeira apresentava timeout/erro recorrente. Corrigido anexando `promise.catch(() => {})` à promise original dentro de `comTimeout()`, suprimindo a rejeição tardia sem alterar o comportamento de timeout já observável por quem chama.

## [1.1.1] - 07/07/2026
### Adicionado
- **Quantidade de peças e quilos reais (origem/destino) no drill-down**: a função Oracle bloqueada por falta de GRANT (`PKGBENF0001.FNC_RETORNA_PC_ORIGEM_OB`, ver [1.1.0]) foi substituída por join direto em `SGTPRD.GERAPECAORIGEMOB`/`GERAPECADESTINOOB` + `GERAPECASPRODUTO` (acessíveis ao usuário readonly, validado em produção: 89,6% de cobertura, ~3s por dia). Duas novas CTEs (`DIM_PECAS_ORIGEM`, `DIM_PECAS_DESTINO`) no template SQL, colunas `PECAS_ORIGEM`/`KG_ORIGEM_REAL`/`PECAS_DESTINO`/`KG_DESTINO_REAL` persistidas (schema SQLite v6, nova recarga completa de 90 dias). São valores por OB (não escalados por fase/percentual, ao contrário de `QT_KG`) — nova coluna "Peças (OB)" no `DetailDrawer` com tooltip detalhando origem vs. destino.

## [1.1.0] - 07/07/2026
### Adicionado
- **Painel dedicado de Tingimento, reconstruído do zero**: novo módulo `contracts/tingimento.py` e endpoint `GET /api/beneficiamento/tingimento` (escopo fixo `CODIGO_FASE=40`, independente dos filtros gerais da aba — só aceita `dt_inicio`/`dt_fim`). Cobre resumo (OBs, KG, eficiência, reprocesso relativizado ao KG produzido, setup médio, desvio médio, produtividade), série diária (volume + reprocesso %) e rankings por máquina, por cor e por turno, com `amostra_insuficiente` (n<20) sinalizado. `MIN_SETUP`/`MIN_PROCESSO` agora persistidos (schema SQLite v5, nova recarga completa de 90 dias). Novo componente `Dashboard/src/components/beneficiamento/TingimentoPanel.tsx`, com presets de período próprios, na `BeneficiamentoPage`.
- **Autocomplete de produto e filtro hierárquico Setor→Grupo→Fase** (ver seção anterior) ganharam continuidade neste ciclo com a coluna MT (metros) e desvio relativo no drill-down (`DetailDrawer`).
### Alterado
- **Reprocesso removido dos rankings gerais "por setor industrial" e "fases críticas"**: só tem sinal real quando relativizado à produção de uma fase específica (ex.: cor tingida); nas demais fases/máquinas é ruído. A análise de reprocesso agora vive exclusivamente no painel de Tingimento.
- **`DetailDrawer` (drill-down)**: largura aumentada (720px → 1080px) para eliminar a barra de rolagem lateral com as colunas atuais. Coluna "Fim" agora formata `DD/MM/YYYY HH:MM:SS` (`formatDateTimeBr`, novo em `lib/format.ts`) em vez do ISO cru. Coluna "Desvio (min)" (minutos absolutos, sem contexto do tamanho da fase) substituída por "Desvio" em percentual relativo ao tempo previsto, com destaque visual (âmbar >15%, vermelho >30%). Nova coluna MT (metros).
### Não incluído (bloqueio técnico)
- **Quantidade de peças**: a função Oracle `PKGBENF0001.FNC_RETORNA_PC_ORIGEM_OB` usada para esse cálculo retornou `ORA-00904` para o usuário Oracle readonly atual — o Oracle disfarça falta de permissão (`GRANT EXECUTE`) como "identificador inválido". Precisa de liberação do DBA antes de ser adicionada com segurança à query de produção.

## [1.0.9] - 07/07/2026
### Adicionado
- **Beneficiamento: separação visual de produção confirmada vs. planejada**: investigação do default de 30 dias revelou que a query sempre trouxe OBs `PLANEJADA`/`PROGRAMADA` (ainda não executadas) misturadas com produção `CONFIRMADA` — não é um bug de refresh, é um comportamento pré-existente (útil para um PCP ver o que está agendado). `STATUS_FASE`/`DS_STATUS_FASE` agora são persistidos no histórico (schema SQLite bump para v4, nova recarga completa de 90 dias) com a chave derivada `STATUS_KEY` (`confirmada`/`planejada`). Novo filtro `status` (`confirmada`/`planejada`/todos) em `GET /overview` e `/detail`. KPIs ganharam `fases_planejadas` e `planejado_pct`, exibidos como indicador visual (⚠ acima de 20%) no tile "Fases concluídas" do Dashboard, sem remover ou filtrar dados por padrão — apenas tornando visível a mistura.

## [1.0.8] - 07/07/2026
### Alterado
- **Beneficiamento: enquadramento e sinal de reprocesso**: o painel fixo dedicado da fase Tingimento (`_build_tingimento`, campo `tingimento` do overview) foi removido — desde a fase real por fase (v1.0.7), qualquer fase tem drill-down equivalente via `rankings.fases_criticas`/`treemap`, tornando o bloco redundante e de baixo sinal (0,74% de reprocesso na base). Ranking "por setor industrial" promovido para o topo da grade de rankings no Dashboard. `rankings.fases_criticas` ganhou o campo `amostra_insuficiente` (true quando `fases_concluidas < 20`), sinalizado com aviso visual na UI para não comparar percentuais de reprocesso estatisticamente instáveis (ex.: 1 fase com reprocesso = 100%).
- **`filter_options.alternativos` removido**: listava até 160 dos 596+ produtos distintos em um `<select>` simples, inviável de navegar; substituído por busca dinâmica.
### Adicionado
- **Autocomplete de produto**: novo endpoint `GET /api/beneficiamento/produtos?q=` (busca por código ou descrição, mínimo 2 caracteres, limite configurável) e componente `Dashboard/src/components/beneficiamento/ProductAutocomplete.tsx` substituindo o `<select>` de 596 itens na `FilterBar`.
- **Filtro hierárquico completo Setor → Grupo de Fase → Fase** na `FilterBar` (selecionar setor reseta grupo/fase; selecionar grupo reseta fase).

## [1.0.7] - 07/07/2026
### Alterado
- **Beneficiamento: substitui o bucket grosseiro `CD_DS_FASE` (11 categorias por `TIPO_MAQUINA`) pela fase real do Oracle + hierarquia Setor Industrial → Grupo de Fase → Fase**: `sql/templates/detalhado.sql` ganhou as CTEs `DIM_FASE` (join `FASES_FLUXO`→`GRUPO_FASES`→`SETOR_INDUSTRIAL`) e `DIM_TIPO_MAQ` (`VW_ENU_TIPO_DE_MAQUINAS_SETOR`), projetando `CODIGO_FASE`, `DESCR_FASE`, `DESCR_GRUPO_FASE`, `DESCR_SETOR_INDUST` e `DESCR_TIPO_MAQ` em vez do `CASE` textual. Schema SQLite bump para v3 (`HISTORICO_SCHEMA_VERSION = 3`, dispara recarga completa do histórico via `runner.py`) com as novas colunas e chaves derivadas `SETOR_KEY`/`GRUPO_FASE_KEY`/`TIPO_MAQ_KEY`. Painel de Tingimento reancorado em `CODIGO_FASE = 40` (antes `FASE_KEY = '03 - TINGIMENTO'`).
### Adicionado
- **Filtros dinâmicos por setor industrial, grupo de fase, tipo de máquina e reprocesso** em `GET /api/beneficiamento/overview` e `/detail` (novos query params `setor`, `grupo_fase`, `tipo_maquina`, `reprocesso`), com novos `target_type` de drill-down (`setor`, `grupo_fase`, `tipo_maquina`). Novo ranking "por setor industrial" e agregação hierárquica `treemap` (Setor → Fase → Máquina) no contrato de overview.
- **Treemap Setor → Fase → Máquina no Dashboard** (`Dashboard/src/components/beneficiamento/Treemap.tsx`, SVG próprio slice-and-dice sem dependência externa, tooltip com top-3 máquinas por célula), integrado à `BeneficiamentoPage` com drill-down por clique. `FilterBar` ganhou seletores hierárquicos de Setor → Fase, Tipo de Máquina e toggle tri-state de Reprocesso.

## [1.0.6] - 07/07/2026
### Adicionado
- **OBP-04: nova fase monitorada 47-UMM (UMEDECIMENTO DE MALHA)**: adicionada em `OBs Paradas Fase/config.json` (bloco `fases_monitoradas` e mapa `ordem_codigos_fase`), com `threshold_dias: 0.5`, `ativo: true` e `responsavel: lider_reserva_3_turno` (mesmo papel da fase 45-CDC). Tabela de fases monitoradas em `docs/runbooks/obs-paradas-fase-runbook.md` atualizada.

## [1.0.5] - 06/07/2026
### Corrigido
- **`Import-HubEnv` (`lib/Lib-Config.psm1`) enviava o comentário inline do `.env` junto com o valor real**: linhas no formato `CHAVE=numero         # Nome Legível` (comentário usado só para legibilidade/manutenção do `.env`, nunca deveria compor o valor) eram parseadas sem remover esse comentário. O valor resultante incluía o texto do comentário, e como `generate_phase_cards.py` (OBP-04) monta a menção do card com `f"Responsável: @{cfg.responsavel}"`, o WhatsApp exibia o nome do comentário (prefixado por `#`) ao lado da menção — afetava todos os contatos de líder/reserva configurados dessa forma. Lógica de parsing extraída para a função `ConvertFrom-EnvLine` (nova, testável isoladamente via `InModuleScope`) que agora aplica `[regex]::Replace($value, '\s+#.*$', '')` para descartar tudo após um `#` precedido de espaço. Afeta todas as automações que leem `.env` via `Import-HubEnv`/`Get-HubConfig` (mecanismo compartilhado), não só OBP-04. Testes de regressão em `lib/tests/Lib-Config.Tests.ps1` cobrindo comentário inline, valor sem comentário e linha de comentário puro.

## [1.0.4] - 06/07/2026
### Adicionado
- **Endpoint `GET /api/system/metrics/daily?days=N` — métricas diárias agregadas de execução (Fase 3 do plano Monitor/Beneficiamento)**: novo `services.metrics.get_daily_execution_metrics` agrega por dia (via `func.date(started_at)`, aproveitando o índice `ix_exec_status_started`) total, sucessos, erros, taxa de sucesso, duração média e p95 (calculado em Python por dia — SQLite não tem percentil nativo; volume limitado pela retenção de 90 dias de `purge_old_executions`). `days` limitado a `[1, 90]` via `Query(ge=1, le=90)` no router (`Orchestrator/app/routers/system.py`); novos schemas `DailyExecutionMetric`/`SystemMetricsDailyResponse` em `Orchestrator/app/schemas/system.py`. Cobertura de `services/metrics.py`: 97% (`Orchestrator/tests/test_metrics_daily.py`, 6 testes: agregação vazia/single-day, execução pendente sem taxa terminal, payload do endpoint, `days` padrão e limites 0/91/90).
- **Página Monitor: tendência de taxa de sucesso, duração média e falhas 7d**: dois novos gráficos `TimeSeries` (uPlot) — taxa de sucesso % e duração média (s) — cobrindo os últimos 14 dias, consumindo o endpoint acima (`orchestratorApi.getSystemMetricsDaily`, novo em `Dashboard/src/api/orchestrator.ts`). Novo tile "falhas (7d)" compara a semana atual com a anterior (client-side, a partir dos mesmos 14 dias) e mostra a variação percentual ou "sem base de comparação" quando a semana anterior não teve erros.

## [1.0.3] - 06/07/2026
### Alterado
- **Rename "Observabilidade" → "Monitor" no Dashboard (Fase 2 do plano Monitor/Beneficiamento)**: item de menu, rota (`/observabilidade` → `/monitor`, com redirect `<Navigate>` preservando bookmarks/links antigos) e página (`Dashboard/src/pages/ObservabilidadePage.tsx` → `MonitorPage.tsx`) renomeados. `Orchestrator/tests/test_e2e_dashboard.py` atualizado (tupla de rotas, docstring de evidência, teste de screenshot) e ganhou `test_e2e_dashboard_observabilidade_redirect_to_monitor` cobrindo o redirect. Baseline visual `dashboard_observabilidade.png` removido (órfão) e regenerado como `dashboard_monitor.png`.

### Adicionado
- **Console de telemetria: correção do parsing de eventos reais + filtros client-side**: o handler do WebSocket `/ws/events` esperava um payload `{logs: [...]}` que o backend nunca envia — `ConnectionManager.broadcast_event` sempre emite `{type, data, timestamp}` (`Orchestrator/app/routers/websocket.py`), então o console de telemetria nunca exibia eventos reais em produção (bug pré-existente, corrigido nesta versão via verificação com `POST /api/broadcast_event`/`broadcast_logs` reais). `MonitorPage.tsx` agora traduz corretamente `LOG_UPDATE`, `TASK_STARTED`, `TASK_STOPPED`, `TASK_TIMEOUT`, `TASK_FAILED` e `TASK_COMPLETED` em linhas legíveis, coloridas por severidade. Adicionados filtros 100% client-side sobre o buffer de 300 linhas em memória: por execução (dropdown das últimas 30 vistas), por tipo de evento (dropdown dinâmico) e busca livre — sem novo tráfego de rede.
- **Tendência de fila nos KPIs do Monitor**: novo gráfico `TimeSeries` (uPlot) com `pending_count`/`running_count` ao longo do tempo, seletor de janela (1h/6h/24h/7d), consumindo `GET /api/system/history?hours=X` (parâmetro já existente e já clampado em `[1, 336]` pelo próprio serviço — nenhuma mudança de backend). Sparklines nos tiles "pendentes" e "em execução".
- **Tiles clicáveis com deep-link para Execuções**: os tiles pendentes/em execução/concluídas/falhas agora navegam para `/execucoes?status=PENDING|RUNNING|SUCCESS|ERROR`. `ExecucoesPage.tsx` ganhou leitura do filtro inicial via `useSearchParams` (mudança mínima, só o valor inicial do `useState`; nenhuma outra alteração de comportamento).

## [1.0.2] - 06/07/2026
### Adicionado
- **Beneficiamento: filtros dinâmicos, séries diárias e drill-down por clique na aba do Dashboard**: a página passou a consumir `GET /api/beneficiamento/overview` e `GET /api/beneficiamento/detail` (existentes no backend desde 31/05/2026, mas nunca ligados à UI) em vez do agregado estático `/dashboard`. Nova barra de filtros (`Dashboard/src/components/beneficiamento/FilterBar.tsx`) com seletores de máquina/fase/turno/produto populados por `filter_options`, intervalo de datas com presets 7d/30d/90d e busca livre com debounce de 350ms (`useDebouncedValue`, novo hook em `Dashboard/src/hooks/`). Dois gráficos `TimeSeries` (uPlot) mostram volume diário (kg) e eficiência diária; sparklines nos tiles de KG total e Eficiência de tempo. As 4 tabelas de ranking (gargalos, fases críticas, produtos principais, por turno) abrem um `Drawer` de drill-down (`Dashboard/src/components/beneficiamento/DetailDrawer.tsx`) ao clicar em uma linha, consumindo `/detail` com paginação e, para o alvo "ob", o trace cronológico de fases. 100% sobre o SQLite histórico já indexado — nenhuma consulta nova ao Oracle, nenhuma migração de schema, nenhum endpoint novo. `Dashboard/src/api/orchestrator.ts` ganhou tipagem completa para overview/detail (antes `Record<string, unknown>`), espelhando o shape real dos builders em `Produção Beneficimento/src/beneficiamento/contracts/_queries_overview.py` e `_queries_detail.py`.
- Baseline visual Playwright `docs/playwright-screenshots/baseline/dashboard_beneficiamento_kpi.png` regenerado para refletir o novo layout (mudança intencional de UI; `test_screenshot_beneficiamento_kpi_carregado` voltou a comparar corretamente).

## [1.0.1] - 06/07/2026
### Corrigido
- **Investigação de falhas reportadas nas automações após a migração de e-mail/WhatsApp para `.env`**: diagnóstico com evidência de logs de produção (06/07) confirmou que a causa real era **disco C: cheio** (`Disco critico (0–0.19 GB)`, uso em 98%), abortando o pré-flight (`Test-AutomationPreFlight`) antes de qualquer envio — sem relação com a refatoração de e-mail. Confirmações de que a lógica `.env`-first está correta: OBP-04 rodou 06/07 05:32 e enviou 6/6 cards WhatsApp com sucesso (`ExitCode=0`); todos os pré-flights reportaram `OK: Oracle (SRVDB02) On`, confirmando que `-OracleHost` resolve corretamente de `ORACLE_CONNECT_STRING`; harness read-only via `Lib-Config.psm1`/`Import-HubEnv` (o mesmo mecanismo usado pelos `run.ps1`) confirmou que `MT_EMAIL_TO/CC`, `RB_EMAIL_TO/CC`, `RE_EMAIL_TO`, `OBP_WHATSAPP_TARGET` e `RB_WHATSAPP_TARGET` carregam os valores reais corretamente. Os `@example.com` visíveis são os placeholders intencionais nos `config.json` versionados — os destinatários reais vivem no `.env`, como projetado.
- **~181 MB liberados no repositório** (mitigação parcial do disco cheio, escopo restrito ao repo): removidos 21 arquivos de log rotacionado/teste já superados em `Orchestrator/Logs/` (198→38 MB: `*.1`–`*.5` rotacionados e `*_test.jsonl` de ruído de pytest, nenhum versionado) e os diretórios `.wwebjs_cache/` de `OBs Paradas Fase/`, `Receitas Bloqueadas/`, `lib/`, `Tools/` e raiz (~20 MB, cache regenerável). `lib/.wwebjs_auth/` (sessão WhatsApp logada) **preservado intacto** — deletá-lo forçaria novo scan de QR code. Nota: o C: também enche por fontes fora do repo; esta limpeza reduz a pegada do repo mas não substitui a limpeza do sistema.
- **Line-endings corrompidos por edição anterior restaurados em `lib/Lib-Email.psm1`, `lib/Lib-Retry.psm1` e `_Template/run.ps1`**: a sessão anterior (expurgo de PII) havia reescrito o arquivo inteiro ao editar 1–3 linhas nesses 3 arquivos (efeito colateral da ferramenta de edição normalizando o encoding exótico pré-existente, `\r\r\n`+BOM). Restaurados do git e a correção de conteúdo (fallback de e-mail via `AUTOMACAO_ALERT_EMAIL` em vez de hardcoded) reaplicada com substituição de string pura preservando byte a byte o encoding original. Achado incidental: mesmo um `git checkout HEAD --` sem nenhuma edição já produz esse "diff" nesses 3 arquivos — é um defeito pré-existente do repositório (blob commitado não bate com a declaração `eol=crlf`/`working-tree-encoding=UTF-8` de `.gitattributes` para `*.psm1`/`*.ps1`), não algo introduzido nesta ou na sessão anterior; a normalização do git ao tocar o arquivo é, na verdade, uma correção positiva desse defeito.
- **Line-endings mistos no `.env` normalizados** (CRLF uniforme): as linhas de e-mail/WhatsApp anexadas na sessão anterior estavam em LF puro enquanto o resto do arquivo é CRLF. Verificado (antes e depois) que o parser de `Import-HubEnv` extrai os valores corretamente em ambos os casos — puramente higiene, sem impacto funcional. `.env` não é versionado.

### Nota de processo
- `ORCHESTRATOR_VERSION`/`WORKER_VERSION` em `constants.py` permanecem em `1.0.0` (não bumpados para 1.0.1): `Tools/Test-SemanticGovernance.ps1` valida essas constantes contra a "versão operacional de referência" fixada em `docs/ai-native-context-monitor.md`, e não contra o header do CHANGELOG — mesmo padrão usado ao longo de toda a série `9.5.x`, onde o CHANGELOG numerava cada entrada livremente sem exigir que a constante acompanhasse. Bumpar a constante exigiria propagar `1.0.1` para os 8 docs cross-referenciados pela governança semântica, o que não se justifica para uma correção sem mudança de contrato/comportamento do runtime.

## [1.0.0] - 05/07/2026
### Alterado
- **Reset formal de versão para v1.0.0, marcando o recomeço do projeto em novo repositório GitHub**: `ORCHESTRATOR_VERSION`/`WORKER_VERSION` (`Orchestrator/app/constants.py`), `README.md`, `CONTEXT.md` e os 6 docs de governança com stamp de versão (`docs/ai-native-context-monitor.md`, `docs/quality-dashboard.md`, `docs/testing-strategy.md`, `docs/release-checklist.md`, `docs/repository-governance.md`, `docs/security-policy.md`, `docs/test-coverage-map.md`) atualizados de `v9.5.0` para `v1.0.0`. Motivo: a numeração interna nunca acompanhou a granularidade real do CHANGELOG (parada em `9.5.0` desde a v9.3.6→v9.5.0, mesmo com ~34 entradas subsequentes na série 9.5.x) — `package.json`/`Dashboard/package.json` já estavam em `1.0.0` sem nunca terem sido sincronizados com o resto da stack. Decisão de negócio: aproveitar a migração para um repositório novo (ver expurgo de PII abaixo) para alinhar todo o versionamento em `v1.0.0` como marco de lançamento real, em vez de continuar uma numeração já dessincronizada. Referências históricas a versões específicas dentro do próprio texto do `CHANGELOG.md` e de `CONTEXT.md`/runbooks (ex.: "desde v9.5.20", "ADR-019 v9.5.0") foram mantidas intactas — documentam fatos históricos de quando cada mudança ocorreu, não o estado atual do projeto.
- **Varredura completa de PII/segredos em todo arquivo versionado do git** (não só `OBs Paradas Fase`): buscados padrões de telefone BR, CPF, CNPJ, e-mail, tokens (GitHub/AWS/Slack/JWT), chaves privadas, hostnames internos, IPs privados, username Windows e artefatos de sessão WhatsApp nos 435 arquivos rastreados. Confirmados como **não** sensíveis (mantidos): nomes de schema/coluna Oracle (`SGTPRD.*`, `NOME_OPERADOR_INI` etc.) — identificadores funcionais obrigatórios das queries, não credenciais; SHAs de commit em `.github/workflows/governanca.yml` — pins de GitHub Actions (boa prática); dados sintéticos em `test_sanitization.py` (CPF/IP fictícios que provam o mascaramento). Uma passada inicial mais rasa havia declarado "nenhum vazamento adicional" e classificado os `contactId` de WhatsApp como roteamento não-PII — **corrigido nesta versão**: a segunda varredura, mais profunda, encontrou e-mails corporativos e um contato individual (ver Segurança abaixo).

### Segurança
- **E-mails corporativos de funcionários removidos de todo arquivo versionado** (achado da segunda varredura, não pego na primeira que focou em telefones): endereços reais no formato `nome.sobrenome@<dominio-corporativo>` estavam hardcoded em 9 arquivos — listas de destinatários em `Montagem de Terceirizados/config.json`, `Receitas Bloqueadas/receitas_config.json` e `Receitas Emitidas/receitas_config.json`; fallbacks `gabriel.dias@...` em `Montagem/run.ps1`, `lib/Lib-Email.psm1`, `lib/Lib-Retry.psm1`, `Tools/ConfigurarEmailTeste.ps1` e `_Template/run.ps1` (comentário); e dados de teste em `Orchestrator/tests/test_notifications.py`. Correção: destinatários reais migraram para `.env` (`MT_EMAIL_TO`/`MT_EMAIL_CC`, `RB_EMAIL_TO`/`RB_EMAIL_CC`, `RE_EMAIL_TO`), com os `run.ps1` lendo env-first e o `config.json` versionado guardando apenas placeholders `@example.com`. Os fallbacks hardcoded passaram a usar `AUTOMACAO_ALERT_EMAIL` (já existente no `.env`) ou foram substituídos por placeholder/supressão (`Lib-Retry` agora suprime o alerta com WARN se `AUTOMACAO_ALERT_EMAIL` não estiver configurado, em vez de usar e-mail hardcoded). Dados de teste genericizados para `@example.com`. `.env.example` documenta as novas variáveis.
- **Contato WhatsApp individual e ID de grupo removidos dos `whatsapp-config.json` versionados**: `Receitas Bloqueadas/whatsapp-config.json` continha um `contactId` de **contato individual** (`<numero>@c.us`), ou seja, o WhatsApp pessoal de uma pessoa (PII real; a classificação anterior de "roteamento não-PII" valia só para IDs de grupo `@g.us`, não para este). `OBs Paradas Fase/whatsapp-config.json` tinha um ID de grupo (`<numero>-<timestamp>@g.us`, que embute o número do criador do grupo). Ambos migraram para `.env` (`RB_WHATSAPP_TARGET`, `OBP_WHATSAPP_TARGET`): o config versionado guarda placeholder + uma referência `contactIdEnv` ao nome da variável de ambiente. `lib/Send-WhatsApp.ps1` passou a aplicar o override via `target.contactIdEnv` (env-first) para o modo AUTO (Receitas Bloqueadas); `OBs Paradas Fase/run.ps1` lê `OBP_WHATSAPP_TARGET` antes do `contactId` do config no modo BATCH.
- **Hostname interno do servidor Oracle removido de arquivos versionados**: o nome real do servidor estava hardcoded em `lib/Lib-Logging.psm1` (`Test-Connection` no pre-flight `Test-AutomationPreFlight -CheckOracle`) e citado em `OBs Paradas Fase/README.md`. `Test-AutomationPreFlight` ganhou o parâmetro `-OracleHost` e resolve o host de `ORACLE_CONNECT_STRING` (env var ou leitura direta do `.env`) — sem host configurável, emite WARN e pula o ping em vez de falhar. Divulgação de topologia interna eliminada; o host real vive só no `.env`. O schema e o service name Oracle mantidos por serem identificadores funcionais das queries, não exploráveis sem host+credenciais (ambos já protegidos no `.env`).

## [9.5.34] - 05/07/2026
### Segurança
- **PII (nomes e números de WhatsApp de responsáveis operacionais) removida de todo arquivo versionado, em preparação para publicação em novo repositório**: a seção `contatos` de `OBs Paradas Fase/config.json` — que guardava nome+número real dos 6 papéis de turno e da equipe de qualidade — foi removida do arquivo versionado. `generate_phase_cards.py`/`format_message.py` passaram a resolver cada papel (`lider_1_turno`, `lider_reserva_1_turno`, ..., `equipe_cq`) via variáveis de ambiente `OBP_CONTATO_<PAPEL>` (nova função `_load_contatos_from_env()`), lidas de `.env` local (nunca versionado, já no `.gitignore`) através do mesmo mecanismo usado pelas credenciais Oracle (`os.environ`, injetado pelo `run.ps1`/`Lib-Config.psm1`). Os fallbacks hardcoded de nome/número que viviam no próprio código-fonte de ambos os scripts (usados apenas se `config.json` estivesse ausente/corrompido) também foram substituídos por leitura de ambiente. `.env.example` ganhou os 7 placeholders `OBP_CONTATO_*` documentados; `.env` real recebeu os valores de produção. Nomes/números reais também removidos de `CHANGELOG.md` (entradas 9.5.20 e 9.5.21) e de `docs/runbooks/obs-paradas-fase-runbook.md`. `Orchestrator/tests/test_obs_paradas_fase.py`: `test_config_json_valido` passou a exigir a **ausência** de `contatos` em `config.json`; fixtures com nome/número real substituídas por dados fictícios (`5500000000001` etc.); `test_config_real_resolve_contatos_por_variavel` passou a usar `monkeypatch.setenv` para simular os papéis via ambiente. Achado incidental: `OBs Paradas Fase/whatsapp-config.json` e o equivalente de `Receitas Bloqueadas` expõem `contactId` de grupo (`<numero>-<timestamp>@g.us`) — mantido sem alteração, é ID operacional de roteamento (like a channel id), não dado pessoal de um indivíduo.

## [9.5.33] - 05/07/2026
### Adicionado
- **Fase 4 do planejamento de fechamento: verificação operacional das 4 automações de domínio registradas (RB-01, RE-03, MT-02, OBP-04)**. Para cada uma, adicionado nos runbooks (`docs/runbooks/*.md`): (a) evidência de SLA — última execução `SUCCESS` real consultada no banco de produção (somente leitura) comparada contra o `sla_minutes` cadastrado, todas dentro do SLA com folga; (b) drill de falha simulado — executado isoladamente contra cópia em memória do schema real (nunca contra `automacoes.db` de produção nem disparando WhatsApp/e-mail/Outlook real), injetando execuções `ERROR`/SLA-breach sintéticas e chamando as funções reais de recuperação (`collect_sla_breaches`, `check_sla_breaches`, `prepare_requeue`). Resultado: SLA breach detectado corretamente nas 4; auto-retry elegível para RB-01 (`max_retries=2`) e MT-02 (`max_retries=1`); auto-retry corretamente **bloqueado** para RE-03 e OBP-04 (`max_retries=0`, decisão deliberada do operador — falhas exigem intervenção manual). Achado incidental: as 4 automações compartilham `queue_group="oracle"` em produção, serializando retries entre si por design.
- `docs/ai-native-context-monitor.md`: referência cruzada explícita a `Produção Beneficimento/CONTEXT.md` como exceção arquitetural deliberada (sem manifesto/run.ps1), para evitar que agentes futuros interpretem a ausência como lacuna.

## [9.5.32] - 05/07/2026
### Adicionado
- **Fase 3 do planejamento de fechamento: paridade documental e gate de cobertura do Dashboard**. `Dashboard/README.md` criado (dev/build/test/design system). Gate de cobertura Vitest adicionado em `Dashboard/vitest.config.ts` — escopo deliberadamente restrito a `src/api/`, `src/hooks/`, `src/lib/`, `src/context/` (componentes e páginas ficam de fora, validados via Playwright E2E, não Vitest); piso de 40% linhas / 65% funções / 85% branches, medido em 43.6%/70%/90% real com margem de regressão (mesmo critério do gate Python). CI (`governanca.yml`, job `frontend`) passou a rodar `npm run test:coverage` em vez de `npm test`. Critério de transição do job `benchmark` (non-blocking) registrado em `docs/quality-dashboard.md`: promover a bloqueante só se houver regressão sustentada em 3 execuções consecutivas de CI nos 4 benchmarks nomeados (`test_bench_schedule_parse`, `test_bench_portfolio_catalog_build_summary`, `test_bench_oracle_extract_serialize_rows_1000`, `test_bench_system_diagnostics_build_payload`), ou incidente real de produção rastreável a uma regressão que o job já media e não bloqueou.

## [9.5.31] - 05/07/2026
### Adicionado
- **Fase 2 do planejamento de fechamento: cobertura dos 4 módulos nomeados como déficit da Fase 3 de QA**. `app/telemetry.py` (28%→93%), `app/metrics.py` (40%→94%), `app/services/beneficiamento_refresh.py` (31%→100%), `app/routers/websocket.py` (47%→100%). Novos arquivos: `test_telemetry_unit.py` (mocka `sys.modules` para simular o SDK OpenTelemetry indisponível/disponível, já que o pacote real não está instalado no venv), `test_metrics_prometheus_unit.py` (usa `prometheus_client` real, que já está instalado), `test_beneficiamento_refresh_unit.py` (mocka `subprocess.run`), `test_websocket_router_unit.py` (primeiro teste de WebSocket do projeto — `ConnectionManager`, validação de key, log replay e os 2 endpoints WS + 3 endpoints HTTP de broadcast). Cobertura total subiu de 82.66% para 85.40% (`--cov=app --cov=worker`, medição igual à do CI).
- **Gate de cobertura do CI elevado de 82% para 84%** (`--cov-fail-under=84` em `.github/workflows/governanca.yml`), mantendo margem de ~1.4pp sobre a medição real, no mesmo critério da subida anterior (83%→82%).

### Nota de processo
- Confirmado que rodar `pytest` sem `-m "not e2e"` localmente (incluindo `test_e2e_dashboard.py` na mesma sessão) deixa o event loop asyncio do processo em estado inconsistente após uma falha do Playwright, quebrando testes assíncronos executados depois (`test_telemetry_unit.py`, `test_websocket_router_unit.py`). Isso **não afeta o CI**, que já roda `testes-python` (`-m "not e2e"`) e `testes-e2e` (`-m e2e`, só `test_e2e_dashboard.py`) em jobs separados — mas é importante rodar a suíte local com `-m "not e2e"` para reproduzir fielmente o comportamento do CI.

## [9.5.30] - 05/07/2026
### Corrigido
- **Dívida de formatação black/isort eliminada em `Orchestrator/app`**: 9 arquivos (`logger_setup.py`, `error_handlers.py`, `middleware.py`, `routers/automation_ide.py`, `routers/automation_config.py`, `routers/websocket.py`, `routers/automations.py`, `schemas/common.py`, `services/portfolio_catalog.py`) reprovavam `black --check` e 1 (`services/portfolio_catalog.py`) reprovava `isort --check-only` — dívida pré-existente registrada desde jun/2026. Aplicado `black`/`isort` (config já presente em `pyproject.toml`, perfil `black`) só nesses arquivos; diff de 65 linhas, 403 testes e `ruff check` seguem verdes. Em `schemas/common.py`, o black quebrou a assinatura de `parse_dt_br` em múltiplas linhas, descolando o comentário `# pylint: disable=too-many-return-statements` da linha reportada pelo pylint (R0911) — corrigido extraindo dois helpers (`_parse_dt_br_pattern`, `_parse_dt_iso_or_legacy`) em vez de suprimir, reduzindo os retornos da função sem alterar comportamento (mesmos testes de `test_timezone_contract.py` cobrem os casos; equivalência verificada manualmente e por revisão arquitetural independente contra 17 casos-limite). Decisão do usuário: corrigir agora em vez de aceitar como dívida permanente, no contexto do planejamento de fechamento de desenvolvimento do projeto.
- **Mutation testing (mutmut) descartado permanentemente**: decisão explícita do usuário de não introduzir dependência de WSL/Linux no projeto — stack é 100% nativa Windows. Não será revisitado.

## [9.5.29] - 05/07/2026
### Corrigido
- **Reordenação de imports da 9.5.28 quebrava o gate de CI `Lint Python` (Black & Isort)**: o fix anterior (`isort -p app --known-local-folder tests`) satisfazia o pylint local mas divergia do `isort` real do projeto (`pyproject.toml [tool.isort]`, perfil `black`, sem `known-first-party` configurado) — que é o padrão validado pelo job `lint-python` do CI e roda com `--check-only` sobre todo arquivo tocado no diff, sem tolerância parcial. Corrigido na direção oposta: os 17 arquivos voltaram à ordem original (`app.*` antes de `fastapi`/`sqlalchemy`/`pytest`/`conftest`), que é o que o isort do projeto realmente espera; `C0411` foi desabilitado no pylint do hook local (`Tools/Test-PythonGovernance.ps1`) e documentado em `CLAUDE.md`, já que a detecção de first-party do pylint diverge do isort e as duas ferramentas nunca vão concordar nessas linhas. `worker.py` ganhou um bloco `# isort: off` / `# isort: on` ao redor dos dois imports com alias intencional (`claim_next_task as claim_next_task`, usados por `@patch("worker.claim_next_task")` nos testes) — sem o bloco, isort tentava fundi-los num único `from` que quebra o ruff (conflito já documentado em `CLAUDE.md`). Arquivos com débito de formatação pré-existente e tocados nesta sessão (`test_diagnostics.py`, `test_executions.py`, `test_filters.py`, `test_schedule_advanced.py`, `test_timezone_contract.py`, `test_system.py`) foram formatados por completo com black, porque o gate do CI não permite formatação parcial de um arquivo alterado.

## [9.5.28] - 05/07/2026
### Corrigido
- **`C0411` (wrong-import-order) pré-existente em 16 arquivos de `Orchestrator/tests/`**: o pylint do hook de governança (`Tools/Test-PythonGovernance.ps1`) só reconhece o pacote `app.*` como first-party; imports de `pytest`, `fastapi`, `sqlalchemy` e `conftest`/`tests.conftest` posicionados depois de imports `app.*` disparavam `wrong-import-order` e reprovavam qualquer commit que disparasse `full_scan` (arquivos centrais staged), mesmo sem relação com a mudança. Corrigido reordenando os imports (`python -m isort -p app --known-local-folder tests`) — só a ordem dos imports mudou, sem reformatação de código adjacente. `test_performance_baseline.py` manteve o import de `oracle_extract` após o `sys.path.insert` proposital (não pode ser reordenado) e ganhou `wrong-import-order` no disable inline já existente para `wrong-import-position`.

## [9.5.27] - 04/07/2026
### Adicionado
- **Automação de 4 lacunas operacionais do Orquestrador identificadas em auditoria (crescimento de capacidade/reliability/observability)**: até agora essas quatro situações exigiam alguém olhando o dashboard ou clicando manualmente.
  - **Auto-retry de falhas transitórias**: novo job `enterprise_auto_retry` (a cada 3 min, `app/services/scheduler_runtime.py::auto_retry_transient_failures`) reenfileira automaticamente execuções `ERROR`/`TIMEOUT` com `retry_count < max_retries`, respeitando `cooldown_minutes` da automação como backoff. Reusa `prepare_requeue` (mesma validação de concorrência/queue_group do requeue manual via API), então nunca reenfileira sobre uma execução ativa. Só age em automações com `max_retries > 0` configurado explicitamente — comportamento aditivo, automações sem retry configurado continuam exigindo intervenção manual como antes.
  - **Alertas de incidente de infraestrutura fora do dashboard**: `app/notifications.py::send_infra_alert` (WhatsApp/e-mail, cooldown fixo de 30 min por componente) é disparado a partir do `slo_breaches` já calculado a cada 5 min pelo job `enterprise_system_health_snapshot` (`_dispatch_infra_alerts_from_payload`), cobrindo `worker_offline`, `wal_critical` e `orphaned_running` — situações que antes só apareciam no payload de diagnóstico consumido pelo Dashboard, exigindo alguém olhando a tela para perceber o worker caído ou o WAL travado.
  - **SLA breach tracking**: `sla_minutes` (cadastrado por automação desde a v5.0 mas nunca comparado contra a duração real) ganhou checagem ativa. `diagnostic_collectors.collect_sla_breaches` compara `duration_seconds` das execuções finalizadas nas últimas 24h contra `sla_minutes`; `diagnostic_checks.check_sla_breaches` gera finding `WARN`; payload de `/api/system/diagnostics` ganhou `sla_breaches: DiagnosticsSlaBreach[]` e `slo_breaches.sla_breached`.
  - **Sinal de saturação do pool de workers**: `worker.py` passou a rastrear (`_track_pool_saturation`) há quanto tempo contínuo o pool de `MAX_WORKERS` threads está 100% ocupado, publicando `pool_saturated_seconds` no heartbeat (`WorkerHeartbeat.pool_saturated_seconds`, migração `20260704_01`). `diagnostic_checks.check_worker_saturation` gera finding `WARN` quando a saturação contínua ultrapassa 300s (`DIAGNOSTIC_WORKER_SATURATION_WARN_SECONDS`), dando sinal antecipado de que `WORKER_MAX_CONCURRENCY` pode estar insuficiente para o catálogo atual, antes que vire fila envelhecida.
  - Testes: `test_scheduler_runtime_unit.py` (auto-retry: reenfileira dentro do limite, respeita cooldown, ignora automação desabilitada, não reenfileira acima do max_retries, ignora conflito de concorrência; dispatch de alertas de infra a partir do payload), `test_notifications.py` (`send_infra_alert`: envio, throttle, ausência de canais, reset), `test_worker_saturation_unit.py` (novo arquivo: tracking de streak de saturação), `test_diagnostics.py` (SLA breach/dentro do limite, saturação de worker).

## [9.5.26] - 03/07/2026
### Adicionado
- **Fase 3 (parcial) do plano de melhoria de QA — property-based testing, performance baseline e regressão visual**. `requirements-test.in`/`.txt` ganharam `hypothesis` e `pytest-benchmark`; `pytest.ini` ganhou o marcador `benchmark`. `Orchestrator/tests/test_beneficiamento_property.py` (13 propriedades reais de `beneficiamento/core/`: `to_float`, `safe_text`, `round_or_zero`, `time_efficiency`, `weighted_average`, `first_present`, `normalize_shift` — o plano original citava 3 exemplos que não correspondiam ao código real). `Orchestrator/tests/test_performance_baseline.py` (4 benchmarks dentro do orçamento: `build_diagnostics_payload`, `portfolio_catalog._build_portfolio_summary`, `schemas.parse_schedule`, `oracle_extract.serialize_rows`); job `benchmark` não-bloqueante adicionado ao CI, publica `benchmark-results.json`. 4 testes de regressão visual em `test_e2e_dashboard.py` (`/painel`, `/observabilidade`, `/automacoes`, `/beneficiamento`) com baseline em `docs/playwright-screenshots/baseline/` e comparação por diff de histograma de pixels (PIL, tolerância 5%) — cria o baseline na primeira execução, compara nas seguintes.
### Não implementado (decisão documentada)
- **F3-T1 (mutation testing com `mutmut`)**: a ferramenta se recusa a rodar nativamente no Windows (exige WSL), incompatível com o toolchain Windows-first deste projeto. Rodar em um job `ubuntu-latest` dedicado é tecnicamente viável (os módulos-alvo são lógica pura) mas não foi configurado nem validado por falta de ambiente Linux para testar localmente nesta sessão.
- **F3-T5 (threshold de cobertura 90%)**: cobertura medida ficou em 82.71%, essencialmente igual à Fase 2 — os testes de propriedade/benchmark reforçam lógica já coberta, não adicionam cobertura de linhas novas. Chegar a 90% exigiria uma frente própria de testes nos módulos com menor cobertura (`telemetry.py`, `beneficiamento_refresh.py`, `metrics.py`, `websocket.py`), fora do escopo natural desta fase. Threshold mantido em 82%.

## [9.5.25] - 03/07/2026
### Adicionado
- **`diff-cover` no job de PR, fechando a Fase 2 do plano de melhoria de QA**: `requirements-test.in`/`.txt` ganharam a dependência `diff-cover`; o job `testes-python` do CI (`.github/workflows/governanca.yml`) passou a fazer checkout com `fetch-depth: 0` (necessário para comparar contra o SHA base do PR) e, apenas em eventos `pull_request`, roda `diff-cover coverage.xml --compare-branch=<base sha> --fail-under=85` — exige 85% de cobertura só nas linhas alteradas pelo PR, sem penalizar código legado ainda sem teste. Relatório em markdown publicado no step summary do GitHub Actions e como artefato.

## [9.5.24] - 03/07/2026
### Adicionado
- **F2-T2 do plano de melhoria de QA: Vitest + Testing Library no Dashboard React**. `Dashboard/vitest.config.ts` (ambiente jsdom, `include` restrito a `src/__tests__/**/*.test.{ts,tsx}`); `Dashboard/package.json` ganhou `test`/`test:watch`/`test:coverage`; job `frontend` do CI (`.github/workflows/governanca.yml`) ganhou o passo `npm test` entre ESLint e o build. 4 arquivos de teste novos (54 cenários): `format.test.ts` (`lib/format.ts` — `formatDuration`, `formatAge`, `formatNumber`, `formatPercent`, `successRate`, `shortId`), `status.test.ts` (`lib/status.ts` — mapeamento de tom/badge: `executionTone`, `severityTone`, `healthTone`, `slaTone`, `criticalityTone`, `healthLabel`), `client.test.ts` (`api/client.ts` — `qs`, `setApiKey`/`getApiKey`, tratamento de erro HTTP não-ok) e `useApiKey.test.ts` (`hooks/useApiKey.ts` — persistência via `sessionStorage`, incluindo o caso negativo de que a chave *não* vai para `localStorage`). O plano original descrevia 5 arquivos para conceitos que não existem no Dashboard atual (parser de schedule, badges CAT/DRIFT/DOCS, `action_code`, KPI de beneficiamento, `localStorage`) — o escopo foi corrigido para testar a lógica real e testável do módulo.

## [9.5.23] - 03/07/2026
### Adicionado
- **Fase 2 (backend) do plano de melhoria de QA implementada**: threshold de cobertura elevado de 77% para 82% em `.github/workflows/governanca.yml` (cobertura medida: 82.66%, 358 testes). 5 arquivos de teste novos/ampliados: `test_worker_integration.py` (`run_task`/`main_loop` — guard de status, dispatch, backoff de fila cheia; documenta que `run_task` não bloqueia reentrada para um exec_id já `RUNNING`, mitigado na prática pelo `UPDATE` atômico de `claim_next_task`), `test_notifications.py` ampliado com 13 cenários (escalada de cooldown, eviction LRU de `_alert_state`, dispatch por canal, paths de erro de WhatsApp/e-mail — a idempotência do ADR-013 vive no PowerShell de `Receitas Bloqueadas`, não neste módulo, então os testes de idempotência de canal do plano original não se aplicavam aqui), `test_oracle_circuit_breaker.py` (pybreaker + stamina: abertura, half-open, fechamento, retry transitório), `test_portfolio_catalog_unit.py` (31 cenários das funções puras de scoring/drift/SLA/health), `test_scheduler_runtime_unit.py` (24 cenários, incluindo `app/runtime.trigger_worker_wakeup` que o plano atribuía erroneamente a `scheduler_runtime.py`) e `test_conftest_coverage.py` (auditoria dinâmica que varre `app/**/*.py` para garantir que todo módulo que importa `SessionLocal` diretamente está patchado na fixture `client`).
### Corrigido
- **`list_scheduled_jobs` (`app/services/scheduler_runtime.py`) quebrava com `TypeError` ao ordenar jobs agendados**: a lista misturava `next_run_time` já formatado como string BR (`schemas.ScheduledJob.apply_br_format`) com `None` (jobs sem próxima execução), e o sort comparava `str < datetime.max` — erro que só não se manifestava nos testes porque eles nunca iniciam o `BackgroundScheduler` de verdade (todos os `next_run_time` ficavam `None` uniformemente). Corrigido ordenando pelo `next_run_time` bruto do APScheduler via chave `(has_run_time, valor)`, que nunca compara tipos incompatíveis. Descoberto ao escrever `test_list_scheduled_jobs_resolve_nome_da_automacao`.
- **`make_oracle_retry` (`lib/python/oracle_retry.py`) tipava `reset_timeout` como `int`**, embora o valor seja comparado como segundos fracionários pelo `pybreaker`; alterado para `float` (compatível com todos os chamadores existentes).

## [9.5.22] - 03/07/2026
### Adicionado
- **Fase 1 do plano de melhoria de QA (`docs/qa-improvement-plan.md`) implementada**: `Orchestrator/tests/conftest.py` ganhou 4 fixtures reutilizáveis ausentes até então — `mock_popen` (subprocess.Popen padronizado), `reset_worker_globals` (reseta `shutdown_event`/`wakeup_event`/`log_buffer`/`stats` do `worker.py` entre testes), `mock_requests_worker` (mock de `requests.get`/`post` para o wakeup listener e log flusher) e `mock_oracle_connection` (mock de `oracledb.connect` para os 4 scripts de extração que usam `lib/python/oracle_extract.py`). `pytest.ini` ganhou `--strict-markers` (marcador com typo agora falha em vez de passar silencioso). 5 arquivos de teste novos cobrindo comportamento antes sem cobertura: `test_worker_core_unit.py` (`_force_kill`, `_build_subprocess_env`/allowlist, caps de `_drain_process_output`, guard de status de `_finalize_execution`, `update_stat`, `scan_for_artifacts`, `broadcast_log`), `test_worker_monitor_unit.py` (timeout, término pelo usuário, shutdown, intervalo de checagem do banco — usa `time-machine` para congelar o relógio em vez de esperar minutos reais), `test_worker_wakeup_unit.py` (backoff exponencial do `wakeup_listener_loop`, retry único do `log_flusher_loop`), `test_oracle_extract_unit.py` (fetch em lotes, serialização, hash determinístico, credenciais) e `test_worker_security.py` (audita que `_ALLOWED_ENV_KEYS` nunca inclui segredos como `ORACLE_READONLY_PASSWORD`). Dependência `time-machine` adicionada a `requirements-test.in`/`.txt`. Suite completa: 275 testes, cobertura 80.34% (gate: 77%).
- **F1-T7 do plano (health check obrigatório antes do job E2E) avaliado e não implementado**: a premissa do GAP-12 estava desatualizada — a fixture `uvicorn_server` (`Orchestrator/tests/test_e2e_dashboard.py`) já sobe seu próprio subprocesso Uvicorn e levanta `RuntimeError` com stdout/stderr se o servidor não responder em 5s, então não há "skip silencioso" a corrigir. O job `testes-e2e` do CI também não depende de nenhum servidor pré-existente na porta 8000, então o `curl http://127.0.0.1:8000/health` proposto no plano quebraria o job sem necessidade.

## [9.5.21] - 03/07/2026
### Corrigido
- **Menções do WhatsApp não notificavam o contato de verdade (OBP-04 e demais automações que usam `lib/WhatsApp-Core.js`)**: `extrairOpcoesMensagem()` montava o array de `mentions` concatenando `@c.us` direto no número discado (`<numero>@c.us`), sem consultar o WhatsApp para saber qual é o ID de registro real daquele contato. Números brasileiros frequentemente têm um ID interno que não bate com o número discado (contas antigas sem o 9º dígito, ou identidade LID em contas mais novas) — o resultado, confirmado em disparo real, era o WhatsApp renderizar a menção como texto de telefone formatado em vez de uma menção real que notifica o contato. Substituído por `resolverMencoes(client, caption)` (assíncrona): consulta `client.getNumberId(numero)` — que faz `QueryExist` contra o servidor do WhatsApp — para obter o `wid` real de cada número citado na legenda antes de montar `mentions`; se o `wid.user` resolvido divergir do número discado, o texto visível da legenda é ajustado para que o `@` bata com o ID mencionado de verdade (caso contrário a menção não renderiza mesmo com o array `mentions` correto). Números não registrados no WhatsApp (`getNumberId` retorna `null`) geram apenas um aviso de log, sem quebrar o envio. Os 4 pontos de disparo em `lib/WhatsApp-Core.js` (mensagem única com anexo, mensagem única só texto, lote e retry de lote) foram atualizados para `await resolverMencoes(...)`. Contrato reforçado em `Receitas Bloqueadas/tests/whatsapp-offline.test.js` (exige `resolverMencoes`/`getNumberId`, proíbe o helper síncrono antigo).

## [9.5.20] - 03/07/2026
### Alterado
- **OBP-04 (OBs Paradas Fase) migrado de matching por palavra-chave para matching 100% por código de fase**: o controle de responsável/threshold por fase era feito por substring no texto de `FASE_ATUAL`, causando colisões entre fases cujo texto compartilha a mesma substring — ex.: fase 26 (`IVF-INVERSÃO P/FELPAGEM`) e fase 65 (`FEL-FELPAGEM`) caíam ambas na keyword `"FELPAGEM"`, atribuindo o responsável errado à fase 26. `SQL-ObsParadasFase.sql` passou a expor `OBF.CODIGO_FASE` (já usado no JOIN, nunca selecionado). `config.json` foi redesenhado: as antigas seções `threshold_por_fase`/`responsaveis_por_fase`/`ordem_fases`/`filtros_por_fase` (chave = palavra-chave) deram lugar a uma única seção `fases_monitoradas` (chave = `CODIGO_FASE` exato, valor = objeto `{descricao, ativo, threshold_dias, responsavel}` — o campo `descricao` documenta a fase Oracle correspondente para manutenção visual, sem uso pelo código) mais `filtros_por_codigo_fase` e `ordem_codigos_fase`. Levantamento das 17 fases hoje monitoradas feito via consulta temporária (não versionada) em `SGTPRD.FASES_FLUXO`/`OB_FASES`/`OB` (mesmo padrão de `SQL-ObsParadasFase.sql`). `generate_phase_cards.py`/`format_message.py`: `get_threshold`/`get_responsavel`/`ResponsavelConfig`/`ThresholdConfig` foram removidos e substituídos por `get_fase_config`/`FaseConfig` (lookup exato, sem loop de substring); agrupamento de OBs por fase (`_group_obs`/`_group_and_sort`) passou a usar `CODIGO_FASE` (int) como chave em vez do texto normalizado; `_apply_phase_filter` e a ordenação de exibição (`_phase_sort_key`/`ordem_codigos_fase`) também migraram para código exato. Corrigidos dois achados colaterais descobertos pela consulta: fase 160 (`CDQ-CONTROLE DE QUALIDADE`, keyword `CQ` nunca batia por não ser substring de `CDQ`) e fase 165 (`CDF-CONFERÊNCIA DE FELPA`, não coberta por nenhuma keyword) agora usam explicitamente a equipe de qualidade (`equipe_cq`). O campo `ativo` (booleano, default `true`) em cada entrada de `fases_monitoradas` permite desligar o monitoramento de uma fase específica sem removê-la do arquivo (`FaseConfig.ativo`; checado em `_filter_obs` logo após o lookup por código) — necessário porque mapear todas as fases Oracle por código passou a incluir fases que podem não precisar de alerta no WhatsApp. `ordem_codigos_fase` deixou de ser uma lista de códigos (`[20, 46, ...]`) e virou um objeto `{codigo: descricao}` (ex.: `"20": "RMC-REVISÃO MALHA CRUA"`), para permitir reorganizar a ordem de exibição olhando a descrição da fase, sem precisar cruzar com `fases_monitoradas`. Cobertura em `Orchestrator/tests/test_obs_paradas_fase.py` (`test_get_fase_config_resolve_por_codigo_exato`, `test_fase_inativa_e_excluida_do_envio`, `test_codigo_fase_key_normaliza_tipos_oracle`, `test_config_json_valido` estendido).
- **Números de responsável centralizados em `contatos` (variáveis nomeadas), `fases_monitoradas.responsavel` deixa de ter números literais**: `config.json` ganhou a seção `contatos` (chave = nome da variável, valor = objeto `{nome, numero}` para contato único ou lista desses objetos para equipe) com os 7 papéis atuais — `lider_1_turno`, `lider_reserva_1_turno`, `lider_2_turno`, `lider_reserva_2_turno`, `lider_3_turno`, `lider_reserva_3_turno` e `equipe_cq` (lista de 3 contatos). Cada entrada de `fases_monitoradas.responsavel` agora referencia o nome de uma dessas variáveis (ex.: `"responsavel": "lider_3_turno"`) em vez de um número de telefone direto — trocar o número de um papel em um único lugar (`contatos`) propaga automaticamente para todas as fases que o usam. `generate_phase_cards.py`/`format_message.py` ganharam `_resolve_contato()` (resolve objeto/lista/string legada para o formato `"num1 @num2"` já usado no envio) e `_load_config` passou a montar o dicionário de `contatos` antes de resolver cada `responsavel` (com fallback para tratar o valor como literal se não bater com nenhuma chave de `contatos`, por segurança). Números corrigidos para o formato completo com o nono dígito móvel. Fase 25 (`CDP-CONFERENCIA DE PESO`) desativada (`ativo: false`) por decisão de negócio — não fazia parte do mapeamento de turnos fornecido. Cobertura: `test_resolve_contato_aceita_objeto_lista_e_string_legada`, `test_config_real_resolve_contatos_por_variavel`, `test_config_json_valido` estendido para exigir que todo `responsavel` exista em `contatos`.
- **`ordem_codigos_fase` ajustada para agrupar por responsável**: sequência de envio no WhatsApp definida como `20, 26 (lider_3_turno) → 45 (lider_reserva_3_turno) → 46, 50, 55, 60 (lider_1_turno) → 65, 70, 80 (lider_reserva_1_turno) → 90, 100, 110 (lider_2_turno) → 150 (lider_reserva_2_turno) → 160, 165 (equipe_cq)`, a pedido do negócio. Fase 25 (inativa) removida de `ordem_codigos_fase` por não fazer parte dessa sequência.

## [9.5.19] - 02/07/2026
### Alterado
- **Revisão de arquitetura do canal WhatsApp implementada por completo**: as dependências Node do motor soberano (`whatsapp-web.js`, `qrcode-terminal`) migraram de `Receitas Bloqueadas/node_modules` para `lib/package.json`/`lib/node_modules`, eliminando a dependência invertida em que a biblioteca compartilhada `lib/` dependia de uma automação de domínio específica. `Receitas Bloqueadas/package.json` perdeu as dependências do motor (mantém apenas o script de teste offline). Todos os pontos que resolviam `NODE_PATH` via `Receitas Bloqueadas/node_modules` (`lib/Send-WhatsApp.ps1`, `lib/Keep-WhatsApp-Open.ps1`, `lib/Authenticate-WhatsApp.bat`, `Tools/Get-WhatsAppGroups.ps1`) passaram a apontar para `lib/node_modules`.
- **Caminho único de invocação do motor WhatsApp**: `lib/Send-WhatsApp.ps1` (v2.3) ganhou suporte ao modo `BATCH` (`-BatchInputFile`/`-BatchResultFile`); `OBs Paradas Fase/run.ps1` deixou de invocar `lib/WhatsApp-Core.js` diretamente via `node.exe` e passou a delegar ao wrapper, herdando a limpeza de locks/processos zumbis (`Clear-StaleWhatsAppLocksAndProcesses`) antes indisponível nesse fluxo.
- **`docs/architecture-standard.md` ganhou a seção "Canal WhatsApp — Sessão Única e Concorrência"**, documentando que os exit codes `40` (lock ativo) e `23` (cooldown) são comportamento normal de serialização sobre a sessão compartilhada `hub-global`, não falha.

### Removido
- **`Receitas Bloqueadas/sendWhatsApp.js` (motor legado v1.3.0) removido**: não fazia parte do fluxo de produção (usava sessão/`clientId` próprios, desconectados de `hub-global`) e só era mantido vivo por `whatsapp-offline.test.js`, que agora valida exclusivamente o contrato de `lib/WhatsApp-Core.js`. Referências obsoletas atualizadas em `.github/references/runbook-operacao.md`, `.github/skills/nodejs-communications/SKILL.md` e `OBs Paradas Fase/CONTEXT.md`. (`.vscode/tasks.json` também foi corrigido localmente, mas esse arquivo é ignorado pelo git — não faz parte deste commit.)

### Adicionado
- **Validação de `whatsapp-config.json` no preflight de automações** (`Orchestrator/app/services/automation_preflight.py`, função `_whatsapp_config_issues`): quando o manifesto declara o canal `whatsapp`, o preflight passa a exigir `auth.clientId` (string não vazia) e `target.type`/`target.contactId` coerentes (`contact` → sufixo `@c.us`, `group` → sufixo `@g.us`) antes de permitir `create`/`update` da automação, em vez de falhar apenas em runtime no disparo real. Cobertura em `Orchestrator/tests/test_automations_crud.py` (`test_preflight_blocks_missing_whatsapp_config`, `test_preflight_blocks_invalid_whatsapp_config_schema`).

## [9.5.18] - 02/07/2026
### Corrigido
- **Falso-negativo silencioso em `Test-PythonGovernance.ps1` quando invocado com `-Paths` externo**: chamar o script como processo separado via `pwsh -File Test-PythonGovernance.ps1 -Paths @("a.py","b.py")` fazia o parser de CLI do próprio `pwsh.exe` (modo `-File`) descartar silenciosamente todos os elementos do array após o primeiro, validando apenas `a.py` e reportando sucesso sem sequer mencionar `b.py`. O pipeline de produção (`ValidarAutomacoes.ps1`, usado pelo pre-commit hook e pelo CI) não é afetado — sempre invoca via operador `&` in-process, que faz o binding correto do array. Adicionado comentário de alerta no script documentando a limitação (nunca invocar via `-File` para múltiplos arquivos) e um split defensivo que recupera o caso em que os caminhos chegam colapsados em uma única string separada por vírgula.

## [9.5.17] - 02/07/2026
### Adicionado
- **Menção automática do responsável por fase no WhatsApp (OBP-04)**: `config.json` ganhou o mapa `responsaveis_por_fase` (número ou lista de números por fase); `generate_phase_cards.py` (`get_responsavel`, mesmo padrão de matching por substring de `get_threshold`) acrescenta `Responsável: @<numero>` à legenda de cada card. `lib/WhatsApp-Core.js` ganhou `extrairOpcoesMensagem()`, que extrai os números `@digitos` da legenda e monta o array `mentions` do whatsapp-web.js (`<numero>@c.us`), aplicado nos três pontos de envio (single, batch, retry). Fases com múltiplos responsáveis (`CONFERENCIA`, `CQ`) unem os números com `" @"` para gerar múltiplas menções na mesma mensagem.

### Corrigido
- **`contactId` do grupo de destino do OBP-04 corrigido** em `whatsapp-config.json` (grupo antigo estava incorreto); teste `test_whatsapp_config_valido` (`Orchestrator/tests/test_obs_paradas_fase.py`) ajustado para aceitar também o formato `<telefone>-<timestamp>@g.us` usado por esse grupo, além do formato numérico puro já suportado.
- **Tipagem estrita (mypy `--strict`) na cadeia de `_load_config`**: `_load_config`/`_build_card_entry` em `generate_phase_cards.py` agora propagam `responsaveis: dict[str, str]` explicitamente.

## [9.5.16] - 02/07/2026
### Corrigido
- **Ícone de alerta do card OBP-04 não renderizava**: o caractere Unicode `⚠` usado em `generate_phase_cards.py` para OBs urgentes não existe na fonte Arial Bold usada para desenhá-lo, aparecendo como um retângulo vazio ("tofu") — visível em produção. Substituído por um triângulo de alerta desenhado com primitivas do PIL (`_draw_urgency_icon`, mesmo padrão já usado para a bolinha nova/permanente), sem depender de cobertura de glifo de fonte alguma.
- **`.gitignore` sem `obs_seen_state.json`**: o arquivo de estado de OBs vistas (introduzido na v9.5.15) não estava na lista de "Estados runtime por automação", arriscando ser versionado por engano. Adicionado ao lado das demais entradas de `OBs Paradas Fase/`.

### Alterado
- **Card OBP-04 ganhou sublinha para Cliente + Entrega, sem aumentar a altura da linha**: `OB_ROW_H` permanece `42` — a linha 1 mantém posição/fonte de sempre (OB, kanban, dias, alerta, pcs, kg, descrição completa do produto, agora sem truncar na maioria dos casos); Cliente (Nome Fantasia) + Entrega migraram para uma sublinha menor (fonte 10pt) encaixada no espaço ocioso que já existia dentro dos 42px da linha, sem crescer o card.
- **Mensagem visível "⏳ _Verificando canal..._" removida do envio em lote do OBP-04**: `healthCheckCanal()` (`lib/WhatsApp-Core.js`) enviava uma mensagem de probe visível no grupo de WhatsApp antes de cada lote de imagens, poluindo o histórico do canal. Removida a função (sem outros chamadores) e a chamada no modo `BATCH`; `verificarEstadoConectado()` (sem mensagem visível) continua garantindo que o cliente está `CONNECTED` antes do envio. Escopo confirmado: modo `BATCH` é usado exclusivamente pelo `run.ps1` do OBP-04, nenhuma outra automação é afetada.

## [9.5.15] - 02/07/2026
### Alterado
- **Agendamento OBP-04 (OBs Paradas Fase) revisado para 05:30, 14:00 e 22:30/23:00**: horário anterior (`30 5,14,22 * * *` → 05:30, 14:30, 22:30 todo dia) mudou para 05:30 e 14:00 fixos, com o terceiro disparo às 22:30 de Segunda a Sábado e 23:00 aos Domingos. Um único cron 5-campos não expressa minuto/hora dependentes do dia da semana, então `schedule_type=cron` ganhou suporte a `cron_expression` como lista (`["30 5 * * *","0 14 * * *","30 22 * * 0-5","0 23 * * 6"]`), cada expressão virando um `CronTrigger` independente em `_register_schedule` (`Orchestrator/app/services/scheduler_runtime.py`) — extraído para `_register_cron_schedule` para não estourar o limite de variáveis locais do pylint. **Pegadinha descoberta e documentada**: `CronTrigger.from_crontab` (APScheduler) numera dia-da-semana como `0=Segunda...6=Domingo`, diferente da convenção Vixie/cron tradicional (`0=Domingo...6=Sábado`) — por isso "Segunda a Sábado" é `0-5` e "Domingo" é `6`, não `1-6`/`0` como um cron tradicional sugeriria. Corrigido também um bug pré-existente (não introduzido nesta mudança, mas que impedia validar a correção acima) em `_preview_cron_runs`: o preview de "próximas execuções" repetia o mesmo horário `count` vezes porque `get_next_fire_time` era chamado sem `previous_fire_time`, fazendo o trigger devolver o mesmo instante já retornado quando ele coincidia com `now`. Retrocompatível: `cron_expression` como string única continua funcionando exatamente como antes (id de job e descrição textual inalterados); os 33 testes de `test_schedule_advanced.py` + suíte completa (221 testes) seguem verdes. Atualizado via `PUT /api/automations/4` após restart do Orchestrator (fonte de verdade é o registro no banco, não o manifesto); `automation.manifest.json`, `README.md` e o runbook de OBP-04 atualizados como documentação.
- **Rodapé do card OBP-04 mostra contagem de OBs distintas**: `generate_phase_cards.py` acrescenta `{N} OBs` antes de pcs/kg no rodapé de cada card de fase, calculado por `set` de `NUMERO_OB` (defensivo contra duplicatas).
- **Card OBP-04 exibe nome fantasia do cliente e indicador novo/permanente**: `SQL-ObsParadasFase.sql` ganhou join até `PESSOASFJ.NOMEFANTASIA` (via `PEDIDOCOMERCIAL.IDFILIALRESPONSAVEL`); `generate_phase_cards.py` desenha o nome do cliente entre kg e Entrega (fontes da linha reduzidas de 14/13 para 13/12 para preservar espaço da descrição do produto) e uma bolinha antes do número da OB (verde = nova, cinza = permanente), com estado persistido em `obs_seen_state.json` entre execuções.

## [9.5.14] - 02/07/2026
### Corrigido
- **Conflito `isort`/`ruff` em `routers/system.py` resolvido na raiz**: o bloco de imports de `env_admin`, `scheduler_runtime` e `system_runtime` misturava nomes aliasados (`as`) com não-aliasados do mesmo módulo — `isort` e `ruff` (regra I001) discordavam de forma irreconciliável sobre a ordenação (testadas 4 variações anteriormente, nenhuma satisfazia as duas). Substituído por import de namespace (`from ..services import env_admin, scheduler_runtime, system_runtime`) e chamadas qualificadas (`system_runtime.get_worker_status(...)`, `env_admin.validate_env_content(...)`, etc.) nos 11 call sites afetados. Elimina o aliasing por completo — sem colisão de nome possível, os dois linters convergem. Os aliases eram necessários porque o router tem funções locais com o mesmo nome semântico do serviço (ex.: rota `get_worker_status` vs serviço `get_worker_status`); a qualificação por módulo resolve isso sem precisar de alias. 221 testes seguem verdes (cobrem `/health`, `/metrics`, `/worker/status`, `/scheduler/jobs`, `/env`, `/backup`); `black`/`isort`/`ruff`/mypy `--strict`/pylint 100% limpos.

## [9.5.12] - 02/07/2026
### Corrigido
- **`metrics.py` reclassificado**: a falha de `black` neste arquivo **não** era dívida pré-existente (confirmado: limpo em `main`) — era a minha própria edição da Onda 1 (renomear a rota para `/metrics/prometheus`), cuja linha de log ficou longa demais. Corrigido quebrando a chamada em múltiplas linhas, sem tocar mais nada do arquivo. `database.py`, `main.py` e `routers/system.py` permanecem com a dívida pré-existente, tratada separadamente em PR dedicada (`chore/lint-debt-black-isort`).

## [9.5.11] - 02/07/2026
### Corrigido
- **`black`/`isort` do job `Lint Python` (CI)**: os 10 arquivos Python autorados nesta sessão (novos ou majoritariamente reescritos: `lib/python/oracle_extract.py`, os 3 scripts de extração migrados, `processar_receitas.py`, `services/execution_decoration.py`, `services/execution_runtime.py`, `routers/executions.py`, `conftest.py`, `test_purge_retention.py`) foram formatados com `black`/`isort` para satisfazer o gate do CI, que checa o arquivo inteiro (não só as linhas alteradas). `database.py`, `main.py`, `metrics.py` e `routers/system.py` — onde a mudança real foi de 1-2 linhas — foram deliberadamente **revertidos** para a formatação original: rodar `black` neles reformatava dezenas de linhas pré-existentes não relacionadas (dívida de lint já conhecida no `main`, ver `feedback_governance_contracts`/`project_lint_format_debt`); `Lint Python` segue vermelho nesses 4 arquivos por essa dívida pré-existente, não por regressão desta PR.

## [9.5.10] - 02/07/2026
### Alterado
- **Extração Oracle deduplicada em `lib/python/oracle_extract.py`**: o núcleo repetido nos 4 scripts de extração (resolver credenciais/thick mode, `fetchmany` em lotes, normalizar datetime/strings, hash sha256 para idempotência) foi extraído para um módulo compartilhado (`resolve_oracle_credentials`, `init_thick_mode`, `fetch_all`, `serialize_rows`, `compute_hash`, `read_last_hash`, `write_state_tmp`). `Receitas Emitidas/extract_oracle.py`, `OBs Paradas Fase/extract_obs.py` e `Montagem de Terceirizados/extract_oracle.py` migrados; cada script mantém seu próprio perfil de retry, ordenação e contrato de idempotência (MT continua sem idempotência, por exemplo).
- **`Receitas Bloqueadas/processar_receitas.py` alinhado ao `init_oracle_thick_mode` de `lib/python/oracle_client.py`**: eliminada a duplicação de `oracledb.init_oracle_client(...)` inline (achado da revisão de arquitetura).

Validação: comparação byte-a-byte da serialização nova vs. antiga sobre o **mesmo** dataset em memória (evitando falso-negativo por dados de produção mudarem entre execuções) para RE, OBP e MT — hash e `dict` idênticos nos três. Os 3 scripts fetchmany-based e o `processar_receitas.py` rodados de ponta a ponta contra o Oracle de produção (readonly, autorizado pelo usuário). Corrigido durante a migração: MT usava `dsn` fixo `"dbprd"` ignorando `ORACLE_CONNECT_STRING` — preservado via novo parâmetro `force_dsn` em `resolve_oracle_credentials` (sem essa correção o DSN teria mudado silenciosamente). `tests/test_montagem_terceirizados.py` atualizado (mock de `oracledb.connect` migrou para `oracle_extract.oracledb.connect`).

## [9.5.9] - 02/07/2026
### Alterado
- **Polling do Dashboard unificado em `usePolling`**: `AutomacoesPage.tsx` e `ExecucoesPage.tsx` reimplementavam `setInterval`/`useEffect` manualmente em vez de usar o hook já existente. `usePolling` ganhou um parâmetro opcional `deps` que força refresh imediato (reinicia o intervalo) quando muda — necessário para refiltrar/paginar sem esperar o próximo tick. Validado via Playwright contra a API real: listagem, filtro por status, drawer de detalhe, paginação e cards de automação com badges de criticidade.
- **`ExecucoesPage.tsx` reduzido de 382 para ~270 linhas**: `ExecDetailBody`/`KV` (drawer de detalhe da execução) extraídos para `ExecucoesPage.ExecDetailBody.tsx`.

## [9.5.8] - 01/07/2026
### Alterado
- **Lógica de negócio extraída de `routers/executions.py`**: o pipeline de decoração operacional (ações do operador, atenção) mudou para `app/services/execution_decoration.py`; as regras de validação/concorrência do requeue (execução ativa, grupo operacional, limite de retry, prioridade) mudaram para `prepare_requeue()` em `app/services/execution_runtime.py`, que levanta `RequeueValidationError` (status HTTP + mensagem) e o router só converte para `HTTPException`. Router reduzido de ~772 para ~620 linhas; nenhuma rota, contrato de resposta ou comportamento mudou (221 testes permanecem verdes).

## [9.5.7] - 01/07/2026
### Adicionado
- **Marcadores pytest aplicados**: `Orchestrator/tests/conftest.py` ganhou `pytest_collection_modifyitems` que classifica automaticamente cada teste como `unitario` ou `integracao` conforme o uso das fixtures `client`/`db_session` (já declaradas em `pytest.ini`, mas nunca aplicadas). Agora `pytest -m unitario`/`-m integracao` funcionam para rodar subconjuntos.

### Corrigido
- **`PYTHONPATH` do `Test-PythonGovernance.ps1` não incluía `Orchestrator/`**: pylint falhava com `E0401: Unable to import 'app'` ao lintar qualquer arquivo de `Orchestrator/tests/` isoladamente (ex.: hook `-StagedOnly` com um único arquivo de teste no diff), pois `Orchestrator/tests/` não tem `__init__.py` e o pacote `app` só era resolvido quando outro arquivo de `Orchestrator/app/` estava no mesmo lote do pylint. `Orchestrator/` foi adicionado ao `PYTHONPATH` do script (já constava no `MYPYPATH`).

## [9.5.6] - 01/07/2026
### Alterado
- **CI consolidado em pipeline único**: `.github/workflows/ci.yml` removido; suas responsabilidades foram absorvidas por `governanca.yml` (que já rodava nos mesmos eventos com actions pinadas por SHA e permissões mínimas). O `ruff check` bloqueante agora roda no job `lint-python` (Python 3.12). Elimina execução duplicada de Gitleaks, pytest e build do Dashboard e a divergência Python 3.11 vs 3.12; o gate de cobertura (77%) passa a valer para todo push/PR. Docs atualizadas (`CLAUDE.md`, `docs/testing-strategy.md`).

## [9.5.5] - 01/07/2026
### Corrigido
- **Rota Prometheus inacessível**: `GET /api/system/metrics` estava duplicada (JSON + Prometheus no mesmo path); o endpoint Prometheus movido para `GET /api/system/metrics/prometheus`.
- **Wake-up do worker não thread-safe**: `trigger_worker_wakeup()` setava `asyncio.Event` a partir de endpoints sync (threadpool); agora usa `loop.call_soon_threadsafe` com o loop registrado no lifespan (`register_event_loop`).
- **Purge não cumpria contrato**: `purge_old_executions` agora preserva as últimas 50 execuções por automação (janela `ROW_NUMBER`), como o docstring e o contrato operacional de `POST /api/system/purge` prometiam; coberto por `tests/test_purge_retention.py`.
- **Kill cirúrgico quebrado na Infrastructure**: `Start-Orchestrator.ps1` e `Recover-Orchestrator.ps1` filtravam `Get-Process` por `CommandLine` (propriedade inexistente no PS 5.1); a limpeza agora usa `Get-CimInstance Win32_Process` via novo módulo `lib/Lib-OrchestratorRuntime.psm1`.

### Alterado
- **Versão de runtime unificada na Infrastructure**: strings hardcoded (v9.3.0/v5.2/v6.2.0) substituídas por `Get-OrchestratorRuntimeVersion`, que lê `ORCHESTRATOR_VERSION` de `Orchestrator/app/constants.py`.
- **Parser de `.env` deduplicado**: `MonitorAutomacoes.ps1` e `Diagnose-Orchestrator.ps1` passam a usar `Get-OrchestratorEnvValue` do módulo compartilhado.

## [9.5.13] - 02/07/2026
### Corrigido
- **Dívida de `black`/`isort` sanada em `main.py` e `database.py`**: não passavam no job `Lint Python` do CI (`black --check`/`isort --check-only`), embora nenhum teste/mypy/pylint/ruff fosse afetado. Reformatados com o mínimo de ruído: comentários `# pylint: disable=...` que ficaram desalinhados da linha reportada após o rewrap do `black` foram reposicionados manualmente para preservar a supressão `import-outside-toplevel`. 219 testes seguem verdes.

### Fora de escopo (decisão de política pendente)
- **`Orchestrator/app/routers/system.py` excluído desta PR**: `isort` e `ruff` (regra I001) discordam de forma irreconciliável sobre a ordenação de um bloco de imports com aliasing misto (`from ..services.env_admin import a, b, c` vs `from ..services.env_admin import d as e`). Testadas múltiplas variações (merge, split total por nome, `--combine-as`) — nenhuma satisfaz os dois simultaneamente. Requer decisão de qual ferramenta é autoritativa (ou refatoração maior removendo o aliasing) antes de reformatar este arquivo.

## [9.5.4] - 01/07/2026
### Alterado
- **Revisão das skills (drift)**: `python-enterprise-standard` passa a exigir o lint bloqueante do CI (`ruff check`), migrações exclusivamente via Alembic e `session_scope` fora do FastAPI; `enterprise-orchestration-contract` inclui `OBs Paradas Fase/` como padrão de entrypoint; `html-css-enterprise-standard` reconhece a SPA React+TS+Vite (`Dashboard/src/`) como UI ativa, mantendo o template legado validado; skill `/preflight` ganha etapa de ruff antes do black.

## [9.5.3] - 01/07/2026
### Alterado
- **Agendamento OBP-04 (OBs Paradas Fase)**: cron alterado de "Seg-Sex às 07:00 e 14:00" para "Todos os dias às 05:30, 14:30 e 22:30" (`0 7,14 * * 1-5` → `30 5,14,22 * * *`), passando a rodar também nos finais de semana.

### Adicionado
- **Data Entrega no card OBP-04**: `SQL-ObsParadasFase.sql` agora traz `DT_ENTREGA` (via novo CTE `ENTREGA_OB`, agregando a maior data de expedição entre os itens de pedido vinculados à OB) e o card de imagem exibe "Entrega: dd/mm" ao lado de peças/kg em cada linha de OB.

## [9.5.2] - 30/06/2026
### Adicionado
- **Resiliência do Motor WhatsApp (v2.7.0)**:
  - **Health-Check Pré-Envio**: Probe de texto de 30s (`⏳ _Verificando canal..._`) que aborta execuções em canais degradados antes de acumular timeouts de mídias pesadas.
  - **Retry por Fase**: Reenvio automático de mídias uma vez na mesma sessão em caso de timeout de ACK.
  - **Circuit-Breaker de Proteção**: Aborta imediatamente o lote se ocorrerem 2 falhas consecutivas de ACK (após retries), reduzindo tempo de espera em sessões quebradas.
  - **Soma de Peças no Rodapé (OBP-04)**: Inclusão do somatório do campo `QT_PECAS` à esquerda do total de quilos parados no rodapé do card da automação (ex: `64 pcs · 1.050 kg parados`).
  - **Layout Compacto de Linha Única (OBP-04 v1.3.0)**: Condensação de todas as informações de cada OB (número, kanban, dias, alternativo, produto, peças e kg) em uma única linha contínua, reduzindo a altura do card à metade com truncamento inteligente com reticências para produtos longos.

### Alterado
- **Limpeza de Zumbis Segura**: Substituída a limpeza indiscriminada no `Send-WhatsApp.ps1` por `Clear-StaleWhatsAppLocksAndProcesses`, que mata apenas processos zumbis do diretório `Automacoes` com mais de 10 segundos de idade e limpa arquivos LOCK residuais, garantindo integridade de concorrência.

## [9.5.1] - 30/06/2026
### Corrigido
- **Bug de tipo em `timezone.py`**: `to_br_timezone()` declarava `-> datetime` mas retornava `None`; corrigido para `-> datetime | None`.
- **Caminho absoluto em `New-Automation.ps1`**: placeholder hardcoded no template de runbook substituído por `$BasePath` portável.
- **Manifest OBP-04 redundante**: removido `script_path` duplicado no nível raiz (já existia em `orchestrator.script_path`).

### Adicionado
- **Campo `schedule` nos manifests**: MT-02, RB-01 e RE-03 agora incluem cron JSON estruturado (mesmo formato do OBP-04), eliminando inconsistência entre automações.
- **`Produção Beneficimento/CONTEXT.md`**: documentação da arquitetura snapshot-first, última automação que faltava CONTEXT.

### Alterado
- **Version bump v9.3.6 → v9.5.0**: README, CONTEXT, constants.py, ai-native-context-monitor e 6 docs de governança atualizados para refletir a versão operacional corrente.

## [9.5.0] - 21/06/2026
### Alterado
- **Nova identidade visual do Dashboard — "Sala de Instrumentação"**: redesign completo do frontend React com identidade industrial (grafite + sistema de sinais ciano/âmbar/verde/vermelho onde cor codifica significado), família tipográfica IBM Plex (Sans Condensed / Sans / Mono) e cantos de instrumento. Substitui a antiga "Sala de Controle" âmbar-sobre-preto.
- **Design system de componentes** (`Dashboard/src/components/ui/`): primitivos reutilizáveis (Button, Card, Nameplate, StatusTag, StatTile, DataTable, Drawer, ConfirmModal, Toast, Feedback) e componentes de assinatura (Mímico Operacional, Anunciador, Gauge SVG, Sparkline, TimeSeries via uPlot) com CSS Modules e tokens centralizados (`styles/tokens.css`) — fim dos inline styles dispersos.
- **Roteamento por URL real** (`react-router-dom`): rotas `/painel /execucoes /observabilidade /beneficiamento /automacoes /sistema` com deep-link e histórico; barra de status global ao vivo no topo (estado do sistema, fila, worker, sinal WebSocket).
- **Inteligência operacional à frente**: scoring de atenção do operador (severidade/score), status de SLA, lanes de fila e criticidade passam a ser exibidos; Execuções com ações contextuais (Reenfileirar/Parar) e drawer de detalhe com visor de logs.
- **Beneficiamento real**: página deixa de despejar JSON cru e passa a mostrar saúde do snapshot, seletor de período, KPIs e rankings.
- **Camada de dados reconciliada** (`Dashboard/src/api/orchestrator.ts`): cliente tipado alinhado às rotas reais do Orchestrator (`/start`, `/pause`, `/resume`, `/stop`, `/requeue`, `system/overview|history|baseline`), corrigindo chamadas defasadas.
- **Acessibilidade**: contraste de tokens revisado (WCAG AA), foco visível (ciano), focus-trap em modais/drawer, skip-link e layout responsivo até mobile; `prefers-reduced-motion` respeitado.

### Adicionado
- **SPA fallback no `RevalidatedStaticFiles`** (`Orchestrator/app/main.py`): requisições 404 sob `/dashboard` caem em `index.html`, habilitando deep-links do react-router em recarga de página.

### Removido
- **Frontend vanilla legado**: `Dashboard/js/**` (~4.800 LOC) e `Dashboard/css/dashboard.css` (1.976 linhas), inertes desde que `dist/` passou a ser autoritativo. Removido também o `eslint.config.mjs` da raiz (obsoleto; o Dashboard tem o seu próprio).

### CI/Governança
- **Gate de frontend renovado**: jobs `js-quality` (`ci.yml`) e `frontend` (`governanca.yml`) passam a instalar, lintar e **buildar** o projeto React em `Dashboard/` (tsc + vite), em vez do antigo `eslint` sobre `Dashboard/js`. O `lint:js` da raiz delega para o lint do Dashboard.
- **Detecção de alvos**: `Tools/Get-GovernanceTargetSummary.ps1` e `Tools/Test-SourceEncoding.ps1` passam a reconhecer `.ts`/`.tsx` (e `.mjs`/`.cjs`), garantindo que mudanças no Dashboard acionem o gate e a checagem de encoding (UTF-8 sem BOM).

## [9.4.1] - 19/06/2026
### Alterado
- **Limpeza de Caches e Resíduos**: Aplicação segura da política de retenção do repositório via `Tools/AplicarPoliticaRetencao.ps1`, removendo diretórios de cache locais (`__pycache__` e `.mypy_cache`) sem afetar arquivos de ambiente, dados locais ou arquivos versionados pelo Git.
- **Validação Completa de Governança**: Executado o ciclo de validações estáticas locais (`Tools/ValidarAutomacoes.ps1`) e testes de contrato de comunicações offline (`Tools/Test-NodeCommunications.ps1`) obtendo 100% de sucesso.
- **Ajuste de Timeout no Bridge do WhatsApp**: Aumento do limite de tempo para confirmação de recebimento (ACK) de mensagens de 60 segundos (30 tentativas) para 180 segundos (90 tentativas) em `lib/WhatsApp-Core.js` e `Receitas Bloqueadas/sendWhatsApp.js`, além do ajuste correspondente no teste de contrato offline, mitigando falhas espúrias em conexões lentas ou congestionadas.

## [9.4.0] - 15/06/2026
### Adicionado
- **Beneficiamento ao vivo**: refresh contínuo near-real-time substitui o batch espaçado. Jobs APScheduler `beneficiamento_live_diario` (~90s) e `beneficiamento_mensal_rollup` (~10min) reprocessam em subprocesso isolado (Oracle nunca abre no processo web), respeitando o corte de ~20s do DB. Intervalos configuráveis por `BENEFICIAMENTO_LIVE_INTERVAL_SECONDS` e `BENEFICIAMENTO_MENSAL_INTERVAL_SECONDS`.
- **Refresh on-demand**: endpoint `POST /api/beneficiamento/refresh?period=diario|mensal` e botão "Atualizar agora" no dashboard, com auto-refresh (~60s) na aba visível e debounce reativo nos filtros de texto.

### Alterado
- **Períodos enxutos**: Beneficiamento mantém apenas `diario` e `mensal`; `semanal` e `anual` (e o template `anual.sql` com fatiamento mensal) foram removidos.

### Removido
- **Análises sem relevância**: contrato `analytics` legado (`/api/beneficiamento/historico/analytics`, `contracts/analytics.py` e schemas `BeneficiamentoAnalytics*`); geração/serviço do artefato `*.profile.json` (profiling segue em memória apenas para o quality gate).
- **Legado do Orquestrador**: redirects `/api/health` e `/api/metrics` (use `/api/system/*`) e o stub `services/beneficiamento_dashboard.py`.

## [9.3.20] - 13/06/2026
### Alterado
- **Contratos de agentes padronizados**: `AGENTS.md`, `CLAUDE.md` e `GEMINI.md` local unificados em hierarquia coesa com referências cruzadas explícitas e sem contradições.
- **CLAUDE.md promovido a contrato de repositório**: reescrito em PT-BR, elevado ao nível 3 da ordem de precedência junto com `GEMINI.md`, incluído na sequência de bootstrap obrigatório.
- **Princípios comportamentais canônicos**: seção "Princípios Comportamentais" adicionada em `AGENTS.md` como fonte única dos 4 princípios (Pensar Antes de Executar, Simplicidade Primeiro, Mudanças Cirúrgicas, Execução Orientada a Metas) aplicáveis a todos os agentes.
- **Resolução de conflito formalizada**: regra explícita adicionada à ordem de precedência de `AGENTS.md` para casos em que simplicidade de código colide com governança/documentação.
- **GEMINI.md global alinhado**: `CLAUDE.md` adicionado à lista de contratos locais na ordem de precedência; `ai-engineering-discipline` global ganhou cross-reference para os princípios canônicos de `AGENTS.md` em `C:\Automacoes`.

## [9.3.19] - 12/06/2026
### Adicionado
- **Núcleo compartilhado do Beneficiamento**: criado `beneficiamento/core` para coerções, aliases de campos, normalização de turnos e métricas reutilizáveis.
- **Camada tipada de histórico**: criado `beneficiamento/data` com schema declarativo, escrita idempotente por `executemany` e consultas que leem colunas SQLite sem reabrir o blob JSON por padrão.
- **Contratos históricos canônicos**: `beneficiamento/contracts` contém a implementação SQLite de overview, detalhe e analytics; `overview_v1.py` permanece apenas como fachada de compatibilidade.
- **Health testável**: adicionada máquina de estado explícita para precedência de saúde dos snapshots, com cobertura unitária.
- **Sessão segura do Orchestrator**: adicionado `session_scope()` para rollback e fechamento garantidos em worker, scheduler e jobs internos.
- **Serviço de broadcast**: criado `LogBroadcaster` como implementação única de agrupamento, emissão e preview de logs WebSocket.

### Alterado
- **Schema v2 do histórico**: bases antigas são recriadas deterministicamente e devem ser recarregadas pelo runner retroativo; `DADOS_COMPLETOS` permanece apenas para auditoria e `include_raw=true`.
- **Hot path do worker**: `run_task()` foi dividido em início, monitoramento e finalização sem alterar estados, exit codes, alertas ou eventos WebSocket.
- **WAL periódico não bloqueante**: checkpoints agendados usam `PASSIVE`; `TRUNCATE` permanece restrito ao startup/recovery.
- **Broadcast de logs consolidado**: endpoints unitário e em lote compartilham a mesma rotina de emissão para WebSocket.
- **Governança arquitetural do histórico**: a allowlist de SQLite reconhece explicitamente os três módulos autorizados de `beneficiamento/data`, mantendo acesso direto bloqueado fora da camada.
- **Teste Oracle determinístico**: o mock de extração de Montagem de Terceirizados configura corretamente o context manager da conexão, eliminando loop infinito em `fetchmany`.

## [9.3.18] - 10/06/2026
### Alterado
- **Fatiamento adaptativo do refresh Oracle do Beneficiamento**: a geração de snapshots passou a dividir automaticamente períodos pesados em subfaixas mensais e, se necessário, em intervalos menores quando o Oracle retorna timeout ou `ORA-00028`, mantendo cada consulta dentro do orçamento imposto pelo DBA.
- **Refresh mensal estabilizado**: o snapshot mensal foi regenerado com sucesso após o fatiamento adaptativo, reduzindo o risco de derrubar a sessão Oracle por excesso de tempo de execução.

## [9.3.17] - 10/06/2026
### Alterado
- **Health do Beneficiamento mais explícito**: o bloqueio de quality agora expõe causas específicas, como `quality_missing_required_columns`, `quality_critical_nulls` e `quality_duplicate_keys`, em vez do rótulo genérico `quality_blocked`.
- **Snapshot semanal reprocessado**: o snapshot semanal foi regenerado com o runner atual, reduzindo o bloqueio de qualidade no período semanal e alinhando o contrato ao template operacional vigente.

## [9.3.16] - 10/06/2026
### Alterado
- **Causa primária explícita no health do Beneficiamento**: `GET /api/beneficiamento/health` agora escolhe de forma determinística o `reason_code` e a `recommended_action` a partir da issue mais grave do conjunto, evitando `attention` genérico quando já existe um motivo operacional mais forte.
- **Cobertura de prioridade de issues**: adicionada validação de que, quando coexistem snapshot ausente e snapshot stale, o health aponta a causa mais grave primeiro e preserva a trilha de ação recomendada.

## [9.3.15] - 10/06/2026
### Alterado
- **Resumo temporal do quality gate local**: `Tools/ValidarAutomacoes.ps1` agora publica o modo de seleção governada e a duração por etapa do ciclo local, preservando o gate atual e adicionando visibilidade objetiva para fast path, conformidade de log, governança nativa, skills e dashboard template.
- **Exportação opcional do ciclo local**: o validador passa a aceitar `-SummaryJsonPath` para persistir um resumo JSON com contagens, seleção aplicada e tempos medidos sem depender de parsing textual do console.

## [9.3.14] - 10/06/2026
### Alterado
- **Telemetria aditiva do Orchestrator**: `GET /api/system/diagnostics` e `GET /api/system/overview` passam a expor `performance.timings_ms` com custo de montagem por etapa, sem quebra de contrato e sem dependência nova.
- **Hotspots internos simplificados**: a montagem de diagnósticos e overview foi decomposta em helpers menores para fila, checks de runtime, execuções recentes e cards de automação, reduzindo duplicação entre consulta, agregação e serialização.

## [9.3.13] - 08/06/2026
### Adicionado
- **Colunas derivadas no histórico do Beneficiamento**: o SQLite local passa a manter `TURNO_ID`, `TURNO_LABEL`, `MAQUINA_KEY`, `FASE_KEY` e `CODIGO_KEY`, com backfill idempotente em `init_db` para acelerar filtros operacionais sem reabrir Oracle.
- **Cobertura de schema do Beneficiamento**: adicionada validação automatizada para garantir colunas derivadas e índices idempotentes do histórico local.

### Alterado
- **Overview V1 otimizado**: `GET /api/beneficiamento/overview` deixa de usar `date(DATA_FIM)` no filtro principal, materializa um conjunto filtrado temporário por request e reaproveita esse recorte para KPIs, rankings, turnos, Tingimento e séries diárias.
- **Filtro indexado do Beneficiamento**: buscas por data, turno, máquina, fase e código operacional passam a usar colunas persistidas/normalizadas compatíveis com índice, eliminando `SCAN` no recorte principal por data.
- **Carga progressiva da aba Beneficiamento**: o frontend passa a proteger contra respostas antigas, aplicar debounce curto nos filtros e renderizar status/KPIs antes das tabelas e gráfico pesados.

## [9.3.12] - 07/06/2026
### Adicionado
- **Padrão Arquitetural Governado**: criado `docs/architecture-standard.md` como contrato oficial de camadas, severidades e validação arquitetural do Hub.
- **Validador de Arquitetura**: criado `Tools/Test-ArchitectureStandard.ps1`, com saída humana/JSON, suporte a `-Paths`, severidade gradual e falha apenas para violações críticas no v1.
- **Ruleset Arquitetural Versionado**: criado `Tools/architecture-standard.rules.json` para manter allowlists e seções documentais obrigatórias fora do script executor.
- **Cobertura Pester do Validador**: adicionados testes para cenário saudável, violação Oracle em router FastAPI, aviso de `subprocess`, contrato JSON, `-Paths` direcionado, path externo, comentário com Oracle e ruleset ausente.

### Alterado
- **Quality Gate**: `Tools/ValidarAutomacoes.ps1` passa a executar o validador arquitetural dentro da governança nativa.
- **Escopo e Segurança do Validador**: `Test-ArchitectureStandard.ps1` passa a bloquear `-Paths` fora da raiz, respeitar validação direcionada para automações e reduzir falsos positivos de Oracle em comentários de endpoints GET.
- **Documentação Viva**: README, CONTEXT, monitor AI-Native, diretrizes de governança e README de Tools passam a apontar para o padrão arquitetural oficial.

## [9.3.11] - 31/05/2026
### Adicionado
- **Beneficiamento V1 com drill-down**: criado `GET /api/beneficiamento/detail` para abrir detalhe por produto, máquina/fase, fase, turno e OB, com resumo operacional, rastreabilidade por OB, paginação e `raw_records` opcional.
- **Controle operacional por turno**: `/api/beneficiamento/overview` passa a expor a seção `turnos`, com volume, eficiência, reprocesso, produtividade e médias por turno.
- **Bloco dedicado de Tingimento**: `/overview` agora entrega `tingimento.summary`, série diária e rankings por Alternativo e máquina, suportando análise mais elaborada da fase `03 - TINGIMENTO`.

### Alterado
- **Beneficiamento V1 operacional**: a aba passa a usar `Alternativo` como eixo principal de produto, adiciona filtro próprio de Alternativo e abre modal local ao clicar em produto, turno, gargalo, fase ou OB.
- **Normalização de turno no SQLite**: a leitura do histórico e do overview deixa de depender de `turno`/`TURNO` legados e passa a priorizar `TURNO_DESC` e `TURNO_PROD`, eliminando o colapso indevido em `Indefinido`.
- **Rastreabilidade enriquecida**: `/historico` continua compacto, mas agora já retorna turno normalizado para apoio operacional.

## [9.3.10] - 31/05/2026
### Adicionado
- **Contrato V0 de Beneficiamento**: criado `GET /api/beneficiamento/overview` como contrato principal da aba, com `generated_at`, `filters.effective`, `health`, `kpis`, `rankings`, `series` e `filter_options`.
- **Janela efetiva por SQLite**: quando datas não são informadas, `/overview` usa 30 dias encerrados em `MAX(DATA_FIM)` da base histórica local, evitando dependência da data do sistema.
- **Testes de contrato V0**: adicionada cobertura para resposta mínima, filtros, recorte vazio com `health.status=no_data` e proteção contra dependência de runner/Oracle no endpoint de leitura.

### Alterado
- **Beneficiamento operacional enxuto**: a aba foi refeita como tela única para PCP diário, com status da base, filtros essenciais, 8 KPIs, série volume/eficiência, gargalos por máquina/fase, produtos principais, fases críticas e rastreabilidade compacta de OB.
- **Eficiência de tempo**: a UI deixa de tratar o indicador como OEE completo e passa a exibir o proxy V0 `MIN_PREV / MIN_REAL * 100`.
- **Documentação viva**: README, arquitetura, runbook de refresh e monitor AI-Native foram alinhados ao novo contrato `/overview` e à permanência de `/historico`.

### Removido
- **Ornamentos analíticos da aba**: removidos da experiência V0 pódio de operadores, setup estimado por regra fixa, painéis técnicos de profiling/qualidade e destaques isolados de artigos/cores.

## [9.3.9] - 31/05/2026
### Adicionado
- **Análise Dinâmica de Produtos e Artigos**: criada a tabela dinâmica de produtos na tela (`index.html`) e o painel lateral de top artigos e cores de maior representatividade.
- **Filtros Cruzados Avançados**: adicionada a barra de filtros cruzados no frontend (busca textual de produtos/artigos e dropdowns dinâmicos de Máquina, Fase e Turno).
- **Agregação Multidimensional `fato_producao`**: implementada função `build_fato_producao` no backend (`analytics.py`) e integrada na montagem de payloads (`beneficiamento_dashboard.py`), pré-agregando dados brutos do Oracle em chaves combinadas compactas para máximo desempenho de filtros locais no navegador.

### Alterado
- **Métricas e Rankings Vivos**: ao interagir com os filtros dinâmicos, o dashboard agora recalcula e atualiza instantaneamente os 8 KPIs principais (linhas, volumes, rendimento, eficiência) com animações de contagem, além de re-renderizar e reordenar as tabelas de ranking de máquinas e fases baseando-se no recorte selecionado.
- **Evidências de Homologação**: criados scripts de simulação para injeção de dados ricos em snapshots locais de DX, com validação de 100% de sucesso na suite de testes E2E do Playwright (`8 passed`) e conformidade estrita de encoding.

## [9.3.8] - 31/05/2026
### Alterado
- **Refatoração Premium do Beneficiamento**: unificação completa e revitalização visual do dashboard de beneficiamento em `index.html`, `dashboard.css` e `dashboard_beneficiamento.js`.
- **KPIs e Insights Unificados**: os 8 slots numéricos (Linhas, KG, MT, Turnos, Rendimento, Eficiência, Desvio e Qualidade) foram integrados em uma única fileira de cards premium, com estilo moderno (glassmorphism sutil, bordas de acento por categoria), animações sequenciais de stagger de entrada e contagem progressiva (`count-up`) de 0 até o valor formatado.
- **Micro-interações e Visualização ApexCharts**: os gráficos ApexCharts foram atualizados para usar bordas arredondadas nas colunas, preenchimentos gradientes com curvas suaves nas linhas e legendas refinadas integradas à paleta escura do orquestrador.
- **Rankings Interativos**: as tabelas de ranking de máquinas e fases ganharam medalhas estilizadas no pódio top 3 (🥇, 🥈, 🥉) e barras de progresso horizontais inline com o percentual de share de volume.
- **Limpeza de Informações Técnicas (Accordions)**: o painel detalhado de integridade/qualidade de dados e o profiling técnico de snapshot (estruturas e colunas) foram movidos para painéis expansíveis (accordions) inteligentes e discretos no final da view, mantendo o foco operacional limpo.

### Corrigido
- **Conformidade de Qualidade e Testes**: validação de integridade do console e comportamento do dashboard realizada por meio da suíte completa de testes E2E do Playwright (`8 passed`) e verificação estática de encoding sem ocorrência de erros.

## [9.3.7] - 31/05/2026
### Adicionado
- **Beneficiamento Snapshot-First**: estruturado o domínio `Produção Beneficimento/` com pacote Python modular, SQLs parametrizadas, snapshots promovidos e documentação operacional própria.
- **API de Produção do Beneficiamento**: adicionados contratos Pydantic e endpoints `/api/beneficiamento/health`, `/api/beneficiamento/periods` e `/api/beneficiamento/periods/{period}`, mantendo `/dashboard` compatível.
- **Testes de Contrato**: criada cobertura para leitura de snapshots, health com `call_timeout` não aplicado e validação de período inválido.

### Alterado
- **Dashboard Beneficiamento**: a aba passa a exibir status operacional e idade do snapshot por período.
- **Segurança Oracle**: leituras `GET` do Beneficiamento não abrem conexão Oracle; refresh fica restrito a runner controlado com orçamento abaixo de 20 segundos.

### Removido
- **Artefatos Temporários do Beneficiamento**: planejada limpeza direta de `analysis_tmp/`, `__pycache__/`, outputs locais e JSONs exploratórios após promoção dos snapshots finais.

## [9.3.6] - 2026-05-27
### Adicionado
- **Governança Semântica**: criado `Tools/Test-SemanticGovernance.ps1` para bloquear drift entre monitor AI-Native, constantes do runtime, documentação viva, taxonomia de skills, mapa de criticidade e dependências Node versionadas.
- **Teste Offline de Node/WhatsApp**: criado `Tools/Test-NodeCommunications.ps1` e `Receitas Bloqueadas/tests/whatsapp-offline.test.js`, permitindo validar o contrato do canal WhatsApp sem depender de sessão real, Puppeteer, internet ou credenciais.
- **Cobertura de Runtime e Bibliotecas**: adicionados testes de sanitização/truncamento, finalização de execuções e contratos de `Lib-Config`/`Lib-Retry`, elevando a suíte do Orchestrator para 165 testes e a cobertura para 81%.

### Alterado
- **Documentação Viva Alinhada**: README, CONTEXT, quality dashboard, estratégia de testes, mapa de cobertura, segurança, release checklist e mapa de criticidade passam a refletir o baseline atual e os manifestos como fonte operacional.
- **Runtime Versionado**: `ORCHESTRATOR_VERSION` e `WORKER_VERSION` avançam para `9.3.6`.
- **Governança Python Mais Real**: removidos ignores globais de `pylint`/`mypy` em `constants.py` e `security.py`.

### Corrigido
- **Drift do Catálogo Operacional**: cadências do mapa de criticidade foram sincronizadas com os `automation.manifest.json`.
- **Higiene Node na Raiz**: removido `package-lock.json` órfão da raiz sem `package.json` correspondente.

## [9.3.5] - 2026-05-27
### Adicionado
- **Classificador Compartilhado de Diff Governado**: criado `Tools/Get-GovernanceTargetSummary.ps1` como fonte única para classificar caminhos alterados, detectar escalonamento para scan completo e identificar alvos elegíveis de conformidade de log no hook local e no GitHub Actions.

### Alterado
- **Contrato do Pre-commit Reposicionado**: `Tools/ValidarAutomacoes.ps1` agora consome o classificador compartilhado, mantém o gate local focado em staged files, preserva o fallback para scan completo em caminhos críticos e roda `Test-LogConformidade.ps1` apenas quando o diff realmente altera scripts PowerShell operacionais elegíveis.
- **Workflow Governanca Alinhado ao Hook**: `.github/workflows/governanca.yml` passa a publicar o resumo do diff governado, expondo `selection_mode`, quantidade de caminhos críticos e o motivo operacional para execução ou skip de `conformidade-log`.
- **Documentação Viva Corrigida**: monitor AI-Native, política de segurança e diretrizes de governança foram alinhados ao estado real do pipeline, removendo a leitura incorreta de que o hook espelha todo o CI ou de que `conformidade-log` estaria desativado quando aparece em branco.

### Corrigido
- **Catálogo Direcionado com Caminho Unitário**: `Tools/Test-AutomationCatalog.ps1` passa a normalizar o conjunto de manifestos como coleção mesmo quando o diff contém apenas um caminho, evitando falha espúria no modo `-Paths` usado pelo gate staged.

## [9.3.4] - 2026-05-27
### Adicionado
- **Agente de Revisão de Código (Declarativo estruturado)**: migrado o Agente de Revisão de Código de um markdown solto na raiz para uma pasta estruturada autocontida de agente de verdade declarativo em [.agents/agents/code-review-agent/agent.json](.agents/agents/code-review-agent/agent.json), consolidando regras de qualidade de encoding, Zero Trust, V.A.L.E.G., prompt completo e formato de data brasileira (`DD/MM/YYYY`).
- **Ferramenta de Auditoria Local**: criada a ferramenta utilitária `Tools/Review-Code.ps1` (UTF-8 com BOM) para execução rápida e cirúrgica de validação estática de staged files diretamente pelo terminal, gerando pareceres Markdown formatados de feedback por gravidade (`INCIDENTE`, `ATENÇÃO`, `MELHORIA`).

### Alterado
- **Otimização Extrema de Pre-commit (DX)**: o orquestrador `Tools/ValidarAutomacoes.ps1` foi inteiramente reestruturado e otimizado. Adicionado o switch `-StagedOnly` para auto-resolução nativa em PowerShell de arquivos staged, eliminando dependências externas UNIX no hook do Git. O Pytest pesados de homologação e Playwright E2E agora são pulados sob o switch `-OnlyGovernance` do pre-commit. O tempo total de commit local foi reduzido de dezenas de segundos para menos de 2 segundos.
- **Detecção de Dependências em Cadeia**: implementada inteligência de fallback global em `ValidarAutomacoes.ps1`. Modificações que afetam arquivos críticos de infraestrutura ou governança (`lib/`, `Tools/`, contratos) revertem automaticamente para scan completo do repositório para evitar quebras em cadeia.
- **Portabilidade do Git Hook**: o hook `.githooks/pre-commit` foi simplificado e reconfigurado para delegar nativamente a resolução de staged files para o PowerShell via `-StagedOnly`, removendo comandos Unix de manipulação de string (`tr`, `sed`) incompatíveis com IDEs em ambiente Windows.
- **Governança do Catálogo Direcionada**: `Tools/Test-AutomationCatalog.ps1` foi atualizado para aceitar o parâmetro `-Paths`, permitindo auditar estaticamente apenas os manifestos e runbooks que sofreram modificações.

## [9.3.3] - 2026-05-26
### Adicionado
- **Governança de Datas e Contrato de Não Regressão**: criado o validador especializado `Tools/Test-DateConformidade.ps1` e integrado diretamente no Quality Gate soberano (`Tools/ValidarAutomacoes.ps1`). Ele audita e proíbe de forma automatizada regressões de datas ISO-8601 (`YYYY-MM-DD`) no corpo de textos de documentações Markdown (`.md`) e chamadas de formatação de exibição/logs em arquivos de código (`.py`, `.js`, `.ps1`), garantindo a preservação eterna do formato brasileiro `DD/MM/YYYY`.
- **Padronização de Documentações**: saneamento geral e promoção de 11 arquivos de documentação operacional ativos na pasta `docs/` para o padrão de data brasileira `DD/MM/YYYY`, eliminando referências a formatos legados ISO-8601.

### Alterado
- **Receitas Bloqueadas / Observabilidade do WhatsApp**: a etapa `Send-WhatsApp.ps1` passou a ser acompanhada pelo orquestrador PowerShell com repasse contínuo do `stdout`, permitindo que bootstrap, ACK e falhas do bridge apareçam online no modal de execução do Orchestrator.

### Corrigido
- **Diagnóstico do Bridge WhatsApp**: `lib/WhatsApp-Core.js` agora serializa melhor falhas de inicialização e protocolo, evitando logs vazios como `undefined` quando o runtime rejeita com payload não padrão.
- **Status Final de Receitas Bloqueadas**: a automação deixa de encerrar com sucesso limpo quando o e-mail conclui, mas o WhatsApp retorna falha de canal; a idempotência parcial do e-mail permanece preservada.

## [9.3.2] - 2026-05-25
### Adicionado
- **Baseline Operacional Unificado**: criado `GET /api/system/baseline`, com resumo objetivo `healthy`, `attention` ou `incident`, ação recomendada e métricas normalizadas para heartbeat do worker, idade da fila, execuções acima do `max_runtime`, ownership órfão e pressão do WAL.
- **Baseline no Histórico Operacional**: `GET /api/system/history` agora expõe `baseline_status`, `baseline_attention_count` e `baseline_incident_count` por snapshot, enquanto `trend_summary` passa a acumular quantos pontos recentes ficaram em atenção ou incidente.
- **Resumo Operacional do Portfólio**: `GET /api/portfolio/health` passa a expor `summary.status`, `healthy_items`, `attention_items`, `incident_items`, `top_issue` e `recommended_action`, elevando drift, documentação obrigatória e runtime sem reconciliação a um sinal operacional consumível.
- **Preflight Governado de Automações**: `POST /api/automations/preflight` passa a retornar `governance` com manifesto detectado, bloqueios, avisos e ação recomendada antes do save administrativo.
- **Smoke Test Inicial no Scaffold**: `Tools/New-Automation.ps1` passa a gerar `Orchestrator/tests/test_<slug>.py` como prova mínima dos artefatos obrigatórios da nova automação.

### Alterado
- **Contrato de Diagnóstico**: `GET /api/system/diagnostics` passa a incluir `operational_baseline` de forma aditiva, mantendo compatibilidade com os consumidores atuais.
- **Overview Principal do Dashboard**: `GET /api/system/overview` agora replica `portfolio` com o resumo governado do catálogo, e o painel principal passa a destacar o risco operacional prioritário combinando baseline e governança do portfólio.
- **Administração de Automações**: a aba `Automações` passa a consumir o catálogo governado para enriquecer o risco da frota com `CAT`, `DRIFT` e `DOCS`, e o modal de revisão exibe quando o save foi bloqueado pelo manifesto canônico.
- **Governança do Catálogo**: `Tools/Test-AutomationCatalog.ps1` agora exige `queue_group`, `smoke_tests`, `owner_area` sem placeholder e `runbook_path` dentro de `docs/runbooks/` para automações ativas.
- **Scaffold Oficial**: `Tools/New-Automation.ps1` agora aceita parâmetros de owner, criticidade, fila, SLA, runtime e dependências básicas, gerando manifesto mais pronto para o contrato governado do Orchestrator.
- **Ferramentas Operacionais**: `Tools/Get-QualitySnapshot.ps1` passou a consultar o baseline live quando a API local estiver disponível, e `Tools/Test-OrchestratorIntegrity.ps1` agora valida explicitamente o contrato `diagnostics + baseline + history + portfolio`.
- **Versionamento do Runtime**: `ORCHESTRATOR_VERSION`/`WORKER_VERSION` avançaram para `9.3.2` e `ORCHESTRATOR_CONTRACT_VERSION` para `2026.05.25.1`.

### Corrigido
- **Vínculo de Automação no Portfólio**: corrigido o preenchimento de `automation_id` nos itens governados do catálogo para sempre refletir a automação reconciliada, eliminando associação residual incorreta durante a leitura agregada do portfólio.

## [9.3.1] - 2026-05-25
### Corrigido
- **Rotina de Limpeza Duplicada no Orchestrator**: corrigida a falha recorrente da automação `Retenção de Arquivos` quando executada pelo worker com `ExecId` posicional. `Tools/AplicarPoliticaRetencao.ps1` agora infere a raiz do repositório quando `-RootPath` não é informado e deixa de interpretar `CRON_*` como caminho inválido.

### Alterado
- **Limpeza de Arquivos como Job Reservado**: `Tools/AplicarPoliticaRetencao.ps1` passa a ser tratado como rotina reservada do sistema. O preflight bloqueia novo cadastro desse script como automação comum e o `reload_scheduled_tasks()` neutraliza o registro legado persistido no banco para manter apenas o job interno `enterprise_file_cleanup`.

## [9.3.0] - 2026-05-24
### Adicionado
- **Catálogo Governado de Automações**: cada automação ativa passa a possuir `automation.manifest.json` como fonte canônica de criticidade, SLA, owner, dependências, smoke tests e caminho operacional do Orchestrator.
- **Portfólio Operacional na API**: novos endpoints `GET /api/portfolio/health` e `GET /api/portfolio/drift` cruzam catálogo versionado, documentação e runtime; `GET /api/portfolio/runbook/{catalog_id}` fornece leitura segura do runbook para a UI.
- **Runbooks Oficiais do Hub**: adicionados os runbooks de `Montagem de Terceirizados` e `Receitas Emitidas`.
- **Smoke de Receitas Emitidas**: criada a suíte `tests/test_receitas_emitidas.py` cobrindo geração HTML mínima da automação.
- **Governança do Catálogo**: criado `Tools/Test-AutomationCatalog.ps1` e integrado ao quality gate agregado.

### Alterado
- **Dashboard Operacional**: o painel principal agora mostra a grade de portfólio governado com criticidade, SLA, docs e drift.
- **Scaffold Oficial**: `Tools/New-Automation.ps1` passa a gerar manifesto canônico e runbook inicial junto do pacote base da automação.
- **Snapshot de Qualidade**: `Tools/Get-QualitySnapshot.ps1` passa a relatar cobertura do catálogo, runbooks presentes, smoke declarado e issues do catálogo.
- **Snapshot de Qualidade Refinado**: a métrica de tamanho agora mede o payload efetivamente versionado no Git e expõe a pegada operacional local como dado auxiliar, evitando falso alerta causado por sessão do WhatsApp, logs e SQLite/WAL locais.
- **Versionamento do Runtime**: `ORCHESTRATOR_VERSION`/`WORKER_VERSION` avançaram para `9.3.0` e `ORCHESTRATOR_CONTRACT_VERSION` para `2026.05.24.2`.

## [9.2.7] - 2026-05-24
### Adicionado
- **Histórico Operacional do Orchestrator**: criada a tabela `system_health_snapshots`, o job `enterprise_system_health_snapshot` com coleta a cada 5 minutos e o endpoint `GET /api/system/history`, permitindo tendência operacional de fila, WAL, heartbeat e violações recentes sem depender apenas de logs.
- **Ownership de Execução no Worker**: execuções `RUNNING` passam a registrar `claimed_at`, `worker_instance_id` e `worker_pid`; o diagnóstico agora identifica `queue.orphaned_running` e diferencia backlog legítimo de execução órfã.
- **Preflight Administrativo de Automações**: novo endpoint `POST /api/automations/preflight` centraliza a validação de `script_path`, agenda, diretório resolvido, `queue_group` e `notification_channels` antes de `create/update`.

### Alterado
- **Contrato de Diagnóstico**: `/api/system/diagnostics` e `/api/system/overview` passam a expor `trend_summary` e `slo_breaches` de forma aditiva, preservando compatibilidade com o Dashboard atual.
- **Mutações Administrativas**: gravações de `.env`, scripts e configs agora retornam `validated`, `backup_path` e `audit_id`, mantendo `backup` por compatibilidade.
- **Scheduler Runtime**: disparos agendados e claims do worker passaram a respeitar concorrência por `queue_group` também no caminho normal de despacho, não apenas no requeue manual.
- **Versionamento do Runtime**: `ORCHESTRATOR_VERSION`/`WORKER_VERSION` avançaram para `9.2.7`, `ORCHESTRATOR_CONTRACT_VERSION` para `2026.05.24.1` e `ORCHESTRATOR_SCHEMA_VERSION` para `20260524_01`.

### Testado
- **Suite completa do Orchestrator**: `pytest tests -q` → `140 passed`.
- **Regressão focada**: `pytest tests/test_automations_crud.py tests/test_queue_rules.py tests/test_system.py tests/test_validation.py -q` e `pytest tests/test_diagnostics.py tests/test_recovery.py tests/test_executions.py tests/test_worker_queue.py tests/test_worker_loop.py -q` → `62 passed`.

## [9.2.6] - 2026-05-22
### Alterado
- **Governança dos Versionados e `.gitignore`**: removido o papel canônico do artefato gerado `docs/playwright-e2e-evidence-generated.md`, mantendo no repositório apenas o padrão e o template de evidência Playwright. O `.gitignore` passa a cobrir explicitamente a evidência gerada e capturas `Logs/playwright-*.png`.
- **Contrato Atual do Dashboard**: skills e documentação deixam de tratar `Dashboard/dashboard.html` como output operacional válido; a shell real permanece em `Dashboard/index.html` e o template canônico em `.github/templates/dashboard-modern.html`.
- **Scaffold de Nova Automação**: `Tools/New-Automation.ps1` foi alinhado ao fluxo atual do Hub, removendo dependências quebradas de `Deprecated\config.json` e `_Template\Trigger_Automation.vbs`. O utilitário agora gera o scaffold mínimo e orienta o cadastro posterior via Dashboard/API do Orchestrator.

## [9.2.5] - 2026-05-22
### Adicionado
- **Reconstrução da Limpeza Segura do Repositório**: `Tools/AplicarPoliticaRetencao.ps1` foi reescrito do zero com modo `-DryRun`, resumo auditável por categoria e guardrails para impedir remoção de itens rastreados pelo Git, caminhos fora do repositório e artefatos preservados por contrato local.

### Alterado
- **Política de Retenção Operacional**: a limpeza automática agora trata separadamente resíduos Python, Playwright, artefatos E2E do Orchestrator, logs/backups expirados, temporários de runtime e estados transitórios por automação, com retenção por idade em vez de exclusão cega.
- **Documentação de Ferramentas**: `Tools/README.md` foi alinhado ao estado real do repositório, removendo a referência obsoleta a `Tools/Legacy_VBA/` e documentando a política conservadora de preservação de `.env`, `.venv`, `.gemini/` e `.wwebjs_auth/`.

## [9.2.4] - 2026-05-22
### Corrigido
- **Hardening do Outlook COM para Assinaturas Inline**: reforcado o fluxo compartilhado de `lib/Lib-Email.psm1` para estabilizar a assinatura padrao antes do envio automatizado. O modulo agora forca `BodyFormat` HTML, aguarda a prontidao do editor, persiste o draft apos carregar a assinatura, registra a contagem de anexos inline, salva novamente apos montar o `HTMLBody` final e executa uma recarga controlada do draft quando a assinatura referencia imagens mas nenhum anexo inline e detectado. O objetivo e reduzir casos de "imagem nao vinculada" em assinaturas que funcionam no envio manual, mas falhavam em automacoes por timing do Outlook COM.

## [9.2.3] - 2026-05-22
### Alterado
- **Reorganização do Contexto AI-Native**: `GEMINI.md` foi simplificado para atuar como contrato local estável de bootstrap, encoding, skills e validação. O histórico operacional curado passa a viver em `docs/ai-native-context-monitor.md`, enquanto o `CHANGELOG.md` permanece como histórico completo e auditável de versões.

## [9.2.2] - 2026-05-22
### Adicionado
- **Disciplina Global de Engenharia com IA**: Formalizada a adoção da skill global `ai-engineering-discipline` como contrato compartilhado entre Codex, Gemini CLI e Antigravity, preservando a precedência dos contratos locais do repositório.

### Alterado
- **Governança de Skills Globais**: `AGENTS.md`, `GEMINI.md` e `Tools/Test-SkillsGovernance.ps1` passam a reconhecer `ai-engineering-discipline` como skill global obrigatória, junto de `protocolo-valeg` e `git-ide-governance-skill`.

## [9.2.1] - 2026-05-22
### Alterado
- **Ajuste na Detecção de Alteração de Receitas Bloqueadas (v2.3.2)**: Modificada a lógica de detecção de alterações da inteligência de estado em `processar_receitas.py` para auditar e marcar receitas modificadas (`MODIFIED` / `⚠ DATA ALTERADA`) exclusivamente quando a data na coluna "Data Bloqueio" for modificada. Alterações na coluna "Data Última Prod." passam a ser desconsideradas para fins de mudança de estado, mitigando alertas redundantes e alinhando o robô ao seu objetivo de negócio principal.

### Testado
- **Validação de Testes Automatizados**: Suite completa pytest com 134/134 testes verdes executada com sucesso após alteração das regras de comparação na inteligência de estado.

## [9.2.0] - 2026-05-22
### Adicionado
- **Decomposição e Modularização de Testes**: Decomposição da suíte monolítica `test_api.py` (~967 linhas) em 4 sub-suítes de testes focadas por domínio de negócio em `tests/` (`test_automations_crud.py`, `test_automations_ide.py`, `test_executions.py` e `test_system.py`), removendo fisicamente o arquivo monolítico do disco para maximizar a testabilidade e isolamento.
- **Robustez Unitária em Alertas e Worker**: Implementação das suítes de testes unitários `test_notifications.py` (throttling e resiliência sintática de envio via subprocesso mockado de PowerShell) e `test_worker_loop.py` (motor concorrente e backoff exponencial sob ociosidade), elevando a confiabilidade do core.
- **Saneamento Físico de Disco**: Inclusão de purga rigorosa e dinâmica de arquivos temporários de banco de dados SQLite (`.db`, `.db-shm` e `.db-wal` gerados sob o PID dos testes) no teardown de fixtures no `conftest.py` e `test_e2e_dashboard.py`.
- **Ajustes de Contratos e Resiliência**: Correção na serialização de hotspots de falha no endpoint de overview `/api/system/overview` mapeando `failures_24h` de forma estrita para `failures` (garantindo compatibilidade retroativa e integridade da SPA) e resolução de colisão de cabeçalhos no router `executions.py`.

### Corrigido
- **Resiliência contra Deadlock de Buffer (Uvicorn)**: Substituição do `subprocess.PIPE` no stdout/stderr do subprocesso Uvicorn dos testes E2E Playwright (`test_e2e_dashboard.py`) por arquivos físicos temporários de log. Isso impede o congelamento do servidor de testes quando o buffer do Windows enche sob tráfego concorrente intenso.
- **Correção de BOM para Compatibilidade do PowerShell**: Conversão do script de governança `Tools/Test-PythonGovernance.ps1` para a codificação estrita `UTF-8 com BOM`, garantindo portabilidade absoluta sob PowerShell 5.1 e resolvendo falhas de validação de encoding.
- **Saneamento Estático e Pylint**: Eliminação de trailing whitespaces órfãos no fixture do Uvicorn e aplicação de `# pylint: disable=no-name-in-module` para falso-positivos em imports dinâmicos Pydantic.

### Testado
- **Suite Completa Consolidada**: Execução de 134/134 testes automatizados (unitários, integração e Playwright E2E) com status 100% verde (0 falhas) em menos de 25 segundos.
- **Quality Gate Geral**: Validação de conformidade estática pelo validador global (`ValidarAutomacoes.ps1`), atingindo status de aprovação total com zero erros de segurança, de encoding, de SQL, de linting e de conformidade de design.

## [9.1.1] - 2026-05-21
### Adicionado
- **Operação Self-Service no Dashboard**: reorganizada a navegação em trilhas explícitas de `Operação` e `Administração`, com foco em bancada de triagem para execuções e fluxo guiado de cadastro operacional.
- **Resumo Derivado para Automações**: `AutomationResponse` e o overview do sistema agora expõem `last_execution_id`, horários da última execução, `last_failure_reason`, `last_recovery_action`, `active_execution_count`, métricas `24h` e `operational_state`.
- **Triagem Derivada para Execuções**: `ExecutionSummary` e `ExecutionResponse` agora expõem `operator_action_label`, `operator_action_hint`, `requeue_allowed`, `requeue_block_reason` e vínculo com execução/grupo relacionado para orientar a operação sem heurística no front-end.
- **Revisão Final no Modal de Automação**: o fluxo de cadastro/edição passou a exigir revisão operacional final com resumo do cadastro, prévia de agenda e impacto antes do save.

### Alterado
- **Painel Operacional**: a tabela de controle passou a exibir contexto operacional pronto para leitura, incluindo resumo de agenda, próxima janela, última execução e estado derivado da automação.
- **Gestão de Automações**: a tabela administrativa agora mostra histórico recente diretamente na listagem e rebaixa JSON/IDE para um bloco visualmente avançado, fora do fluxo principal.
- **Bancada de Execuções**: a tela de execuções ganhou presets operacionais, banner de estado do recorte atual e ações coerentes com o contrato de retry/bloqueio do backend.
- **Bancada de Execuções Compacta**: a coluna `Triagem` passou a ficar silenciosa em execuções `SUCCESS` saudáveis, com `requeue` tratado como ação contextual em `Ações` e cards de triagem exibidos apenas quando houver sinal operacional real.
- **Versionamento do Runtime**: `ORCHESTRATOR_VERSION`/`WORKER_VERSION` avançaram para `9.1.1` e `ORCHESTRATOR_CONTRACT_VERSION` para `2026.05.21.1`.

### Testado
- **Backend focado**: `pytest tests/test_api.py tests/test_api_smoke_critical.py tests/test_api_contracts.py tests/test_worker_queue.py -q` -> `49 passed`.
- **Dashboard E2E**: `pytest tests/test_e2e_dashboard.py -q` -> `3 passed`.

## [9.1.0] - 2026-05-20
### Adicionado
- **Horário de Âncora no Agendamento por Intervalo Periódico**: Introduzido suporte ao campo opcional `anchor_time` (Horário de início/âncora) para a recorrência do tipo `interval`. Permite ao usuário definir a partir de qual horário exato do dia (ex: `08:15`) a cadência periódica (ex: a cada 30 min) deve começar a contar de forma robusta e consistente.
- **Normalização e Validação no Backend**: Implementada a verificação rigorosa via regex `^\d{2}:\d{2}$` do campo `anchor_time` em `normalize_schedule_payload`. Adicionado tratamento tolerante para fallbacks consistentes no modo não-strict.
- **Cálculo Matemático e Determinístico de Próximos Disparos**: Desenvolvida lógica refinada em `preview_next_runs` para computar os múltiplos do intervalo com precisão, considerando tanto âncoras no passado hoje (calculando o primeiro múltiplo estritamente futuro) quanto no futuro hoje (primeiro disparo coincide na própria âncora).
- **Integração Gráfica e Textual no Dashboard**: Adicionado input HTML de tipo `time` (`#f-interval-anchor-time`) e ligados os eventos de renderização dinâmicos. A descrição textual e a pré-visualização das próximas execuções foram estendidas para exibir `, a partir das HH:MM` em PT-BR de forma impecável.
- **Suite Ampliada de Testes Automatizados**: Criada classe de testes `TestAnchorTime` em `test_schedule_advanced.py` cobrindo normalização, descrição humana, fallbacks e preview determinístico com simulação temporal congelada (`monkeypatch` do pytest), elevando a suite pytest para **103/103 testes 100% verdes**.
- **Vinculação do Agendador no APScheduler**: Modificada a função `_register_schedule` em `scheduler_runtime.py` para processar `anchor_time` e injetá-lo programaticamente como `start_date` no `IntervalTrigger` em relação à timezone local `America/Sao_Paulo`.
- **Diagnóstico de RUNNING Acima do Limite**: `/api/system/diagnostics` agora expõe `queue.running_over_runtime` e o check `running_over_runtime`, permitindo que o Dashboard mostre execuções ativas que excederam `max_runtime_minutes`.
- **Alinhamento de Versão Runtime/Contrato**: `constants.py` foi alinhado para `ORCHESTRATOR_VERSION`/`WORKER_VERSION` `9.1.0`, contrato `2026.05.20.1` e schema Alembic ativo `a5b212d4418f`.

## [9.0.0] - 2026-05-20
### Adicionado
- **Migração de Banco de Dados com Alembic**: Transição completa do ecossistema de infraestrutura de banco de dados SQLite para o controle estruturado, versionado e auditável utilizando o Alembic integrado ao SQLAlchemy.
- **Startup Dinâmico e Programático**: FastAPI agora executa programaticamente as migrações até a versão mais recente (`upgrade head`) no evento de startup (`lifespan`), dispensando a execução de comandos manuais CLI por operadores no deploy do servidor.
- **Modo Batch para SQLite**: Configurado o modo batch (`render_as_batch=True`) no ambiente do Alembic (`env.py`), garantindo suporte perfeito e livre de falhas para comandos `ALTER TABLE` que possuem limitações nativas severas na arquitetura SQLite.

### Corrigido
- **Resiliência e Desvio nos Testes In-Memory**: Implementada a verificação dinâmica na função `run_alembic_migrations()` para identificar e desviar silenciosamente a execução do Alembic quando a conexão do banco de dados for `:memory:` (banco em memória de testes do pytest). Isso eliminou concorrências de conexões e instâncias duplicadas do SQLite em memória nas threads secundárias do lifespan do FastAPI durante a suite do pytest.
- **Resolução Dinâmica de URL no env.py do Alembic**: Ajustado o carregamento do `env.py` para respeitar URLs injetadas programaticamente (como o banco de dados temporário físico de testes do Playwright E2E) e blindar a resolução de caminho de `:memory:` contra concatenações relativas a caminhos físicos do Windows (como `<PASTA_PROJETO>\:memory:`), resolvendo o erro `OperationalError: unable to open database file`.
- **Ajuste de Teste E2E do Dashboard**: Refatorada a fixture `setup_test_database` no arquivo `test_e2e_dashboard.py` para estruturar as tabelas do banco de teste físico temporário aplicando as migrações do próprio Alembic (`upgrade head`) em vez de usar `Base.metadata.create_all()`. Isso alinha 100% o ambiente de homologação ao de produção, garantindo que o Uvicorn de teste detecte a tabela `alembic_version` no `head` e não cause colisões de tabelas existentes no startup.
- **Remoção de Tabela Obsoleta**: Saneada a asserção da tabela obsoleta `orchestrator_metadata` no teste de integridade `test_database_schema.py`, uma vez que a tabela foi substituída com sucesso pela tabela nativa `alembic_version` do Alembic.

## [8.0.0] - 2026-05-20
### Adicionado
- **Suíte de Testes com Mocks Resilientes**: Criação dos testes unitários isolados `test_receitas_bloqueadas.py` e `test_montagem_terceirizados.py` cobrindo validação sintática, mocks do banco de dados Oracle Thick Mode e prevenção de efeitos colaterais.
- **E2E Playwright no Dashboard**: Criada suite `test_e2e_dashboard.py` cobrindo a navegação do Dashboard SPA por completo, capturando evidências de console e gerando relatório regulatório automático de homologação (`docs/playwright-e2e-evidence-generated.md`).

### Corrigido
- **Interferência de Variáveis na Suite Pytest**: Implementada a fixture global com `autouse=True` (`force_env_vars`) em `conftest.py` que re-injeta a variável `ORCHESTRATOR_API_KEY` com um valor sintético de teste e o caminho `ORCHESTRATOR_DB_PATH` como `:memory:` antes de cada execução de teste. Isso neutralizou a interferência causada pela importação tardia de robôs de negócio (como `extract_oracle.py`) que executavam `load_dotenv(..., override=True)` sobrescrevendo as chaves de teste pelas de produção, sanando todas as 40 falhas de `403 Forbidden` na suite completa (agora **73/73 testes verdes**).
- **Isolamento de Banco in-memory**: Configurada a injeção do banco em memória SQLite (`os.environ["ORCHESTRATOR_DB_PATH"] = ":memory:"`) no topo absoluto de `conftest.py` com patches sobre `SessionLocal` em múltiplos arquivos de API e serviços.
- **Prevenção de Locks de Logs**: Desviada dinamicamente a gravação de logs físicos no `main.py` e `worker.py` para arquivos de teste específicos (`orchestrator_test.jsonl` e `Worker_test.jsonl`) sob ambiente de teste `pytest`, evitando colisões de arquivos com o runtime de produção ativo.
- **Validação de Governança Local**: Saneado o script do Quality Gate (`Tools/ValidarAutomacoes.ps1`) com codificação `UTF-8 com BOM`, obtendo conformidade perfeita de encodings e aprovação de 100% no validador.

## [7.0.4] - 2026-05-20
### Corrigido
- **Correção nos Alertas de Falha (Orchestrator)**: Refatorado o módulo de notificações do orquestrador (`Orchestrator/app/notifications.py`) para utilizar variáveis de ambiente na passagem de parâmetros ao PowerShell. Isso elimina a falha onde nomes de robô com aspas simples (ex: `Montagem de Terceirizados`) causavam injeção sintática e faziam o PowerShell atribuir indevidamente termos como `"Montagem"` no Cc e `"de"` no Cco (autocompletado pelo Outlook para `"Dener Santos da Silva"`).
- **Encoding de Alertas de Falha**: Corrigido o envio de e-mails em formato ASCII no Orchestrator, adotando codificação UTF-8 completa com suporte a caracteres acentuados PT-BR (como `"Automação"`, `"Horário"`, `"Divergência"`) sem quebras sintáticas ou de caracteres.

## [7.0.3] - 2026-05-19
### Adicionado
- **Homologação Definitiva de Automações**: Homologação completa de todas as 5 automações em lote concorrente no modo de teste global. Todas as execuções obtiveram status de `SUCCESS` com 100% de integridade e estabilidade.
- **Gravação Dinâmica de Logs**: Validação pontual do preenchimento e injeção do campo `"automation_name"` em todas as entradas dos logs estruturados (JSONL) nos robôs.

### [7.0.2] - 2026-05-19
### Adicionado
- **Nome Dinâmico de Automação nos Logs**: Atualizada a biblioteca `lib/Lib-Logging.psm1` para extrair e injetar dinamicamente o nome correto da automação (campo `automation_name`) nas entradas de log JSONL estruturadas, via variável `$script:CurrentAutomationName`.
- **Estabilização da Test Task**: Criado o script físico resiliente `test/run.ps1` para simular execuções em modo sandbox/teste e registrar telemetria.

### Corrigido
- **Falha de Parâmetro de Telemetria**: Removida chamada incorreta ao parâmetro `-ExitCode` em `Close-ExecutionTelemetry` no script `test/run.ps1`, sanando o erro de execução no runtime do PowerShell.
- **Recuperação do Validador de Governança**: Corrigida a função `Invoke-NativeGovernanceCheck` em `Tools/ValidarAutomacoes.ps1` que possuía chaves órfãs e sintaxe quebrada, permitindo a execução robusta dos validadores locais.
- **Saneamento de Encodings**: Saneados os arquivos `.ps1` e `.psm1` afetados para `UTF-8 com BOM`, prevenindo falhas de interpretação de acentuação no PowerShell 5.1.

## [7.0.1] - 2026-05-19
### Adicionado
- **Self-Cleaning Repository:** Integração do script `AplicarPoliticaRetencao.ps1` diretamente no `APScheduler` interno do Orchestrator (job `enterprise_file_cleanup`). A rotina agora roda de forma autônoma (diariamente às 02:00 AM), removendo logs e backups antigos sem intervenção manual, prevenindo alertas de disco cheio.

### Corrigido
- Removida a invocação redundante da API `/api/system/purge` no script PowerShell, consolidando o controle de expurgo do banco de dados exclusivamente na rotina Python do Orchestrator (`enterprise_daily_purge`).

## [7.0.0] - 2026-05-19
### Adicionado
- **Fase 10 (Documentação de Governança)**: Conclusão da Fase 10 com a criação de 4 documentos de governança técnica formalizando o ciclo completo de desenvolvimento e operação do Hub:
  - `docs/development-workflow.md`: Fluxo de branches, convenção de commits semânticos PT-BR, ciclo de qualidade local (black/isort/pylint/mypy/pytest), uso de lockfiles, processo de criação de nova automação e gates obrigatórios antes do push.
  - `docs/testing-strategy.md`: Mapa de cobertura por camada (unit/integration/e2e), suite completa de 65 testes, política de cobertura mínima de 60%, convenções de mock/fixtures e guia de adição de novos testes.
  - `docs/security-policy.md`: Política formal de Zero Trust, mandatos de encoding (UTF-8 BOM para PS1), gestão de segredos, higienizador `sanitize_log_payload`, Gitleaks, autenticação do Dashboard, ciclo de rotação de credenciais e proteção de dados sensíveis.
  - `docs/release-checklist.md`: Checklist completo de promoção de versão: gates de qualidade (tests/lint/governança/segurança), validação E2E Playwright, commit semântico de release, verificação pós-deploy e protocolo de rollback auditado.

## [6.9.0] - 2026-05-19
### Adicionado
- **Fase 9 (Dashboard Operacional)**: Conclusão da Fase 9 com evolução significativa do Dashboard Operacional e da camada de dados:
  - **SLA por Automação**: Adicionada coluna `sla_minutes` no modelo `Automation` com migração inline automática. Schemas Pydantic (`AutomationBase`, `AutomationUpdate`, `SystemOverviewAutomationCard`) atualizados para incluir `sla_minutes`, `sla_status` (ok/at_risk/violated/unknown) e `sla_avg_duration_minutes`.
  - **Cálculo de SLA**: `system_overview.py` calcula o status de SLA de cada automação com base na duração média das execuções bem-sucedidas das últimas 24h vs. `sla_minutes` configurado (< 80% = ok, 80-100% = at_risk, > 100% = violated).
  - **Painel de Fila por Prioridade**: Novo painel visual no Dashboard com contadores em tempo real de execuções por prioridade (HIGH/NORMAL/LOW), alimentado pelos dados já existentes em `DiagnosticsQueue.active_by_priority`.
  - **Score de Saúde Consolidado**: Widget de score (0-100) calculado dinamicamente a partir de achados de diagnóstico (findings CRITICAL/WARN) e violações de SLA, exibido ao lado do painel de fila.
  - **Modo Operador**: Toggle `⚙ Modo Operador` no Dashboard que, quando ativado, exibe botões avançados por linha (⏸ Pausar, ▶ Retomar, 📋 Clonar) e botões globais (⏸ Pausar Todas, ▶ Retomar Todas). Todos os botões chamam os endpoints FastAPI já existentes.
  - **Badge de SLA**: Coluna SLA na tabela de automações com badge colorido (✅ OK / ⚠️ Risco / 🔴 Violado / ➖ N/A) e tooltip com duração média vs. SLA configurado.
  - **Badge de Grupo Operacional**: Coluna Grupo exibindo o `queue_group` de cada automação como badge na tabela.
  - **Fila com `active_by_priority`**: `SystemOverviewQueue` enriquecido com `active_by_priority` propagado do `DiagnosticsQueue`.
- **Validação**: Suite pytest **65/65 testes verdes** após migração de schema e alterações de backend.

## [6.8.0] - 2026-05-19
### Adicionado
- **Fase 8 (Runbooks Operacionais & SLAs)**: Conclusão da Fase 8 focada na padronização documental e governança operacional de incidentes:
  - `docs/templates/automation-runbook-template.md`: Criado o template padrão de runbooks operacionais de missão crítica.
  - `docs/runbooks/receitas-bloqueadas-runbook.md`: Elaborado o runbook operacional detalhado da automação crítica de Receitas Bloqueadas, cobrindo ficha técnica, arquitetura, dependências, engenharia de resiliência (retry exponencial do Oracle e graceful degradation de canais), exit codes detalhados e troubleshooting passo a passo.
  - `docs/automation-criticality-map.md`: Criado o mapa formal de criticidades e SLAs do Hub de Automações, categorizando todos os robôs ativos por criticidade (Tiers 1 a 4), SLAs de recuperação, cadências de disparo, impacto de parada e fluxos automáticos de escalonamento.

## [6.7.0] - 2026-05-19
### Adicionado
- **Fase 7 (Arquitetura e Modularização)**: Conclusão da Fase 7 focada em modularizar a definição de contratos de dados Pydantic:
  - `Orchestrator/app/schemas/`: Criado o pacote de schemas quebrando o arquivo massivo e monolítico `schemas.py` de ~850 linhas (26KB).
  - `Orchestrator/app/schemas/common.py`: Contém funções de validação de segurança, expressões regulares de nomes seguros, normalizadores de schedule e visualização de recorrências.
  - `Orchestrator/app/schemas/automations.py`: Contém as classes `AutomationBase`, `AutomationCreate`, `AutomationUpdate` e `AutomationResponse`.
  - `Orchestrator/app/schemas/executions.py`: Contém as classes `ExecutionBase`, `ExecutionResponse`, `ExecutionSummary`, `ExecutionTelemetryStart`, `ExecutionTelemetryEnd`, `ExecutionQueueActionRequest` e `ExecutionQueueActionResponse`.
  - `Orchestrator/app/schemas/system.py`: Contém todas as definições de telemetria, KPIs, diagnósticos operacionais, overview de fila, validação de arquivos `.env` e estruturas de auditoria.
  - `Orchestrator/app/schemas/__init__.py`: Inicialização do pacote garantindo retrocompatibilidade de 100% de modo que nenhum router, service ou teste precise alterar seus caminhos de importação (`from .schemas import ...`).
- **Validação de Excelência**: Executado com sucesso o pytest obtendo **65/65 testes unitários e de integração 100% verdes** e o validador de governança local `ValidarAutomacoes.ps1 -OnlyGovernance` retornando zero falhas em todos os 172 arquivos mapeados.

### Removido
- `Orchestrator/app/schemas.py`: Arquivo monolítico legado de 850 linhas removido definitivamente em prol de maior modularidade, manutenibilidade e economia de tokens de contexto.

## [6.6.0] - 2026-05-19
### Adicionado
- **Fase 6 (Segurança)**: Conclusão da Fase 6 focada em segurança, varredura de vazamentos e higienização robusta de logs e payloads:
  - `Orchestrator/app/security.py`: Implementado o higienizador de alto desempenho `sanitize_log_payload` com suporte a strings, dicionários e listas recursivos. Ele mascara chaves sensíveis como `api_key`, `password`, `senha`, `token`, `jwt`, `secret_key` para `********`, oculta senhas em conexões `oracle://` ou `http://` e mascara CPFs e CNPJs formatados.
  - `Orchestrator/tests/test_sanitization.py`: Criada a suite com 6 novos testes unitários testando todos os casos de mascaramento de URLs, chaves, dicionários e listas recursivas (todos verdes).
  - **Integração no Core**: O higienizador foi integrado no core do runtime de logs (`execution_runtime.py`) e na rota de telemetria externa (`telemetry_end`), prevenindo vazamento físico de credenciais para o banco de dados.
  - **Gitleaks CI**: Homologada a integração do scanner oficial de segurança no GitHub Actions com `gitleaks-action@v8` para auditoria estática contra vazamento de segredos em cada push/PR.
  - **Base Ampliada**: Elevada a suite do Pytest para **65 testes unitários e de integração 100% verdes**.

## [6.5.7] - 2026-05-19
### Adicionado
- **Fase 5 (Testes Automatizados)**: Criadas e homologadas suites de testes robustas e resilientes, elevando a base histórica de 48 testes para **59 testes** unitários e de integração 100% verdes:
  - `Orchestrator/tests/test_queue_rules.py`: Validação de concorrência distribuída no mesmo grupo (`queue_group`), limite rigoroso baseado em `max_retries` e classificação correta de exit codes do subprocesso (WhatsApp expirado/canal).
  - `Orchestrator/tests/test_diagnostics.py`: Validação de heartbeats antigos (worker offline), fila ociosa/envelhecida em `PENDING`/`RUNNING` (`stalled queue`) e alerta de tamanho WAL do SQLite elevado com simulação e mock de rotas.
  - `Orchestrator/tests/test_validation.py`: Validação estrita de cron schedules inválidos via schemas Pydantic e auditoria de conformidade sintática de arquivos `.env` rejeitando espaços, duplicidades e erros de formatação.
  - `Orchestrator/tests/test_api_contracts.py`: Validação de segurança Zero Trust (headers `X-API-Key`), respostas 403 e 404 apropriadas, integridade estrutural contendo `contract_version` e prevenção de vazamento de credenciais privadas.
  - `docs/test-coverage-map.md`: Mapeamento de cobertura associando os arquivos críticos do Orchestrator às suas respectivas suites de testes automatizados.

### Corrigido
- **Mensagem de API Key nos Testes**: Ajustado assert do teste de autorização para coincidir com a mensagem real traduzida em Português do Brasil no middleware.
- **Isolamento de Concorrência de Grupo**: Refatorado o teste de `queue_group` para utilizar automações distintas simulando concorrência real entre robôs diferentes em grupo compartilhado, prevenindo falsos positivos causados pelo lock por automação individual.
- **Mock de WAL no Router**: Modificado o mock de tamanho do WAL para aplicar o patch diretamente no router `system.py`, garantindo que o endpoint de API utilize com precisão o valor simulado no teste.

## [6.5.6] - 2026-05-19
### Adicionado
- **Fase 4 (Métricas de Qualidade)**: Criado o script local robusto `Tools/Get-QualitySnapshot.ps1` (UTF-8 com BOM) para coleta totalmente automatizada e síncrona de tamanho de repositório, contagem de arquivos, cobertura de testes (Pytest), score de estilo do Pylint, erros do Mypy e conformidade agregada da governança nativa.
- **Fase 4 (Quality Dashboard)**: Criado o documento centralizador `docs/quality-dashboard.md` consolidando as métricas obtidas e definindo as metas estabelecidas na governança técnica.

### Alterado
- **Cálculo de Tamanho Real**: O script de snapshot foi ajustado para ignorar os gigas e megabytes gerados pelas sessões temporárias do WhatsApp (`lib/.wwebjs_auth/`) no cálculo de arquivos grandes e tamanho total do repositório, refletindo de forma real a baseline do git clone (caindo de 368 MB para **96.97 MB**).
- **Validação Síncrona da Governança**: Substituída a chamada concorrente em background por uma execução síncrona e nativa via `$LASTEXITCODE`, garantindo que o status consolidado de governança do snapshot reflita com precisão o estado real do ecossistema.

## [6.5.5] - 2026-05-19
### Adicionado
- **Fase 1 (Higiene do Repositório)**: Criado o arquivo `.env.example` com o mapeamento completo e seguro de todas as variáveis de ambiente necessárias para o deploy da aplicação.
- **Fase 2 (Dependências Reproduzíveis)**: Criados os arquivos de especificação `requirements.in`, `requirements-dev.in` e `requirements-test.in`, gerando os respectivos lockfiles `requirements.txt`, `requirements-dev.txt` e `requirements-test.txt` através de `pip-compile`.
- **Fase 3 (CI Obrigatório & Gitleaks)**: Integrado job Gitleaks Security Scan oficial usando a action oficial no GitHub Actions (`gitleaks/gitleaks-action@v8`) para verificação automática de vazamento de segredos.

### Alterado
- **Higiene e Gitignore**: `.gitignore` v2.1.1 configurado para ignorar relatórios Playwright, coberturas, caches locais e artefatos de compressão, mantendo a permissão explícita para o versionamento dos lockfiles.
- **Governança de Encoding**: `Tools/Test-SourceEncoding.ps1` ajustado para ignorar arquivos de estado runtime dinâmicos (`email_state.json`, `receitas_state.json`, `delivery_state.json`) do scanner de UTF-8 sem BOM, evitando falsos positivos no pre-commit causados pelo Orchestrator.
- **CI / GitHub Actions**: Atualizado o job de governança do workflow `.github/workflows/governanca.yml` para usar setup-python com cache de pip, instalar dependências a partir dos lockfiles compilados de dev/test/runtime, e validar a conformidade de estilo de código via Black e Isort de forma contínua.
- **Estilo de Código (Python Lint & Formatter)**: Formatados 30 arquivos Python em todo o ecossistema com Black e ordenados os imports com Isort para consolidação de padrões estéticos homogêneos e eliminação de drifts de código.

### Testado
- **Validação Local e Unitária**: Execução bem-sucedida do pytest (48 testes passando) e governança local agregada via `ValidarAutomacoes.ps1` pós-formatação de imports e estilo Python.

## [6.5.4] - 2026-05-18
### Adicionado
- **Governança de Evidência Playwright**: Novo `Tools/Test-PlaywrightEvidence.ps1` valida padrão, template e evidências E2E, exigindo URL real do dashboard, Playwright como etapa final, console limpo e resultado aprovado.
- **Contrato Operacional Versionado**: `/api/system/overview`, `/api/system/diagnostics` e `/api/system/version` agora expõem `contract_version`; diagnósticos também incluem `checks` mínimos de runtime e plano de recovery em duas camadas.

### Alterado
- **Governança Agregada**: `Tools/ValidarAutomacoes.ps1 -OnlyGovernance` passa a executar o validador de evidência Playwright junto aos checks nativos.
- **Runtime Compartilhado do Orchestrator**: scheduler, wake-up do worker, helpers de execução e criação base de jobs/executions foram extraídos para módulos comuns, reduzindo acoplamento entre `main.py`, routers e `worker.py`.
- **Dashboard SPA**: migração de ações para registro controlado via `data-action` avançou para ações dinâmicas e modais; paginação saiu de `onclick` inline para listeners explícitos em `ui_manager.js`.

### Testado
- **Contrato de Payload**: testes de API e smoke agora validam `contract_version` nos endpoints agregados de sistema.
- **E2E sem Cache**: Playwright validou fluxo real do dashboard em sessão nova, incluindo navegação entre abas e paginação de execuções com console limpo.

## [6.5.3] - 2026-05-18
### Adicionado
- **Classificação de Falhas de Canal**: Worker passou a traduzir exit codes conhecidos em `failure_reason` e `recovery_action` operacionais, diferenciando sessão WhatsApp expirada, falha de entrega de canal e erro genérico.
- **Lock de Grupo no Requeue**: `/api/executions/{exec_id}/requeue` agora bloqueia retry manual quando já existe execução ativa no mesmo `queue_group`, reduzindo risco de duplicidade em canais, Oracle ou recursos compartilhados.

### Testado
- **Regressões de Recovery**: Adicionados testes focados para classificação de resultado do subprocesso e bloqueio de requeue por grupo operacional ativo.

## [6.5.2] - 2026-05-18
### Adicionado
- **Diagnóstico Operacional Acionável**: `/api/system/diagnostics` passou a expor impacto, prioridade, `action_code`, `action_label`, `operator_actions`, hotspots de falhas em 24h e fila ativa por prioridade/grupo.
- **Console de Recovery no Dashboard**: A aba `Sistema` agora usa ações estruturadas do diagnóstico para orientar checkpoint, sincronização de agenda, wake-up/recovery e triagem de execuções.
- **Requeue Auditável na UI**: A tela `Execuções` passou a exibir motivo de falha, ação de recuperação, retries e botão de requeue quando o contrato permitir.
- **Baseline de Melhoria Operacional**: Documentados snapshot, fases pequenas e roteiro de evolução em `docs/operational-improvement-baseline.md` e `docs/operational-improvement-roadmap.md`.

### Corrigido
- **Cache de Testes do Orchestrator**: `Orchestrator/pytest.ini` desabilita o cache do pytest para evitar warnings de permissão em ambientes restritos sem alterar a lógica do produto.

## [6.5.1] - 2026-05-18
### Corrigido
- **WhatsApp de Receitas Bloqueadas**: `lib/WhatsApp-Core.js` passou a registrar bootstrap, autenticação, desconexão e ACK com mais clareza e aumentou o `protocolTimeout` do Puppeteer para mitigar a falha `Runtime.callFunctionOn timed out` na inicialização.
- **Retentativa de Bootstrap**: Falhas transitórias na inicialização do cliente WhatsApp agora fazem uma retentativa curta antes de devolver erro definitivo ao orquestrador, sem reenviar o e-mail.

### Removido
- **Política Local em `.gemini/`**: `project_auto_approve.toml` foi desindexado do Git para respeitar o contrato de limpeza de artefatos locais já cobertos por `.gitignore`.

## [6.5.0] - 2026-05-18
### Adicionado
- **Recorrência v2 na Aba Automações**: Contrato de agenda evoluído com `schedule_version=2` e `schedule_type` (`manual`, `daily`, `weekly`, `monthly`, `interval`, `once`), mantendo leitura retrocompatível de payload legado.
- **Preview de Agenda**: Novo endpoint `POST /api/system/schedule/preview` para simular próximas execuções e retornar resumo humano da recorrência.
- **Ações Operacionais por Automação**: Novos endpoints `POST /api/automations/{id}/pause`, `POST /api/automations/{id}/resume` e `POST /api/automations/{id}/clone`.

### Alterado
- **Scheduler Enterprise**: `reload_scheduled_tasks` agora traduz agenda v2 para jobs APScheduler auditáveis por tipo de recorrência.
- **Contrato de Resposta de Automação**: `AutomationResponse` passa a incluir `schedule_type`, `schedule_summary` e `next_runs_preview`.
- **UX da Aba Automações**: Tabela operacional ampliada com sinais de risco (`cooldown`, `retries`, `queue_group`), ações rápidas (executar, pausar/retomar, clonar, histórico) e formulário de configuração expandido.
- **Validação de Agenda**: `POST /api/system/schedule/validate` passou a usar normalização centralizada e resumo consistente com o preview.

### Corrigido
- **Recuperação da Aba Sistema**: `POST /api/system/worker/wakeup` voltou a ser apenas um nudge leve e a recuperação canônica do worker passou a usar o fluxo `Recover-Orchestrator.ps1` / `Start-Orchestrator.ps1` quando o worker está offline.
- **Ação Contextual no Dashboard**: A aba `Sistema` agora troca a ação operacional exibida conforme o estado real do worker, mostrando wake-up quando o worker está online e recuperação quando está offline.

## [6.4.0] - 2026-05-17
### Adicionado
- **Schema Evolutivo do Orchestrator**: Startup agora aplica migrações leves em SQLite e persiste `schema_version` em `orchestrator_metadata`.
- **Contrato de Fila Operacional**: Execuções passaram a registrar `retry_count`, `max_retries`, `failure_reason`, `recovery_action` e `queue_group`.
- **Requeue Auditável**: Novo endpoint `POST /api/executions/{exec_id}/requeue` cria nova execução `PENDING`, preserva origem da tentativa e audita o motivo operacional.
- **Validação Administrativa**: Novos endpoints `POST /api/system/schedule/validate` e `POST /api/system/env/validate` permitem validar payloads antes de persistência.

### Alterado
- **Overview e Diagnostics Tipados**: `/api/system/overview`, `/api/system/diagnostics` e `/api/system/version` passaram a expor `schema_version` e contratos de resposta mais estáveis para front-end e operação.
- **Disparo de Execuções**: Criação manual e agendada agora herda `max_retries` e `queue_group` da automação; disparo manual também respeita `cooldown_minutes` e bloqueio por grupo.
- **Diagnóstico de Scheduler**: `/api/system/diagnostics` agora detecta inconsistências entre automações agendadas no banco e jobs carregados em memória.
- **Documentação AI-Native**: `README.md`, `CONTEXT.md`, `SECURITY.md` e `GEMINI.md` sincronizados com o novo contrato operacional.

### Corrigido
- **Persistência de Recovery**: Limpeza de execuções `RUNNING` após reboot agora registra `failure_reason=ORCHESTRATOR_REBOOT` e `recovery_action=REQUEUE_IF_SAFE`.
- **Timeout e Falha do Worker**: Worker passou a classificar falhas com `failure_reason` e `recovery_action`, reduzindo ambiguidade para operação e requeue.

## [6.3.2] - 2026-05-17
### Adicionado
- **Montagem de Terceirizados**: E-mails de divergência agora informam a quantidade de peças vinculadas a NF incorreta por OB e no resumo agregado da notificação, usando o campo `QT_PC_NF`.
- **Diagnóstico Acionável**: `/api/system/diagnostics` agora expõe `overall_status`, `findings`, risco do WAL, idade do heartbeat e idade das execuções mais antigas em `PENDING` e `RUNNING`.
- **Resumo Operacional no Overview**: `/api/system/overview` passou a incluir resumo de diagnóstico sem quebrar o contrato existente do Dashboard.
- **Achados na Observabilidade**: Dashboard passou a renderizar achados operacionais com severidade, componente afetado e ação sugerida para o operador.

### Alterado
- **Versão Unificada**: Orchestrator e Worker atualizados para `6.3.2` na fonte única `Orchestrator/app/constants.py`.
- **Restart Canônico**: `Infrastructure/Start-Orchestrator.ps1` alinhado para reportar `6.3.2` nas mensagens operacionais.
- **Regressões de Observabilidade**: Testes de API ampliados para cobrir diagnóstico saudável, fila antiga, WAL elevado e compatibilidade do overview.
- **Runtime Padronizado**: Automações de negócio passaram a carregar `.env` via `Lib-Config`, usar Python da venv por caminho explícito e aceitar `ORACLE_CLIENT_LIB_DIR`/`ORACLE_CLIENT_PATH` como fallback.
- **Governança de Alta Estabilidade**: Validadores JSON, Python e PowerShell approved verbs foram ajustados para evitar falhas por cache/runtime local e reduzir tempo de validação agregada.

### Corrigido
- **Montagem de Terceirizados**: `extract_oracle.py` agora carrega o `.env` com `override=True`, eliminando divergência entre execução manual e execução via Orchestrator quando a sessão local tiver variáveis Oracle stale.
- **Conformidade de Logs**: Timestamps de estado e watchdog alinhados para `dd/MM/yyyy HH:mm:ss`, fechando violações do guardrail de log.
- **WhatsApp Wrapper**: `lib/Send-WhatsApp.ps1` passou a usar `Invoke-NativeProcess` para captura estruturada de saída e exit code.

## [6.3.1] - 2026-05-17
### Alterado
- **Governança E2E (Playwright)**: Formalizado Playwright como validação final obrigatória para mudanças de Dashboard/UI e contratos front-back operacionais.
- **Contrato de Agentes**: `AGENTS.md` atualizado com regra explícita de ordem de validação, exigindo Playwright E2E por último para fluxos cobertos.
- **Skill de Frontend**: `.github/skills/html-css-enterprise-standard/SKILL.md` atualizado para exigir checklist mínimo de validação E2E com Playwright.
- **Guia Operacional**: Adicionado `docs/playwright-e2e-standard.md` com escopo, ordem, critérios de aceite e evidências obrigatórias para IA.
- **Template de Evidência**: Adicionado `docs/playwright-e2e-evidence-template.md` para padronizar o fechamento técnico de validação E2E Playwright.
- **Catálogo de Ferramentas**: `Tools/README.md` atualizado para apontar o padrão oficial de validação E2E.

## [6.3.0] - 2026-05-17
### Adicionado
- **API Agregada de Operação**: Novos endpoints opcionais `GET /api/system/overview` e `GET /api/automations/{automation_id}/overview` para reduzir roundtrips no dashboard e consolidar visão operacional.
- **Next Run Consistente**: `next_run` agora é enriquecido nas respostas de automações (`/api/automations`, `/api/automations/all`, `/api/automations/{id}`) a partir do scheduler carregado em memória.

### Corrigido
- **SPA Dashboard**: Reimplementados handlers ausentes (`openCreateModal`, `saveAuto`, `addScheduleTime`, `toggleGlobalTestMode`, `callSystemAction`, `handleSearch`) e restaurado fluxo operacional sem erros de console.
- **Execuções com Filtro Real**: Tela de execuções passou a enviar `status`, `automation_id`, `date_from`, `date_to` e `requested_by` para o backend.
- **Logs do Painel de Controle**: Abertura de logs agora usa `exec_id` válido da última execução da automação, removendo placeholder inválido.
- **Gráficos Operacionais**: Renderização de `chart-performance` e `chart-status` com `apexcharts.min.js` baseada em payload agregado.
- **Dupla Submissão no Cadastro**: Removido gatilho duplicado de submit no modal de automações e adicionado lock transacional do botão de salvar para impedir cliques concorrentes.
- **Sessão Zero-Trust na SPA**: Ciclo de `403` agora limpa API Key em memória/localStorage, notifica o operador e solicita nova chave imediatamente.
- **Semântica de Filtros em Execuções**: Endpoint `/api/executions` passou a retornar `422` explícito para `status`, datas, paginação e range inválidos.
- **Feedback Textual**: Corrigida mensagem com mojibake na ação global `resume-all`.
- **Auditoria de Ações Críticas**: `backup`, `purge` e `checkpoint` migrados para `log_audit` com ator real via IP do cliente.
- **Administração .env**: Corrigida resolução de `PROJECT_ROOT` no router de sistema para que `/api/system/env` leia/escreva o arquivo `.env` da raiz do repositório.

### Alterado
- **Design System do Dashboard**: Migração do visual escuro/glass para tema claro corporativo, com foco em densidade operacional, legibilidade e consistência em desktop/tablet.
- **Cadastro e Agenda**: Modal de automação expandido para cadastro completo (descrição, timeout, canais de notificação, agenda por dias/horários) com resumo humano da agenda.

## [6.2.1] - 2026-05-16
### Adicionado
- **Shared Skills Canonicalization**: Consolidada a fonte canônica das skills em `.github/skills/`, com `.gemini/skills/` mantido como espelho de compatibilidade para Gemini CLI e Antigravity via junction/symlink.
- **Agent Workspace Contract**: Adicionado `AGENTS.md` para formalizar a convivência entre ChatGPT/Codex, Gemini CLI e Antigravity no mesmo repositório.

### Alterado
- **Skills Governance**: `Tools/Test-SkillsGovernance.ps1` evoluído para validar placeholders proibidos, referências cruzadas inválidas, taxonomia ativa e consistência do espelhamento entre `.github/skills/` e `.gemini/skills/`.
- **Codex Shared Skills**: `Tools/Test-SkillsGovernance.ps1` agora valida a presença dos mirrors globais obrigatórios do Codex (`protocolo-valeg` e `git-ide-governance-skill`) apontando para a fonte canônica compartilhada do Gemini/Antigravity.
- **Encoding Governance**: Adicionado `Tools/Test-SourceEncoding.ps1` ao fluxo de governança para impedir regressão de encoding em documentação Markdown (`.md` em UTF-8 sem BOM, com proteção contra mojibake), validar `.py`, `.js`, `.json`, `.txt`, `.sql`, `.html` e `.css` como UTF-8 sem BOM e preservar a exigência de `UTF-8 with BOM` em `.ps1` e `.psm1`.
- **Documentação AI-Native**: `README.md`, `CONTEXT.md`, `GEMINI.md`, `.github/copilot-instructions.md` e `.github/references/arquitetura-atual.md` alinhados ao modelo atual de stack 100% nativa e skills compartilhadas.

## [6.2.0] - 2026-05-15
### Adicionado
- **Arquitetura Zero-Latency (Worker)**: Implementado mecanismo de *Instant Wake-up* via Long-Polling, eliminando o atraso de 15s no processamento de novas tarefas.
- **Blindagem de Backend (FastAPI)**: Adicionado *Global Exception Handler* que garante que qualquer erro interno retorne JSON estruturado, evitando travamentos no Dashboard.
- **Modularização de Frontend (ES Modules)**: Refatoração completa do Dashboard SPA, separando responsabilidades em `ui_manager`, `execution_engine` e `ide_service`.
- **Saneamento PEP8**: Correção de fluxos de auditoria e padronização de espaços/tabs em todos os routers Python.

## [6.1.0] - 2026-05-15
### Adicionado
- **Autonomia Máxima (Dashboard)**: Implementada interface de "Ambiente Global" para gestão visual segura do arquivo `.env`.
- **Editor Visual de Regras (JSON)**: Criado modal no Dashboard que permite aos usuários modificar as regras de negócio de cada automação remotamente.
- **Web IDE Minimalista**: Adicionado editor de código-fonte no Dashboard, permitindo ajustar a lógica de arquivos `.ps1`, `.py` e `.sql` em tempo real, com rigorosa soberania de encoding (UTF-8 com BOM).

## [6.0.0] - 2026-05-15
### Adicionado
- **Orchestrator**: Adicionado endpoint assíncrono em lote `/api/broadcast_logs` para suportar transmissões consolidadas do motor Powershell sem sofrer bloqueio I/O.
- **Worker**: Otimização profunda em `worker.py` (v6.0.0) com adoção de **Adaptive Polling** (backoff exponencial de 2s a 15s) reduzindo gargalos de CPU e lock database.

### Corrigido
- **Python Data Pipeline**: Substituição completa dos laços síncronos iterativos do Pandas (`iterrows`) por processamentos vetorizados (`np.where` / `pd.merge`) garantindo eliminação de Overhead Computacional na geração de arrays HTML ("Receitas Bloqueadas" e "Montagem de Terceirizados").
- **Oracle Fetch**: Alteração de cursores lentos `fetchall()` para leitura paginada por lotes via `fetchmany(5000)`, evitando Out-Of-Memory e latências agressivas de alocação de memória no servidor.

### Alterado
- **PowerShell Resiliency**: `Write-AutomacaoLog` refatorado para utilizar chamadas `AppendAllText` e buffer de filas enfileiradas assíncronas `[System.Collections.Generic.List[Hashtable]]::new()` para envio de Broadcast log por Batch em lote. Elimina o antigo modelo 1:1 I/O Blocking I/O. — Hub de Automações (Soberano)

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O projeto segue os princípios de **Resiliência, Escala e Governança (Protocolo V.A.L.E.G.)**.

## [5.8.0] — 2026-05-15
### 🚀 Alta Performance: Pragmatic Upgrade (ADR-016)
- **Zero N+1 Queries**: Refatoração crítica nos routers `system.py` e `executions.py` do Orchestrator. Implementados `joinedload` e agregações SQLAlchemy massivas (`func.count`, `func.avg` com `case`), colapsando dezenas de queries em transações únicas (O(1) database footprint).
- **Batched Broadcasting**: Implementação de Log Flusher Assíncrono no `worker.py`. A transmissão de telemetria agora ocorre em lotes temporais (a cada 1 segundo) via thread dedicada, erradicando a sobrecarga de I/O de rede síncrona gerada pela leitura linha-a-linha dos processos filhos.
- **Throughput Tuning**: Aumento do `WORKER_MAX_CONCURRENCY` padrão de 2 para 4, viabilizado pela drástica redução de contenção de banco e I/O de rede.

## [5.7.1] — 2026-05-15
### 🩺 Consolidação de Saúde e Saneamento de Processos
- **Orquestrador:** Saneamento de processos duplicados (rogue) que operavam fora do ambiente virtual (.venv), causando conflitos de concorrência e falhas de carga de tipos .NET (NativeProcessRunner).
- **Resiliência:** Implementado log de diagnóstico no `Lib-Process.psm1` para monitorar falhas silenciosas do `Add-Type`.
- **Sintaxe:** Correção de risco de interpretação de parâmetros em `Receitas Bloqueadas` e `Receitas Emitidas` (Send-AlertaFalhaDefinitiva).
- **Estabilidade:** Execução de Hard Reset (Rescue Mode) para estabilização da árvore de processos (API, Worker e Watchdog).

## [5.7.0] — 2026-05-15
### 🚀 Alta Performance: Async I/O Wrapper (ADR-015)
- **Deadlock Elimination**: Resolvido o travamento crônico das automações "Receitas Emitidas" e "Receitas Bloqueadas" causado pelo esgotamento de buffers de pipe no PowerShell 5.1.
- **AsyncProcessRunner**: Introduzida a biblioteca `lib\Lib-Process.psm1` com wrapper C# nativo. A leitura de `stdout` e `stderr` agora ocorre em threads paralelas, garantindo fluidez total mesmo sob alto volume de dados (Base64/HTML).
- **Hub Standardization**: Padronização preventiva de 100% dos orquestradores para o novo motor de execução assíncrona.

## [5.6.6] — 2026-05-15
### 🛡️ Endurecimento Crítico: Prevenção de Órfãos e Hangs (Pilar A/R)
- **Zombie Eradication**: Corrigido o vazamento de processos órfãos (`node.exe`) em "Receitas Bloqueadas". O acionamento via `Start-Process` foi substituído por `System.Diagnostics.Process` para atrelar rigorosamente os filhos à árvore principal, garantindo a eficácia do `taskkill /T` do Orquestrador.
- **Network Hang Prevention**: Injetados `expire_time=2` e `call_timeout=180000` (3 minutos) nas conexões `oracledb` em `processar_receitas.py`. Isso impede que oscilações silenciosas de rede travem a execução indefinidamente ("hangs").
- **Mutex Resilience**: Atualizada a `Lib-Logging.psm1` (`Enter-AutomationLock`) para tratar e reciclar graciosamente a `System.Threading.AbandonedMutexException`, evitando crashes sistêmicos caso uma execução anterior seja derrubada forçosamente.
- **Saneamento Ativo**: Executado comando PowerShell para purgar dezenas de processos `python`, `pwsh` e `node` que estavam pendurados desde o dia 14/05, estabilizando os recursos do servidor.

## [5.6.5] — 2026-05-14
### 🔠 Estabilidade de Encoding e Saneamento (Pilar V/G)
- **UTF-8 Normalization**: Convertidos todos os scripts `.ps1` e `.psm1` para `UTF-8 with BOM` para garantir integridade absoluta de acentuação no PowerShell 5.1.
- **Process I/O Integrity**: Implementada a captura explícita de `StandardErrorEncoding` como UTF-8 na orquestração de processos Python, resolvendo falhas de `UnicodeEncodeError`.
- **Double-Encoding Fix**: Revertida a corrupção de caracteres (ex: `Ã§`) em mensagens de log nativas, restaurando a padronização gramatical PT-BR.
- **Repo Cleanup**: Removidos artefatos de teste obsoletos e scripts temporários de manutenção, mantendo o repositório em conformidade Lean.

## [5.6.4] — 2026-05-14
### 🛡️ Endurecimento e Resiliência do Agendador (Pilar R)
- **Misfire Resilience**: Implementado `misfire_grace_time=60` em todos os jobs do APScheduler, garantindo que disparos atrasados por instabilidades do SO sejam recuperados.
- **I/O Guard (Logs)**: Envolvido o loop de heartbeat em blocos `try/except` para prevenir que erros de escrita no console (OSError 22) travem o motor de agendamento.
- **Diagnostic Toolkit**: Consolidada a infraestrutura de diagnóstico no script `tools/diagnostics.py`, substituindo scripts temporários por uma ferramenta unificada de saúde (DB, API e Logs).
- **Saneamento**: Limpeza completa do diretório `scratch` e normalização da stack para v5.6.4.

## [5.6.3] — 2026-05-14
### 🎯 Idempotência Granular Universal (Hub Global)
- **Extensão ADR-013**: Implementada a gestão granular de notificações em `Receitas Emitidas` (v2.7.0) e `Montagem de Terceirizados` (v2.2.0).
- **Delivery Checkpoints**: Introduzido o arquivo `delivery_state.json` para rastrear o sucesso individual de canais de saída, eliminando o risco de spam em caso de falhas na orquestração.
- **Template v2.1.0**: Atualizado o template oficial para suportar nativamente a lógica de supressão granular de notificações.
- **Resiliência**: Scripts `run.ps1` agora realizam leitura resiliente de estados, migrando automaticamente para o novo modelo de checkpoints.

## [5.6.2] — 2026-05-14
### 🕰️ Resiliência e Telemetria do Agendador
- **Saneamento de Processos**: Realizada limpeza profunda de instâncias duplicadas do Orquestrador/Worker, estabilizando o motor de agendamento após restart crítico.
- **Scheduler Telemetry**: Implementado log de carga de automações no startup, permitindo verificar a paridade entre banco de dados e motor in-memory.
- **Proof-of-Life (Heartbeat)**: Adicionado job de sistema `enterprise_scheduler_heartbeat` que loga o status do motor a cada 15 minutos, garantindo visibilidade sobre o loop do APScheduler.
- **Diagnóstico Resolvido**: Identificada e corrigida instabilidade transiente no motor de agendamento que causou a omissão de disparos entre 11:30 e 12:00.

## [5.6.1] — 2026-05-14
### 🎯 Idempotência Granular (Receitas Bloqueadas)
- **Checkpoints de Canal**: Substituição do modelo de "Compromisso Atômico" pela "Idempotência Granular" (ADR-013). Agora, o estado de envio de E-mail e WhatsApp é rastreado separadamente no `email_state.json`.
- **Prevenção de Spam**: Se o e-mail for entregue com sucesso, mas o WhatsApp falhar, o sistema salvará o estado parcial. Na próxima execução, apenas o WhatsApp será retentado, eliminando o reenvio duplicado de e-mails.
- **Resiliência de Estado**: Implementada lógica de leitura resiliente no `run.ps1` (v2.3.0) para migrar automaticamente formatos de estado antigos para a nova estrutura baseada em objetos.

## [5.6.0] — 2026-05-14
### 🛡️ Padronização Global e Blindagem UTF-8
- **UTF-8 with BOM (Logs)**: Migração total da `Lib-Logging.psm1` para `UTF-8 with BOM`. Essa mudança garante que o PowerShell 5.1 identifique corretamente os arquivos de log como UTF-8, eliminando caracteres corrompidos ("ASCII residual") em visualizadores de log.
- **Audit Modo Teste**: Concluída a padronização de todas as automações (`Receitas Bloqueadas`, `Receitas Emitidas`, `Montagem`) para respeitarem a hierarquia: Orquestrador > Registro do Windows.
- **Template Update**: O script de `_Template\run.ps1` foi atualizado com as novas diretrizes de encoding e exemplos de Modo Teste hierárquico.
- **Saneamento de Log**: Removida lógica redundante de Base64 manual em `Receitas Bloqueadas`, agora centralizada e simplificada via `Lib-Logging`.

## [5.5.0] — 2026-05-14
### 🎯 Unificação do Modo Teste (Source of Truth)
- **Orchestrator Injection**: O `worker.py` agora injeta a variável de ambiente `ORCHESTRATOR_TEST_MODE` (`true`/`false`) em cada execução, baseando-se estritamente no status do banco de dados (Dashboard).
- **Lib-Email Update**: `Lib-Email.psm1` agora prioriza o status vindo do Orquestrador, resolvendo o problema de "Split-Brain" onde o Modo Teste permanecia ativo mesmo após ser desabilitado no Dashboard.
- **Manual Fallback**: Mantido suporte ao redirecionamento automático via `AUTOMACAO_TEST_EMAIL` (registro do Windows) para execuções manuais via VS Code.
- **Uniformidade**: Aplicada a mesma lógica de prioridade na automação de Montagem de Terceirizados.

## [5.4.7] — 2026-05-13
### 🔠 Correção Global de Encoding e Pre-commit (UTF-8 com e sem BOM)
- **PowerShell UTF-8 BOM**: Padronização global de todos os scripts `.ps1` e `.psm1` para UTF-8 com BOM, corrigindo erro de sintaxe no PowerShell 5.1 e destravando o pre-commit.
- **UTF-8 No-BOM Global**: Modificação de todos os demais arquivos do projeto (`.py`, `.js`, `.json`, etc) para UTF-8 sem BOM.
- **VS Code Settings**: Atualização do `.vscode/settings.json` para forçar `utf8bom` especificamente em arquivos PowerShell.

## [5.4.6] — 2026-05-13
### 🔠 Padronização de Encoding (UTF-8 with BOM)
- **PS 5.1 Compatibility**: Reintrodução global do Byte Order Mark (BOM) em todos os scripts `.ps1` e `.psm1`. A ausência do BOM impedia o PowerShell 5.1 de reconhecer literais acentuados nativos, causando corrupção nos logs.
- **Log Healing**: Restauração da acentuação correta em 100% das mensagens de log (INÍCIO, Execução, etc.).

## [5.4.5] — 2026-05-13
### 🩹 Recuperação de Desastre (BOM Eradication) & Correção de Motor
- **BOM Eradication**: Removidos Byte Order Marks (BOM) invisíveis via manipulação de bytes brutos em todos os scripts `run.ps1` e bibliotecas `Lib-*`. A regressão foi causada por incompatibilidade do saneamento automático com o PowerShell 5.1.
- **Dependency Healing**: Identificada e corrigida a corrupção na `Lib-Retry.psm1`, que impedia a execução das automações de Receitas.
- **Worker Fix**: Estabilizada a função `dispatch_alerts` no `notifications.py` com a importação correta de `get_now_local`.
- **Validation**: Ciclo completo de testes realizado com sucesso, garantindo que 100% da stack está operacional.

## [5.4.4] — 2026-05-13
### 🧹 Saneamento Estético & Economia de Tokens
- **Massive Cleanup**: Remoção recursiva de espaços em branco (trailing spaces) e colapso de múltiplas linhas vazias consecutivas em 223 arquivos do projeto.
- **Token Optimization**: Redução do tamanho dos arquivos-fonte, otimizando o consumo de tokens em interações com IA e melhorando a legibilidade geral.
- **PowerShell BOM Compliance**: Tentativa de padronização de BOMs (causou regressão de sintaxe, corrigida na v5.4.5).

## [5.4.3] — 2026-05-13
### 🔠 Saneamento Global de Encoding (UTF-8 BOM Native)
- **Global Scan & Eradicate**: Varredura completa em `C:\Automacoes` para normalização UTF-8 e erradicação de guardrails ASCII obsoletos (ex: `# coding: utf-8`).
- **Heal Global**: Reparo recursivo de caracteres corrompidos em todos os scripts PowerShell e Python do Hub.
- **Bridge EOL**: Desativação definitiva do protocolo Base64 Bridge na automação de Montagem de Terceirizados.
- **Orquestração**: Forçamento de I/O UTF-8 explícito em todos os sub-processos Python via run.ps1.

## [5.4.2] — 2026-05-13
### 🛡️ Hardening de Governança e Cura de Bibliotecas (dill)
- **Cura Crítica**: Correção de encoding na biblioteca 'dill' (logger.py) eliminando falhas de linting.
- **Governança PS**: Refatoração de catch genéricos para [System.Exception] em infraestrutura central.
- **Saneamento**: Limpeza de lints residuais e estabilização de ambiente (PYTHONUTF8=1).

## [5.4.1] — 2026-05-13
### 🩺 Validação de Saúde & Ciclo de Vida de Telemetria
- **Health Check Executed**: Execução manual de todo o ecossistema de automações (Montagem, Receitas Bloqueadas, Receitas Emitidas) para validação de saúde pós-upgrade UTF-8.
- **Telemetry Validation**: Confirmação do fluxo de telemetria nativa (TEL_ IDs) enviando logs e- **Estado:** Estabilizado v5.4.3 (Full UTF-8 Native).
- **Encoding:** Padronização absoluta em UTF-8 com BOM para scripts PowerShell, garantindo integridade PT-BR no Windows.
- **Governança:** Conformidade total com Protocolo V.A.L.E.G. e extinção de protocolos legados (Base64 Bridge).
 (Pylint/PowerShell) planejados para refatoração futura.
- **Modo Teste (Sandbox)**: Validação bem-sucedida em ambiente de teste com 100% de sucesso nos disparos simulados.

## [5.4.0] — 2026-05-13
### 🌐 Universal Encoding (UTF-8) & Extinção do ASCII-Safe
- **Python UTF-8 Mode**: Ativação nativa da variável `PYTHONUTF8=1`, resolvendo bugs críticos de interoperabilidade em bibliotecas de terceiros (ex: `dill`) no Windows.
- **Base64 Bridge Discontinued**: Remoção do protocolo de empacotamento em Base64 para logs acentuados (`Lib-Logging`, `Lib-Email`), permitindo log nativo em UTF-8 direto no stderr/stdout.
- **Pre-commit Unblocked**: Remoção do guardrail rigoroso `Test-SourceEncoding.ps1`, liberando a escrita de caracteres acentuados diretamente no código-fonte (.py, .ps1, .js).
- **Codebase Refactoring**: Tradução maciça de escapes Unicode (`\uXXXX`, `[char]0xXX`) para caracteres nativos pt-BR, aumentando dramaticamente a legibilidade para humanos e IA.
- **Dashboard Upgrade**: Tradução de todos os HTML Entities no `dashboard-modern.html` para UTF-8 nativo.

## [5.3.0] — 2026-05-13
### 📡 Telemetria Nativa & Estabilização Global
- **External Telemetry API**: Implementação de novos endpoints `POST /api/executions/telemetry/start` e `POST /api/executions/telemetry/end` no backend FastAPI para registro de execuções externas.
- **PowerShell Library Upgrade**: Adicionadas funções `Register-ExecutionTelemetry` e `Close-ExecutionTelemetry` na `Lib-Logging.psm1`, permitindo que scripts terminal registrem seu ciclo de vida no Dashboard.
- **Real-time Log Streaming**: Atualização da `Write-AutomacaoLog` para transmitir logs em tempo real via broadcast HTTP para o Dashboard durante execuções manuais.
- **Unified ID System**: Padronização de prefixos `TEL_` para execuções originadas em terminais, garantindo distinção visual no banco de dados e interface.
- **Orchestrator Stability (v5.3.0)**: Saneamento estrutural dos scripts `run.ps1` (Receitas Emitidas v2.6.2, Montagem v2.1.0 e Receitas Bloqueadas v2.2.1), eliminando blocos duplicados e garantindo ciclo de vida de telemetria completo (Start/End).
- **Automation Scripts Sync**: Atualização dos scripts `run.ps1` (Montagem, Receitas Bloqueadas, Receitas Emitidas e Template) para adotar o novo fluxo de telemetria nativa de forma resiliente.

## [5.2.7] — 2026-05-12
### 🐛 Hotfix: Correção de Sintaxe & Resiliência de E-mail
- **Python Syntax Fix**: Correção de erro de sintaxe em `validate_and_generate_html.py` causado por injeção de documentação Markdown não comentada.
- **Email Dispatch Hardening**: Atualização do `run.ps1` para garantir que o parâmetro `-To` nunca seja enviado vazio para a biblioteca de e-mail, mesmo em modo de visualização (PreviewOnly), prevenindo falhas fatais no PowerShell.
- **Context Integrity**: Atualização da governança interna de contexto para refletir a estabilização da v5.2.7.

## [5.2.6] — 2026-05-12
### 📧 Governança de Notificações & Acentuação (Enterprise UI)
- **Externalized Recipients**: Migração dos destinatários oficiais de e-mail do código-fonte para o arquivo `config.json`, permitindo manutenção rápida pela equipe fiscal sem edição de scripts.
- **PT-BR Grammar Fix**: Revisão e correção de acentuação em todos os componentes visuais do e-mail (Divergências, Programação, Validação, etc.) e no assunto das mensagens, garantindo profissionalismo.
- **Config-Driven Delivery**: Orquestrador `run.ps1` atualizado para carregar configurações dinâmicas de e-mail (`config.json`) com fallback de segurança para o administrador em caso de erro no arquivo.
- **ASCII-Safe Compliance**: Padronização do código-fonte (.py e .ps1) para ASCII puro (0-127), utilizando escapes Unicode e interpolação de caracteres para garantir que a saída final permaneça perfeitamente acentuada sem comprometer a portabilidade do código.
- **Simplified Comments**: Comentários internos e blocos de gestão de contexto simplificados para ASCII sem acentos, conforme padrão de governança de código.

## [5.2.5] — 2026-05-12
### 🕰️ Modernização do Agendamento (Premium UX)
- **Multi-Schedule Support**: Implementada capacidade de configurar múltiplos horários de disparo específicos para a mesma automação (ex: 08:00, 12:30 e 17:45).
- **Time Picker & Tag System**: Nova interface com sistema de tags para gerenciar a lista de horários de forma visual e intuitiva.
- **Natural Language Summary**: Resumo descritivo atualizado para listar todos os horários configurados (ex: "Disparo agendado para toda segunda a sexta-feira às 08:00, 12:00, 18:00").
- **Backend Sync**: Motor de agendamento (`main.py`) atualizado para registrar múltiplos jobs no APScheduler baseados na nova estrutura de dados.

## [5.2.4] — 2026-05-12
### 🧹 Higienização de Estado & Limpeza de Temporários
- **Montagem de Terceirizados Fix**: Refatoração da lógica de idempotência em `validate_and_generate_html.py` para evitar a criação de arquivos `.tmp` em execuções sem mudanças ("Nenhuma mudança").
- **Orchestrator Cleanup Hardening**: Implementada limpeza automática de arquivos de cache temporários órfãos no bloco `finally` do `run.ps1`, garantindo diretórios limpos após o ciclo de vida da automação.
- **Análise de Coincidência**: Investigação técnica descartou interferência entre "Receitas Emitidas" e "Montagem" em execuções simultâneas, focando na causa raiz de gestão de arquivos locais.

## [5.2.3] — 2026-05-12
### 🛡️ Estabilização de Receitas & Lock Global
- **Enter-AutomationLock Fix**: Correção crítica na `Lib-Logging.psm1` onde a falta do parâmetro `-LogPath` e a ausência de retorno explícito travavam as automações que usavam lógica de condicional no lock.
- **Oracle SQL Hardening**: Upgrade no `extract_oracle.py` (Receitas Emitidas) para capturar DNA da Query e códigos ORA- detalhados, melhorando a rastreabilidade de erros de identificador (ORA-00904).
- **Resiliência V.A.L.E.G.**: Implementado logging de depuração para aquisição de Mutex, garantindo visibilidade total sobre o estado de concorrência do sistema.

## [5.2.2] — 2026-05-12
### 🕰️ Padronização de Timezone & WhatsApp Hardening
- **Timezone Standardization**: Refatoração global de todos os geradores de timestamps no Orquestrador para utilizar o horário de Brasília via helper `get_now_local()`.
- **WhatsApp Engine v2.1**: Correção crítica de sintaxe PowerShell no `Send-WhatsApp.ps1` e implementação de resolução de caminhos absolutos (`Convert-Path`) para evitar erros de `MODULE_NOT_FOUND` no Node.js.
- **Test Mode Sync**: Integração da API do Orquestrador com o PowerShell para sincronização automática da variável de ambiente `AUTOMACAO_TEST_EMAIL`, garantindo que o Dashboard e o Windows operem no mesmo estado de sandbox.
- **Mutex Parameter Fix**: Atualização da `Lib-Logging.psm1` para suportar parâmetros de log na liberação de travas, evitando falhas de orquestração silenciosas.
- **RunWhatsApp Update**: Otimização do script de reautenticação para modo VISUAL com carregamento dinâmico de configurações.
- **Frontend Sync**: Sincronização de datas no Dashboard para evitar deslocamentos de timezone.

---

## [5.2.1] — 2026-05-12
### 🛡️ Resgate Crítico & Concorrência (Hardenized v5.2.1)
- **Atomic Claim Strategy**: Refatoração do loop do Worker (`worker.py`) para realizar a reserva de tarefas via banco de dados antes do despacho, eliminando duplicidade de execuções (Race Conditions).
- **Zombie Process Cleanup**: Upgrade do `Start-Orchestrator.ps1` para rastrear e encerrar Workers órfãos via arquivo `.pid`, garantindo que apenas uma instância do motor de execução esteja ativa.
- **Global Mutex Lock**: Implementada a função `Enter-AutomationLock` no `Lib-Logging.psm1` utilizando `System.Threading.Mutex` do .NET, fornecendo uma camada de proteção no nível do SO para o mesmo `ExecId`.
- **Email Library Fix**: Adicionado suporte ao parâmetro `-PreviewOnly` em `Lib-Email.psm1`, corrigindo falhas de envio em automações que utilizam modo de visualização.
- **Ferramentas Dinâmicas**: Atualização de `AtivarModoTeste.bat` e `DesativarModoTeste.bat` para a versão v5.2.0, eliminando credenciais hardcoded e carregando configurações dinamicamente via `Lib-Config`.

---

## [5.2.0] — 2026-05-12
### 🏗️ Sincronização & Hardening (Enterprise Gold v5.2.0)
- **Sincronização de Versão**: Unificação de toda a stack (Backend, Worker, Dashboard) para a versão v5.2.0 Gold.
- **Hardening de Segurança**: Implementação de API Key robusta (64 chars) gerada via `secrets.token_hex` e externalização total via `.env`.
- **Infraestrutura Externalizada**: Migração de `ALLOWED_ORIGINS` e `WORKER_MAX_CONCURRENCY` para variáveis de ambiente.
- **Refatoração V.A.L.E.G.**: Eliminação de URLs hardcoded no Worker, correção de imports top-level e melhoria no tratamento de exceções (anti-bare except).
- **Dashboard v5.2.0**: Atualização visual e técnica da interface para refletir o novo estado de maturidade do Hub.

---

## [5.1.2] — 2026-05-12
### 🛡️ Resiliência & Idempotência (Safe-State Guard)
- **Safe-State Guard (Two-Phase Commit)**: Refatoração global da gestão de estado nas automações (`Receitas Bloqueadas`, `Receitas Emitidas`, `Montagem de Terceirizados`). O estado oficial agora só é consolidado após o sucesso confirmado de todas as notificações (Email/WhatsApp).
- **Atomic State Commitment**: Migração da responsabilidade de atualização dos arquivos `*_state.json` do Python para o orquestrador PowerShell, usando arquivos `.tmp` como área de transição.
- **WhatsApp Reliability**: Endurecimento da validação de códigos de saída do `Send-WhatsApp.ps1`, impedindo o avanço do estado em caso de falhas de autenticação ou conectividade.
- **Cache Persistence**: Implementação de cache temporário em `Montagem de Terceirizados` para garantir retentativa automática de divergências não notificadas.

---

## [5.1.1] — 2026-05-11
### 🏗️ Arquitetura & Segurança (V.A.L.E.G. v5.1.1)
- **Zero-Trust Dashboard**: Implementado prompt de segurança para API Key no front-end, eliminando tokens hardcoded e exigindo autenticação administrativa.
- **ASCII-Safe Rendering**: Migração completa de literais HTML para Entities Hexadecimais no Dashboard, garantindo exibição correta de acentos em pt-BR sem violar a regra de código-fonte ASCII (0-127).
- **Worker Resilience**: Adicionado controle de Graceful Shutdown no motor de execução, garantindo a terminação de processos filhos PowerShell para evitar processos órfãos.
- **SQLite Performance**: Otimização de `temp_store=MEMORY` e refatoração do purge de execuções para exclusão em massa no `database.py`.
- **Unified Logging**: Padronização do `JsonFormatter` global no `main.py` para correlação total de eventos de sistema via `request_id`.
- **Download Endurecido**: Implementada validação de `os.path.basename` e `startswith` no router de execuções para impedir ataques de Path Traversal.

---

## [5.1.0] — 2026-05-11
### 🏗️ Arquitetura (ASCII-Safe)
- **Padronização Global**: Conversão de todo o código-fonte (.py, .js) para o padrão ASCII-Safe (0-127).
- **Escapes Unicode**: Uso de `\uXXXX` em Python para manter acentuação correta em logs e mensagens de erro no backend.
- **Soberania Técnica**: Garantia de compatibilidade universal do código-fonte, eliminando dependências de encoding no nível de arquivo-fonte.

---

## [5.0.0] — 2026-05-09 (Enterprise Upgrade)
### 🏗️ Arquitetura
- **Central de Automações v5**: Migração completa da arquitetura monolítica para um modelo Control Tower baseado em FastAPI.
- **Modular Routers**: Divisão da API em `automations`, `executions`, `system` e `websocket`.
- **SQLite WAL Engine**: Implementação de modo WAL com auto-checkpoint (APScheduler) para alta concorrência.

---
Mantido pela equipe de Automações & Antigravity AI
