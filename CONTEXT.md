# Cognitive Context: Automações Hub v5.2.0 (Enterprise)

## Repository Philosophy
Este repositório é um ecossistema de automações **AI-Native**, operando na versão **v5.2.0 (Enterprise)**. O sistema segue o **Protocolo V.A.L.E.G.** (Validação, Arquitetura, Logging, Escala e Governança) com foco em resiliência e segurança Zero-Trust.

## System Architecture (v5.2.0 Enterprise)
...
- **ADR-007 (12/05/2026):** Sincronização v5.2.0: Consolidação de versões em toda a stack, hardening de seguranca (API Key robusta), eliminação de URLs hardcoded e refatoração arquitetural de imports/typing.
- **Zero-Trust Dashboard**: Front-end não armazena chaves; solicita via prompt e persiste em `localStorage` seguro.
- **ASCII-Safe Source**: Todo código-fonte (.py, .js) é restrito ao range 0-127. Acentuação pt-BR é gerida via HTML Entities (Front) ou Escapes Unicode (Back).
- **Graceful Worker**: Worker v5.2.0 monitora processos ativos e garante o `taskkill` de toda a árvore de processos no shutdown.
- **SQLite Hardened**: WAL mode com `synchronous=NORMAL` e `temp_store=MEMORY` para máxima performance de I/O.
- **Unified JSON Logging**: Loggers do Orchestrator e Worker unificados para rastreabilidade via `correlation_id`.

## 🧠 Gestão de Contexto (AI-Native)
- **ADR-001 (09/05/2026):** Upgrade v4→v5 aplicando Protocolo V.A.L.E.G. completo.
- **ADR-002 (11/05/2026):** Implementação da **B64 Bridge** e suporte a acentuação segura.
- **ADR-003 (11/05/2026):** Estabilização na porta 8000 e fixação do **Modo Teste Global**.
- **ADR-004 (11/05/2026):** Hardening v5.2.0: Zero-Trust API Prompt e Graceful Shutdown de processos PowerShell.
- **ADR-005 (12/05/2026):** Safe-State Guard (Two-Phase Commit): Estado de idempotência só é consolidado após confirmação de sucesso em todas as notificações (Email/WhatsApp).
- **ADR-006 (12/05/2026):** Centralizacao de Config: Porta da API e parametros de infraestrutura movidos para `.env`. Acesso via `lib\Lib-Config.psm1`. Correcao de Disco (CIM+PSDrive) eliminando falsos positivos.
- **ADR-008 (12/05/2026):** Auth-Resilience: Dashboard agora limpa automaticamente `localStorage` ao receber 403, forçando novo prompt de chave e evitando estados "zumbis" de desconexão.
- **ADR-009 (12/05/2026):** Dynamic Tooling: Scripts de suporte (.bat/.ps1) devem obrigatoriamente carregar configurações do `.env` via `Lib-Config`, eliminando segredos hardcoded e garantindo consistência com a porta da API.

---
Mantido pela equipe de Automações & Antigravity AI
