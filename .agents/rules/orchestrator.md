# Regra de Workspace: Orchestrator (Backend FastAPI)

Aplica-se ao desenvolvimento, testes e manutenção em `Orchestrator/`.

## Ambiente e Execução

- **Virtualenv Oficial**: O virtualenv do projeto fica na **raiz** do repositório (`.venv\`), e não dentro de `Orchestrator/`. Todos os comandos Python devem utilizá-lo.
- **Testes Unitários e Integração**:
  `cd Orchestrator && ..\.venv\Scripts\pytest -v`
  *(A suíte padrão exclui testes E2E via `addopts` no `pytest.ini`)*.
- **Testes por marcador**:
  `cd Orchestrator && ..\.venv\Scripts\pytest -m integracao -v`
- **Migrações de Banco de Dados**:
  `cd Orchestrator && ..\.venv\Scripts\alembic upgrade head`
  *(O Alembic está configurado com `render_as_batch=True` para suportar migrações estruturais no SQLite)*.

## Arquitetura de Módulos (`Orchestrator/app/`)

- `main.py`: Ponto de entrada FastAPI, montagem de rotas, static files da SPA e lifespan com registro de event loop.
- `worker.py` (em `Orchestrator/`): Loop assíncrono de execução de tarefas, spawn de subprocessos PowerShell e encerramento gracioso.
- `runtime.py`: Estado compartilhado entre `main.py`, routers e worker.
  - **Thread-Safety Crítico**: Use sempre `trigger_worker_wakeup` via `loop.call_soon_threadsafe`. Nunca chame `task_queued_event.set()` diretamente de endpoints síncronos, pois estes rodam em threadpool separado.
- `database.py`: Engine SQLite WAL e context manager `session_scope`.
  - **Sessões SQLAlchemy**: Fora do contexto direto de endpoints FastAPI, use obrigatoriamente `with session_scope() as session:`.
  - **Retenção**: `purge_old_executions` preserva um número fixo de execuções mais recentes por automação via window function — o valor canônico está na própria função (`Orchestrator/app/database.py`), não reproduzido aqui.

## Manifesto de Automação

- Toda automação registrada no Orchestrator deve possuir `automation.manifest.json`.
- A ausência de manifesto gera status `incident` e bloqueia criação/atualização no preflight (`POST /api/automations/preflight`).
