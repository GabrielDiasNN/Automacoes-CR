# Changelog

## [9.3.3] - 2026-05-26
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
- **Interferência de Variáveis na Suite Pytest**: Implementada a fixture global com `autouse=True` (`force_env_vars`) em `conftest.py` que re-injeta a variável `ORCHESTRATOR_API_KEY` com o valor de teste `hub-secret-token` e o caminho `ORCHESTRATOR_DB_PATH` como `:memory:` antes de cada execução de teste. Isso neutralizou a interferência causada pela importação tardia de robôs de negócio (como `extract_oracle.py`) que executavam `load_dotenv(..., override=True)` sobrescrevendo as chaves de teste pelas de produção, sanando todas as 40 falhas de `403 Forbidden` na suite completa (agora **73/73 testes verdes**).
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
