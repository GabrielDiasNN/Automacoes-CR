# Orchestrator — contexto de módulo

Carregado apenas ao trabalhar em `Orchestrator/`. As regras universais (encoding, caminhos, banco, Zero-Trust, commits, E2E, manifesto) estão no `CLAUDE.md` da raiz.

## Módulos (`Orchestrator/app/`)

- `main.py` — startup FastAPI: registra routers, monta SPA, inicializa Alembic e jobs APScheduler. Chama `register_event_loop(asyncio.get_running_loop())` no lifespan para viabilizar wake-up thread-safe do worker.
- `worker.py` (em `Orchestrator/`, fora de `app/`) — loop de execução: consome fila, spawn de processos PowerShell, graceful shutdown.
- `runtime.py` — estado compartilhado entre `main.py`, routers e worker. Inclui `register_event_loop` + `trigger_worker_wakeup` (usa `loop.call_soon_threadsafe` — **nunca** chamar `task_queued_event.set()` diretamente de endpoint sync, pois endpoints FastAPI sync rodam em threadpool separada do event loop).
- `database.py` — engine SQLite WAL, `SessionLocal`, `session_scope` (context manager para sessões fora do FastAPI). `purge_old_executions` preserva as últimas 50 execuções por automação via subquery com `ROW_NUMBER() OVER (PARTITION BY automation_id)`.
- `migrations/` (em `Orchestrator/`, fora de `app/`) — Alembic; `env.py` usa `render_as_batch=True` para compatibilidade SQLite.
