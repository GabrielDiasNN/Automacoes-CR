# Cognitive Context: Automações Hub v5.2.0 (Enterprise)

## Repository Philosophy
Este repositório é um ecossistema de automações **AI-Native**, operando na versão **v5.2.0 (Enterprise)**. O sistema segue o **Protocolo V.A.L.E.G.** (Validação, Arquitetura, Logging, Escala e Governança) com foco em resiliência e segurança Zero-Trust.

## System Architecture (v5.2.0 Enterprise)
...
- **ADR-007 (12/05/2026):** Sincronização v5.2.0: Consolidação de versões em toda a stack, hardening de seguranca (API Key robusta), eliminação de URLs hardcoded e refatoração arquitetural de imports/typing.
- **Zero-Trust Dashboard**: Front-end não armazena chaves; solicita via prompt e persiste em `localStorage` seguro.
- **UTF-8 Native Source (v5.4.0)**: Todo código-fonte (.py, .js, .ps1) opera nativamente em UTF-8. A restrição ASCII-Safe e o protocolo Base64 Bridge foram descontinuados para maximizar a legibilidade.
- **Graceful Worker**: Worker v5.2.0 monitora processos ativos e garante o `taskkill` de toda a árvore de processos no shutdown.
- **SQLite Hardened**: WAL mode com `synchronous=NORMAL` e `temp_store=MEMORY` para máxima performance de I/O.
- **Unified JSON Logging**: Loggers do Orchestrator e Worker unificados para rastreabilidade via `correlation_id`.

## 🧠 Gestão de Contexto (AI-Native)
- **Estado:** Estabilizado v5.4.4 (Hardened, Governance & Clean).
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

---
Mantido pela equipe de Automações & Antigravity AI
