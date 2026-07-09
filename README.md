# Central de Automações — v1.0.0

Este repositório é o núcleo governado para orquestração de automações corporativas. Stack consolidada em Python, PowerShell e Node.js, governança Zero-Trust, observabilidade acionável e Dashboard React "Sala de Instrumentação".

## 🏗️ Arquitetura Técnica (Enterprise Control Tower v1.0.0)

```mermaid
graph TD
    subgraph "FRONTEND — Dashboard SPA"
        UI["Dashboard React v1.0.0<br/>Sala de Instrumentação"]
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
        WORKER["Worker v1.0.0<br/>Graceful Shutdown + JSON Logs"]
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
- **Beneficiamento Snapshot-First**: `/api/beneficiamento/*` consome snapshots locais em `Produção Beneficimento/snapshots/latest`, mantendo leitura de Dashboard sem consulta Oracle em tempo real.
- **Beneficiamento com Histórico Tipado v2**: consultas operacionais usam colunas e índices SQLite; o blob JSON completo fica reservado a auditoria e detalhe sob demanda.
- **Sessões e WAL Endurecidos**: worker e scheduler usam escopo centralizado de sessão, enquanto o checkpoint periódico opera em modo `PASSIVE` para evitar bloqueio de writers.
- **Observabilidade Acionável**: `/api/system/diagnostics` consolida saúde, fila, worker, scheduler, banco/WAL e achados com ação sugerida.
- **Histórico Operacional**: `/api/system/history` mantém snapshots leves de saúde para tendência de fila, heartbeat, WAL e violações recentes sem depender apenas de leitura manual de log.
- **Baseline Operacional Formalizado**: `GET /api/system/baseline` e `diagnostics.operational_baseline` resumem worker, fila, WAL e ownership em status `healthy`, `attention` ou `incident`, com ação recomendada e thresholds explícitos.
- **Portfólio Governado**: `automation.manifest.json` passa a ser o catálogo canônico das automações do hub, e a API expõe `/api/portfolio/health` e `/api/portfolio/drift` para cruzar manifesto, documentação e cadastro runtime.
- **Padrão Arquitetural Governado**: `docs/architecture-standard.md` define as camadas e severidades oficiais do Hub, e `Tools/Test-ArchitectureStandard.ps1` integra esse contrato ao quality gate.
- **Resumo Operacional do Portfólio**: `/api/portfolio/health.summary` e `/api/system/overview.portfolio` agora sintetizam status `healthy`, `attention` ou `incident`, top issue e ação recomendada para drift, documentação obrigatória, registro runtime e SLA.
- **Preflight Governado de Cadastro**: `POST /api/automations/preflight` agora confronta o payload com `automation.manifest.json` quando presente, retornando bloqueios de manifesto, docs obrigatórias e smoke tests antes do save administrativo.
- **Scaffold Governado de Automação**: `Tools/New-Automation.ps1` agora gera manifesto parametrizado, `queue_group` inicial, runbook preenchido com metadados básicos e smoke test mínimo em `Orchestrator/tests/`.
- **Contrato Operacional Versionado**: `overview`, `diagnostics` e `version` agora expõem `contract_version`, checks mínimos de runtime e recovery em camadas para evolução controlada do front-back.
- **Ownership de Execução**: Execuções `RUNNING` passam a registrar `claimed_at`, `worker_instance_id` e `worker_pid`, permitindo diferenciar backlog legítimo de execução órfã.
- **Console Operacional de Recovery**: Diagnósticos agora expõem impacto, prioridade, ação estruturada e atalhos para checkpoint, sincronização de agenda, wake-up/recovery e triagem de execuções.
- **Runbook de Incidente e Rollback**: Procedimento operacional oficial para triagem, contenção, recuperação forte e rollback com validação E2E final em `docs/orchestrator-incident-rollback-runbook.md`.
- **Runtime Compartilhado**: estado de scheduler, wake-up do worker, helpers de execução e criação base de jobs/executions foram centralizados para reduzir acoplamento entre `main.py`, routers e worker.
- **Fila Operacional Auditável**: Execuções agora carregam `retry_count`, `max_retries`, `failure_reason`, `recovery_action` e `queue_group`, habilitando requeue seguro e rastreável.
- **Recovery com Lock de Grupo**: Requeue manual respeita `queue_group` ativo para evitar concorrência entre automações que disputam o mesmo canal, banco ou recurso operacional.
- **Evidência E2E Governada**: `Tools/Test-PlaywrightEvidence.ps1` valida que entregas com Playwright registrem URL real, ordem final, console limpo e resultado aprovado.
- **Schema Evolutivo com Alembic**: Startup aplica migrações estruturadas de SQLite via Alembic e usa `alembic_version` como fonte auditável de schema.
- **Diagnóstico de Execuções Acima do Limite**: `/api/system/diagnostics` sinaliza execuções `RUNNING` que excederam `max_runtime_minutes`, diferenciando processamento longo legítimo de provável travamento operacional.
- **Validação Administrativa**: API expõe validação de `schedule` e `.env` antes de persistência.
- **Preflight de Cadastro**: `POST /api/automations/preflight` centraliza validação de `script_path`, agenda, canais e diretório resolvido antes de `create/update`.
- **Scaffold Completo de Automação**: `Tools/New-Automation.ps1` agora gera `README.md`, `CONTEXT.md`, `run.ps1`, `automation.manifest.json` e runbook inicial em `docs/runbooks/`.
- **Worker Resilience**: Encerramento limpo de processos PowerShell para evitar consumo de recursos zumbi.
- **Performance SQLite**: Pragmas otimizados para operação em RAM (`temp_store=MEMORY`).
- **Skills Compartilhadas**: `.github/skills/` é a fonte canônica das 7 skills ativas; `.gemini/skills/` é apenas o espelho de compatibilidade para Gemini CLI e Antigravity.
- **Dashboard React "Sala de Instrumentação"**: identidade visual industrial (grafite + ciano/âmbar), IBM Plex, react-router com deep-links, design system em `Dashboard/src/components/ui/`, uPlot para time series.
- **OBs Paradas Fase (OBP-04)**: automação de visibilidade de OBs paradas por fase, cards PNG via WhatsApp, cron diário às 05:30 e 14:00, com terceiro disparo às 22:30 (Seg-Sáb) ou 23:00 (Dom).

---
Mantido pela equipe de Automações
