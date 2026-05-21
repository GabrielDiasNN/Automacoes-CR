# Central de Automações — v7.0.0 Dashboard Operacional e Governança

Este repositório é o núcleo soberano para orquestração de automações corporativas. O projeto opera no **Estado de Excelência v7.0.0**, com stack consolidada em Python, PowerShell e Node.js, governança Zero-Trust, observabilidade acionável e um conjunto compartilhado de skills para ChatGPT/Codex, Gemini CLI e Antigravity.

## 🏗️ Arquitetura Técnica (Enterprise Control Tower v7.0.0)

```mermaid
graph TD
    subgraph "FRONTEND — Dashboard SPA"
        UI["Dashboard v9.1.0<br/>Zero-Trust + UTF-8 Nativo"]
        WS_CLIENT["WebSocket Client<br/>Logs + Events Replay"]
        UI --> WS_CLIENT
    end

    subgraph "GATEWAY — FastAPI v5 (Hardened)"
        ROUTERS["Routers Modulares<br/>Auto, Exec, Sys, WS"]
        MIDDLEWARE["Middleware Stack<br/>RateLimit, CORS, Auth, Timing"]
        UTILS["Utilities Layer<br/>Validation & Audit"]
        ROUTERS <--> MIDDLEWARE
        ROUTERS --- UTILS
    end

    subgraph "CORE — Motor de Execução v5"
        WORKER["Worker v9.1.0<br/>Graceful Shutdown + JSON Logs"]
        PRIORITY["Priority Queue<br/>HIGH/NORMAL/LOW"]
        SCHEDULER["APScheduler<br/>WAL Checkpoint + Purge"]
        WORKER --- PRIORITY
        WORKER --- SCHEDULER
    end

    UI -->|REST + WS| ROUTERS
    ROUTERS --> DB[(SQLite WAL Engine)]
```

## 🎯 Estado Atual do Hub
- **UTF-8 Nativo Governado**: Código-fonte e logs operam em UTF-8, com PowerShell `.ps1`/`.psm1` em UTF-8 com BOM e demais arquivos textuais em UTF-8 sem BOM, conforme `GEMINI.md`.
- **Zero-Trust Auth**: O Dashboard solicita a API Key dinamicamente, eliminando segredos no código.
- **Observabilidade Acionável**: `/api/system/diagnostics` consolida saúde, fila, worker, scheduler, banco/WAL e achados com ação sugerida.
- **Contrato Operacional Versionado**: `overview`, `diagnostics` e `version` agora expõem `contract_version`, checks mínimos de runtime e recovery em camadas para evolução controlada do front-back.
- **Console Operacional de Recovery**: Diagnósticos agora expõem impacto, prioridade, ação estruturada e atalhos para checkpoint, sincronização de agenda, wake-up/recovery e triagem de execuções.
- **Runbook de Incidente e Rollback**: Procedimento operacional oficial para triagem, contenção, recuperação forte e rollback com validação E2E final em `docs/orchestrator-incident-rollback-runbook.md`.
- **Runtime Compartilhado**: estado de scheduler, wake-up do worker, helpers de execução e criação base de jobs/executions foram centralizados para reduzir acoplamento entre `main.py`, routers e worker.
- **Fila Operacional Auditável**: Execuções agora carregam `retry_count`, `max_retries`, `failure_reason`, `recovery_action` e `queue_group`, habilitando requeue seguro e rastreável.
- **Recovery com Lock de Grupo**: Requeue manual respeita `queue_group` ativo para evitar concorrência entre automações que disputam o mesmo canal, banco ou recurso operacional.
- **Evidência E2E Governada**: `Tools/Test-PlaywrightEvidence.ps1` valida que entregas com Playwright registrem URL real, ordem final, console limpo e resultado aprovado.
- **Schema Evolutivo com Alembic**: Startup aplica migrações estruturadas de SQLite via Alembic e usa `alembic_version` como fonte auditável de schema.
- **Diagnóstico de Execuções Acima do Limite**: `/api/system/diagnostics` sinaliza execuções `RUNNING` que excederam `max_runtime_minutes`, diferenciando processamento longo legítimo de provável travamento operacional.
- **Validação Administrativa**: API expõe validação de `schedule` e `.env` antes de persistência.
- **Worker Resilience**: Encerramento limpo de processos PowerShell para evitar consumo de recursos zumbi.
- **Performance SQLite**: Pragmas otimizados para operação em RAM (`temp_store=MEMORY`).
- **Skills Compartilhadas**: `.github/skills/` é a fonte canônica das 7 skills ativas; `.gemini/skills/` é apenas o espelho de compatibilidade para Gemini CLI e Antigravity.

---
Mantido pela equipe de Automações & Antigravity AI
