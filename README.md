# Central de Automações — v6.0.0 Enterprise High-Performance 🚀

Este repositório é o núcleo soberano para orquestração de automações corporativas. O projeto atingiu o **Estado de Excelência v6.0.0**, operando com arquitetura de alta performance, resiliência de escala (Adaptive Polling) e governança de segurança avançada Zero-Trust.

## 🏗️ Arquitetura Técnica (Enterprise Control Tower v6.0.0)

```mermaid
graph TD
    subgraph "FRONTEND — Dashboard SPA"
        UI["Dashboard v6.0.0<br/>Zero-Trust + ASCII-Safe"]
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
        WORKER["Worker v5.1.1<br/>Graceful Shutdown + JSON Logs"]
        PRIORITY["Priority Queue<br/>HIGH/NORMAL/LOW"]
        SCHEDULER["APScheduler<br/>WAL Checkpoint + Purge"]
        WORKER --- PRIORITY
        WORKER --- SCHEDULER
    end

    UI -->|REST + WS| ROUTERS
    ROUTERS --> DB[(SQLite WAL Engine)]
```

## 🎯 Novidades v5.4.0
- **UTF-8 Universal Encoding**: Adoção global do padrão UTF-8 para código-fonte e logs, abolindo as restrições de ASCII-Safe e Base64 Bridge para garantir máxima legibilidade humana e suporte nativo a PT-BR.
- **Zero-Trust Auth**: O Dashboard solicita a API Key dinamicamente, eliminando segredos no código.
- **Worker Resilience**: Encerramento limpo de processos PowerShell para evitar consumo de recursos zumbi.
- **Performance SQLite**: Pragmas otimizados para operação em RAM (`temp_store=MEMORY`).

---
Mantido pela equipe de Automações & Antigravity AI
