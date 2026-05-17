# Changelog

## [6.3.2] - 2026-05-17
### Adicionado
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
