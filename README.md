# Central de Automacoes (Hub Soberano) — v5.1.0 Enterprise 🚀

Este repositório é o núcleo soberano para orquestração de automações corporativas. O projeto atingiu o **Estado de Excelência v5.0.0 Enterprise**, operando com arquitetura hardened, resiliência de escala (WAL Engine) e governança de segurança avançada.

## 🏗️ Arquitetura Tecnica (Enterprise Control Tower v5)

```mermaid
graph TD
    subgraph "FRONTEND — Dashboard SPA"
        UI[Dashboard v5.0<br/>Glassmorphism + Local Assets]
        WS_CLIENT[WebSocket Client<br/>Logs + Events Replay]
        UI --> WS_CLIENT
    end

    subgraph "GATEWAY — FastAPI v5 (Hardened)"
        ROUTERS[Routers Modulares<br/>Auto, Exec, Sys, WS]
        MIDDLEWARE[Middleware Stack<br/>RateLimit, CORS, Auth, Timing]
        UTILS[Utilities Layer<br/>Validation & Audit]
        ROUTERS <--> MIDDLEWARE
        ROUTERS --- UTILS
    end

    subgraph "CORE — Motor de Execucao v5"
        WORKER[Worker v5<br/>JSON Logs + Correlation ID]
        PRIORITY[Priority Queue<br/>HIGH/NORMAL/LOW]
        SCHEDULER[APScheduler<br/>WAL Checkpoint + Purge]
        WORKER --- PRIORITY
        WORKER --- SCHEDULER
    end

    subgraph "DATA — Persistencia Hardened"
        DB[(SQLite WAL Engine<br/>Auto-Checkpoint)]
        AUDIT[Audit Log System<br/>Enterprise Tracking]
        DB --- AUDIT
    end

    UI -->|REST + WS| ROUTERS
    ROUTERS --> DB
    WORKER -->|Consome Fila Priorizada| DB
    WORKER -->|Broadcast (Retry 3x)| ROUTERS
```

---

## 🚀 Modulos de Automacao (Estado de Excelencia)

### 1. [**Receitas Bloqueadas**](file:///c:/Automacoes/Receitas%20Bloqueadas/README.md) (Soberana v2.1.2) 🌟
- **Diferencial**: Idempotência estrita, geração de Excel analítico e alertas multicanal.

### 2. [**Receitas Emitidas**](file:///c:/Automacoes/Receitas%20Emitidas/README.md) (Nativo v2.5.0) 🚀
- **Diferencial**: Comunicação via *IPC Stdio Pipes* em memória para ultra-performance.

### 3. [**Montagem de Terceirizados**](file:///c:/Automacoes/Montagem%20de%20Terceirizados/README.md) (Pure-Native v2.0) ⚙️
- **Diferencial**: Validação fiscal nativa direta no Oracle via Python (Thick Mode).

---

## 🛠️ Operacao Enterprise v5.0

- **Torre de Comando**: Dashboard reativo servido nativamente em `http://localhost:8766/dashboard/`.
- **WAL Engine**: SQLite operando com **Auto-Checkpoint** a cada 30 min, garantindo resiliência sob carga concorrente.
- **Worker v5**: Logging JSON estruturado com **Correlation ID** (rastreabilidade total do pipeline de execução).
- **Security Hardening**: **Rate Limiting** por IP (120 req/min) e **CORS restrito** a localhost (Security Zero-Trust).
- **Priority Queue**: Suporte nativo a filas de prioridade (HIGH, NORMAL, LOW) para disparos críticos.
- **Maintenance Jobs**: Rotinas automáticas de **Purge** (limpeza de execuções > 90 dias) e integridade de banco.
- **B64 Bridge**: Interoperabilidade total de caracteres especiais (ç, ã, é) entre automações e Dashboard via Base64.
- **Global Test Mode**: Chave mestre de Sandbox para isolamento total de execuções em ambiente de teste.

### Tabela de Erros e Diagnosticos (Protocolo v5)

| Codigo  | Descricao                                           | Acao do Hub               |
| :------ | :-------------------------------------------------- | :------------------------ |
| **0**   | Sucesso Absoluto                                    | Finaliza Ciclo            |
| **2**   | Sucesso: Idempotencia (Sem alteracoes)              | Finaliza Ciclo (Suprimido) |
| **3**   | Sucesso: Sem Dados Encontrados                      | Finaliza Ciclo            |
| **4**   | Erro Tecnico (Python/Node)                          | Alerta Multicanal + Audit |
| **9**   | Falha de Pre-Flight (Validacao script_path)         | **Bloqueio de Execucao**  |
| **429** | Rate Limit Excedido                                 | HTTP 429 + Retry-After    |
| **TIMEOUT**| Execução excedeu tempo máximo                      | Taskkill Tree + Alerta    |

---

## 📏 Governanca (Protocolo V.A.L.E.G. v5)
O projeto atende aos 5 pilares de excelência:
1.  **V - Validação**: Pre-flight de existência física de scripts no momento do cadastro.
2.  **A - Arquitetura**: Camada `app/utils.py` centralizada, eliminando código duplicado.
3.  **L - Logging**: Logs estruturados JSON em todo o pipeline (Orchestrator + Worker).
4.  **E - Escala**: SQLite WAL com checkpoint automático e fila de prioridade.
5.  **G - Governança**: Rate limiting, trilha de auditoria para manutenção e CORS hardened.

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo é uma **unidade de contexto vital** v5.1.0.
- **Obrigação:** Deve ser atualizado imediatamente após qualquer alteração estrutural ou de regra de negócio.
- **Objetivo:** Manter a "memória central" sincronizada (AI-Sovereignty).

---
Mantido pela equipe de Automacoes & Antigravity AI
acoes & Antigravity AI
