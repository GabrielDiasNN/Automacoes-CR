# Changelog — Hub de Automações (Soberano)

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O projeto segue os princípios de **Resiliência, Escala e Governança (Protocolo V.A.L.E.G.)**.

---

## [5.1.3] — 2026-05-11
### 🛠️ Corrigido
- **Receitas Emitidas (Idempotência)**: Corrigida falha que causava disparos duplicados de e-mails. Removidos campos voláteis (`SYSDATE`/`Valida_Atualizacao` e `DIAS_PESADO`) da query SQL e implementada ordenação determinística (`NUMERO_OB`) no Python para garantir estabilidade do hash de idempotência.

---

## [5.1.2] — 2026-05-11
### 🏗️ Governança e Qualidade
- **Tipagem Estrita (Mypy)**: Correção abrangente de assinaturas de funções e anotações de tipo em todas as automações (`Montagem de Terceirizados`, `Receitas Bloqueadas`, `Receitas Emitidas`) e no `Orchestrator`, alcançando conformidade com `mypy --strict`.
- **Qualidade de Código (Pylint)**: Refatoração e adequação de sintaxe e complexidade ciclomática para atingir nota máxima (10.00/10) nas validações do Pylint.
- **Validação Autônoma**: Script de governança `Test-PythonGovernance.ps1` aprimorado para injetar o contexto `.venv`, garantindo validações reais de lint e type hints nos hooks de pre-commit.
- **Testes Unitários**: Validação dos fluxos do FastAPI (CRUD, schemas de bloqueio de Path Traversal) via `pytest`.

---

## [5.1.1] — 2026-05-11
### 🏗️ Governança (AI-Native)
- **Documentação Contínua**: Atualizado `GEMINI.md` para tornar obrigatória a atualização do `CHANGELOG.md` em cada commit bem-sucedido.
- **Protocolo de Histórico**: Implementada regra de sincronismo para garantir trilha de auditoria técnica legível por humanos e IA.

---

## [5.1.0] — 2026-05-11
### ✨ Adicionado
- **Trava de Regressão de Encoding**: Script `Tools/Test-EncodingResilience.ps1` para validar round-trip de caracteres especiais (UTF-8).
- **Soberania de Encoding**: Gatilho preventivo no Git Hook (pre-commit) que bloqueia caracteres não-ASCII no código-fonte.
- **Variavel de Ambiente**: `PYTHONIOENCODING=utf-8` adicionada ao `.env` para estabilidade global.

### 🛠️ Corrigido
- **Worker v5.1**: Captura de logs de subprocessos PowerShell forçada para UTF-8 com substituição de erros, eliminando corrupção por CP1252.
- **Divergência de Porta**: Estabilização do Dashboard e API na porta oficial `8000`.
- **Timezone Heartbeat**: Ajuste na lógica de ping do Worker para maior precisão no Dashboard.

### 🧹 Removido (Limpeza Técnica)
- Pasta `Deprecated/`: Remoção definitiva do monitoramento v4.0 e scripts VBA legados.
- Diretório `Orchestrator/scratch/`: Limpeza de rascunhos de desenvolvimento.
- Diretório `Orchestrator/tests/test/`: Remoção de scripts de teste redundantes.
- Arquivos de lock e caches: `.pytest_cache`, `__pycache__` e arquivos `.lock` de automações.

---

## [5.0.0] — 2026-05-09 (Enterprise Upgrade)
### 🏗️ Arquitetura
- **Hub Soberano v5**: Migração completa da arquitetura monolítica para um modelo Control Tower baseado em FastAPI.
- **Modular Routers**: Divisão da API em `automations`, `executions`, `system` e `websocket`.
- **Utilities Layer**: Centralização de lógica de auditoria e validação em `app/utils.py`.

### 🚀 Funcionalidades
- **SQLite WAL Engine**: Implementação de modo WAL com auto-checkpoint (APScheduler) para alta concorrência.
- **Priority Queue**: Suporte a filas de prioridade (HIGH/NORMAL/LOW) para execuções.
- **Log Replay**: Sistema de WebSocket que envia o histórico de logs imediatamente após a conexão.
- **Rate Limiting**: Proteção de API com limite de 120 requisições/minuto por IP.
- **Audit Log**: Trilha de auditoria persistente para todas as ações administrativas.

### 🎨 Interface
- **Dashboard v5.0**: Nova UI reativa com Design System Glassmorphism e ativos (fonts/JS) 100% locais para operação offline.

---

## [4.0.1] — 2026-04-20
### 🛡️ Estabilização
- Implementação inicial do Protocolo V.A.L.E.G.
- Refatoração do `MonitorAutomacoes.ps1` para maior resiliência.
- Padronização de logs e tratamento de erros.

---
Mantido pela equipe de Automações & Antigravity AI
