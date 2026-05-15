# Cognitive Context: Automações Hub v5.8.0 (Enterprise)

## Repository Philosophy
Este repositório é um ecossistema de automações **AI-Native**, operando na versão **v5.8.0 (Enterprise)**. O sistema segue o **Protocolo V.A.L.E.G.** (Validação, Arquitetura, Logging, Escala e Governança) com foco em resiliência e segurança Zero-Trust.

## System Architecture (v5.8.0 Enterprise)

- **ADR-016 (15/05/2026):** Pragmatic Performance Upgrade. Eliminação de N+1 Queries nos endpoints FastAPI via SQLAlchemy `joinedload` e agregação de dados. Implementação de log batching assíncrono no Worker, reduzindo drasticamente o overhead de I/O de rede e bloqueios, permitindo aumentar a concorrência padrão para 4.
- **ADR-015 (15/05/2026):** Async Process Wrapper (Anti-Deadlock): Implementação da `Lib-Process.psm1` com wrapper C# nativo. Esta arquitetura resolve a limitação de thread do PowerShell 5.1, garantindo que os fluxos `stdout` e `stderr` sejam consumidos simultaneamente em threads separadas. Isso elimina 100% o risco de travamento de buffer (I/O Deadlock) em automações com alto volume de logs ou dados.
- **ADR-007 (12/05/2026):** Sincronização v5.2.0: Consolidação de versões em toda a stack, hardening de seguranca (API Key robusta), eliminação de URLs hardcoded e refatoração arquitetural de imports/typing.
- **Zero-Trust Dashboard**: Front-end não armazena chaves; solicita via prompt e persiste em `localStorage` seguro.
- **UTF-8 Native Source (v5.4.0)**: Todo código-fonte (.py, .js, .ps1) opera nativamente em UTF-8. A restrição ASCII-Safe e o protocolo Base64 Bridge foram descontinuados para maximizar a legibilidade.
- **Graceful Worker**: Worker monitora processos ativos e garante o `taskkill` de toda a árvore de processos no shutdown.
- **SQLite Hardened**: WAL mode com `synchronous=NORMAL` e `temp_store=MEMORY` para máxima performance de I/O.
- **Unified JSON Logging**: Loggers do Orchestrator e Worker unificados para rastreabilidade via `correlation_id`.

## 🧠 Gestão de Contexto (AI-Native)
- **Estado:** Estabilizado v5.8.0 (High Performance Edition).
- **Compliance:** 100% aprovado em saneamento estético (trailing spaces) e encoding UTF-8 com BOM para PowerShell.
- **Ambiente:** Saneado com `PYTHONUTF8=1`, correção de corrupção na biblioteca `dill` e remoção de redundâncias de espaços.
- **ADR-011:** Saneamento Global (13/05/2026) - Remoção recursiva de espaços inúteis e normalização de quebras de linha em 223 arquivos para otimização de tokens.
- **ADR-001 (09/05/2026):** Upgrade v4→v5 aplicando Protocolo V.A.L.E.G. completo.
- **ADR-002 (11/05/2026):** Implementação da **B64 Bridge** e suporte a acentuação segura.
- **ADR-003 (11/05/2026):** Estabilização na porta 8000 e fixação do **Modo Teste Global**.
- **ADR-004 (11/05/2026):** Hardening v5.2.0: Zero-Trust API Prompt e Graceful Shutdown de processos PowerShell.
- **ADR-005 (12/05/2026):** Safe-State Guard (Two-Phase Commit): Estado de idempotência só é consolidado após confirmação de sucesso em todas as notificações (Email/WhatsApp).
- **ADR-006 (12/05/2026):** Centralizacao de Config: Porta da API e parametros de infraestrutura movidos para `.env`. Acesso via `lib\Lib-Config.psm1`. Correcao de Disco (CIM+PSDrive) eliminando falsos positivos.
- **ADR-008 (12/05/2026):** Auth-Resilience: Dashboard agora limpa automaticamente `localStorage` ao receber 403, forçando novo prompt de chave e evitando estados "zumbis" de desconexão.
- **ADR-009 (12/05/2026):** Dynamic Tooling: Scripts de suporte (.bat/.ps1) devem obrigatoriamente carregar configurações do `.env` via `Lib-Config`, eliminando segredos hardcoded e garantindo consistência com a porta da API.
- ADR-012 (13/05/2026): Encoding Standard (UTF-8 BOM): Definido o uso obrigatório de UTF-8 com BOM para todos os scripts PowerShell (.ps1, .psm1). Isso garante que o motor nativo (v5.1) interprete corretamente literais acentuados pt-BR, evitando corrupção de logs e strings de I/O. Corrigido NameError em notifications.py.
- **ADR-013 (14/05/2026):** Idempotência Granular (Receitas Bloqueadas): Evolução do ADR-005. O estado agora rastreia o sucesso individual de canais (E-mail vs WhatsApp). Se o e-mail for enviado, mas o WhatsApp falhar, o estado parcial é salvo, evitando reenvio de e-mails na execução seguinte.
- **ADR-014 (15/05/2026):** Hardening de Processos e Locks: Implementado tratamento de `AbandonedMutexException` para resiliência de orquestração. Processos do Node.js (WhatsApp) foram movidos de `Start-Process` (descolados) para `System.Diagnostics.Process` (atrelados à árvore) garantindo o funcionamento do `taskkill /T` no timeout. Injeção de `expire_time=2` e `call_timeout` no Oracle para prevenir hangs em nível de socket de rede.
- **ADR-015 (15/05/2026):** Async Process Wrapper (Anti-Deadlock): Implementação da `Lib-Process.psm1` com wrapper C# nativo. Esta arquitetura resolve a limitação de thread do PowerShell 5.1, garantindo que os fluxos `stdout` e `stderr` sejam consumidos simultaneamente em threads separadas. Isso elimina 100% o risco de travamento de buffer (I/O Deadlock) em automações com alto volume de logs ou dados.

---
Mantido pela equipe de Automações & Antigravity AI
