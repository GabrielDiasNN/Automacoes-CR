# Changelog — Hub de Automações (Soberano)

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O projeto segue os princípios de **Resiliência, Escala e Governança (Protocolo V.A.L.E.G.)**.

---

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
