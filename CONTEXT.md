# Cognitive Context: Automacoes Hub v5.0.0 (Enterprise)

## Repository Philosophy
Este repositório é um ecossistema de automações **AI-Native**, operando na versão **v5.0.0 (Enterprise)**. Upgrade do v4.0.1 com os 5 pilares do Protocolo V.A.L.E.G. aplicados ao Orchestrator: Validação pré-flight de scripts, Arquitetura deduplicada, Logging JSON com Correlation ID, Escala com WAL Checkpoint e fila priorizada, Governança com Rate Limiting e CORS hardened.

## System Architecture (v5.0.0 Enterprise)
O hub opera sob o modelo **Control Tower Enterprise v5.0.0**:
- **Modular Control Plane:** Backend FastAPI organizado em 4 routers principais (`automations`, `executions`, `system`, `websocket`).
- **Utilities Layer:** `app/utils.py` centraliza `log_audit()`, `get_client_ip()` e `validate_script_path()` — elimina duplicação entre routers.
- **Dashboard Integrado:** Front-end SPA servido nativamente pelo Orchestrator em `/dashboard/`, com assets (fonts/JS) locais para estabilidade offline.
- **Log Replay Engine:** WebSocket aprimorado que despacha o histórico completo de logs de uma execução imediatamente após o handshake de conexão.
- **Motor de Execução v5:** Worker com logging JSON estruturado + Correlation ID por tarefa + retry 3x no broadcast + bug task_start_ts corrigido.
- **WAL Checkpoint Engine:** APScheduler executa `PRAGMA wal_checkpoint(PASSIVE)` a cada 30 min automaticamente.
- **Daily Purge Job:** APScheduler executa purge de execuções > 90 dias às 03:00 (configurável via `EXECUTION_RETENTION_DAYS`).
- **Rate Limiting:** Sliding window 120 req/min por IP (configurável via `RATE_LIMIT_RPM`).
- **Priority Queue:** Campo `priority` (HIGH/NORMAL/LOW) na tabela `executions` com índice composto para ordenação eficiente.
- **Audit Log System:** Trilha de auditoria persistente que registra toda ação administrativa incluindo CHECKPOINT e PURGE.
- **Data Engine Hardened:** SQLite em modo **WAL** com `ForeignKeys = ON`, garantindo resiliência sob carga concorrente.

## Directory Structure (v5.0 Enterprise)
```text
C:\Automacoes\
├── Infrastructure\     # [NUCLEO] Watchdog, API Launcher (v5), Instaladores
├── Orchestrator\       # [BACKEND] 
│   ├── app/            # Modulos FastAPI (routers, models, schemas, middleware, utils)
│   │   └── utils.py    # [NEW v5] Utilities: log_audit, get_client_ip, validate_script_path
│   ├── Logs/           # Logs rotativos (JSON estruturado) do Orchestrator e Worker
│   ├── worker.py       # Motor Concorrente v5 (JSON logs + Correlation ID + retry)
│   └── automacoes.db   # Banco SQLite v5 (Hardened, WAL auto-checkpoint)
├── Dashboard\          # [FRONTEND]
│   ├── css/            # Design System (Glassmorphism)
│   ├── js/             # Camada API e Logica SPA
│   └── dashboard.html  # Interface 4 abas
├── lib\                # [SHARED] Bibliotecas PowerShell e Ativos
├── Logs\               # [LOGS] Logs unificados dos robos
└── [Automacoes]\       # [MODULES] Pastas individuais por robo
```

## Business Rules (Protocolo v5)
1.  **Strict Concurrency**: O Worker permite N tarefas simultâneas (configurável via `.env`), com proteção contra execução duplicada do mesmo ID.
2.  **Priority Queue**: Execuções suportam `priority` = HIGH | NORMAL | LOW. Índice composto garante ordenação eficiente na fila.
3.  **Graceful Shutdown**: Captura de sinais SIGTERM para finalização limpa de tarefas zumbis e registro no Audit Log.
4.  **Active Heartbeat**: O sistema considera o Worker "Inativo" se o heartbeat exceder 60s, alertando o Dashboard em tempo real.
5.  **Schema Validation + Pre-flight V**: 100% dos inputs da API são validados por Pydantic + existência física do script validada no CREATE.
6.  **WAL Auto-Checkpoint**: APScheduler executa checkpoint a cada 30min, prevenindo crescimento ilimitado do `.db-wal`.
7.  **Daily Purge**: Execuções finalizadas há mais de `EXECUTION_RETENTION_DAYS` (default: 90) são removidas às 03:00.

## Security & Resilience (v5 Enterprise)
- **Timing-Safe Auth**: Comparação de API Key via `hmac.compare_digest` + log de falhas de auth com IP.
- **Rate Limiting**: Sliding window 120 req/min por IP via `RateLimitMiddleware` (HTTP 429 com `Retry-After`).
- **CORS Hardened**: `ALLOWED_ORIGINS` restrito a localhost por padrão (configurável via `.env`).
- **Integridade Referencial**: Uso obrigatório de Foreign Keys no SQLite para evitar execuções órfãs.
- **Atomic Backup**: Implementação de `VACUUM INTO` para backups consistentes e automáticos (rotação: 7 cópias).
- **Middleware Observability**: Rastreabilidade total através de `X-Request-Id` + `correlation_id` nos logs do Worker.
- **Pre-flight Validation**: `validate_script_path()` em `utils.py` bloqueia scripts inexistentes e path traversal antes de criar a automação.

## Enterprise API Endpoints (v5)
| Endpoint | Método | Descrição |
|---|---|---|
| `/api/system/health` | GET | Health + `wal_size_mb` |
| `/api/system/version` | GET | Versão, Python, uptime, max_workers |
| `/api/system/checkpoint` | POST | WAL checkpoint manual |
| `/api/system/purge` | POST | Purge de execuções antigas |
| `/api/system/backup` | POST | Backup atômico (VACUUM INTO) |
| `/api/system/audit` | GET | Trilha de auditoria |

- **Obrigação:** Deve ser a primeira leitura da IA e **DEVE** ser atualizado após mudanças estruturais.
- **Objetivo:** Economia de tokens e precisão cirúrgica na evolução do Hub.

---

## 🧠 Gestão de Contexto (AI-Native)
Este é o documento mestre de contexto cognitivo v5.0.
- **Obrigação:** Deve ser a primeira leitura da IA e **DEVE** ser atualizado após mudanças estruturais.
- **Objetivo:** Economia de tokens e precisão cirúrgica na evolução do Hub.
- **ADR-001 (09/05/2026):** Upgrade v4→v5 aplicando Protocolo V.A.L.E.G. completo. Deduplicação via `utils.py`, WAL checkpoint automático, Rate Limiting, CORS restrito a localhost, Priority Queue, Worker com JSON logs + Correlation ID.

---
Mantido pela equipe de Automacoes & Antigravity AI
