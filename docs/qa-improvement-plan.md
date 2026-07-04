# Plano de Melhoria de QA — Automações Hub v9.5.0

> **Gerado em:** 02/07/2026 | **Atualizado em:** 03/07/2026 (v2 — worker.py + conftest.py lidos)
> **Versão analisada:** v9.5.0 (Operational Baseline)
> **Escopo:** Leitura de 40+ arquivos — Orchestrator, Dashboard, domínios, lib, CI, worker.py (26 KB), conftest.py completo

---

## 1. Diagnóstico do Estado Atual

### 1.1 Inventário de Testes Existentes

| Arquivo de Teste | Tamanho | Domínio |
|---|---|---|
| `test_automations_crud.py` | 21 KB | CRUD de automações |
| `test_beneficiamento.py` | 33 KB | Beneficiamento (integração) |
| `test_schedule_advanced.py` | 18 KB | Agendamento (integração) |
| `test_e2e_dashboard.py` | 15 KB | Dashboard E2E Playwright |
| `test_system.py` | 12 KB | Sistema/Diagnóstico |
| `test_executions.py` | 11 KB | Execuções |
| `test_filters.py` | 10 KB | Filtros de execução |
| `test_api_smoke_critical.py` | 10 KB | Smoke crítico de API |
| `test_montagem_terceirizados.py` | 12 KB | Montagem Terceirizados |
| `test_receitas_bloqueadas.py` | 12 KB | Receitas Bloqueadas |
| `test_portfolio.py` | 8 KB | Portfólio |
| `test_diagnostics.py` | 8 KB | Diagnósticos |
| `test_beneficiamento_unit.py` | 9 KB | Beneficiamento (unitário) |
| `test_worker_queue.py` | 7 KB | Fila do Worker |
| `test_queue_rules.py` | 6 KB | Regras de Fila |
| `test_sanitization.py` | 5 KB | Sanitização |
| `test_worker_loop.py` | 4 KB | Loop do Worker |
| `test_notifications.py` | 4 KB | Notificações |
| `test_api_contracts.py` | 3 KB | Contratos de API |
| `test_timezone_contract.py` | 3 KB | Fuso Horário |
| `test_automations_ide.py` | 3 KB | IDE de Automações |
| `test_validation.py` | 3 KB | Validação |
| `test_purge_retention.py` | 2 KB | Purge/Retenção |
| `test_scaffold_governance.py` | 2 KB | Scaffold Governança |
| `test_obs_paradas_fase.py` | 2 KB | OBs Paradas |
| `test_audit_utils.py` | 1 KB | Auditoria |
| `test_database_schema.py` | 1 KB | Schema do Banco |
| `test_receitas_emitidas.py` | 1 KB | Receitas Emitidas |
| `test_recovery.py` | 1 KB | Recovery |
| `test_log_broadcast.py` | 1 KB | Log Broadcast |
| `test_websocket_broadcast_auth.py` | 1 KB | WebSocket Auth |

**Total:** 31 arquivos | ~200 KB de código de teste

### 1.2 Diagnóstico do `conftest.py` (lido integralmente)

O `conftest.py` é sofisticado e bem construído. Fornece:

- `pytest_collection_modifyitems`: marcação automática `unitario`/`integracao` por fixtures usadas ✅
- `db_session`: SQLite in-memory + `StaticPool` + `PRAGMA foreign_keys=ON` ✅
- `client`: patch profundo de `SessionLocal`, `engine`, `PROJECT_ROOT`, `scheduler_runtime`, `websocket_router` ✅
- `force_env_vars` (autouse): garante `ORCHESTRATOR_API_KEY`, `ORCHESTRATOR_DB_PATH`, `RATE_LIMIT_RPM` ✅
- `beneficiamento_historico_seed` (session-scope): semeia 6 registros deterministas para E2E ✅

**Gaps confirmados no `conftest.py`:**

| Gap | Descrição |
|---|---|
| ❌ `mock_oracle_connection` ausente | Nenhuma fixture padronizada para `oracledb.connect` — cada teste teria que reimplementar |
| ❌ `worker_env_vars` ausente | Sem fixture para variáveis de ambiente do worker (`HUB_API_PORT`, `WORKER_MAX_CONCURRENCY`, `WORKER_INSTANCE_ID`) |
| ❌ `mock_subprocess_popen` ausente | Sem fixture para `subprocess.Popen` — testes de worker não podem simular processo PowerShell |
| ❌ `mock_requests` ausente | Sem fixture para `requests.get/post` — wakeup listener e log flusher não têm mock padronizado |
| ❌ `shutdown_event` fixture ausente | `shutdown_event` é global em `worker.py`; sem reset entre testes, estado vaza entre casos |
| ⚠️ `client` fixture faz 9 patches manuais | Frágil: qualquer novo módulo que use `SessionLocal` precisa de patch explícito ou os testes usam banco real |

### 1.3 Diagnóstico do `worker.py` (lido integralmente — 26 KB)

Funções e comportamentos críticos identificados que **não têm testes correspondentes**:

| Função | Risco | Comportamento sem teste |
|---|---|---|
| `_force_kill(pid)` | 🔴 | `taskkill /F /T /PID` com `timeout=15` — e se `taskkill` exceder o timeout? |
| `_monitor_process()` | 🔴 | Verifica DB a cada `_DB_CHECK_INTERVAL=5s`; timeout detectado via `get_now_local()` — sem teste de timezone DST |
| `_drain_process_output()` | 🔴 | Cap de `MAX_LOG_LINES=10_000` e `MAX_LOG_CHARS=5_000_000` — logs acima do cap continuam no WS mas não em memória |
| `_build_subprocess_env()` | 🟡 | Allowlist `_ALLOWED_ENV_KEYS` — segredo vaza se chave nova for adicionada sem revisão |
| `wakeup_listener_loop()` | 🟡 | Backoff exponencial `5s → 60s` com reset em sucesso — sem teste de reset |
| `log_flusher_loop()` | 🟡 | 1 retry com backoff `0.5s`; falha final = logs perdidos no WS mas preservados no banco |
| `broadcast_log()` / buffer | 🟡 | Thread-safe via `log_buffer_lock` — sem teste de concorrência com 2 threads |
| `update_stat()` | 🟢 | Thread-safe via `stats["lock"]` — sem teste de decremento abaixo de zero (`max(0, ...)`) |
| `scan_for_artifacts()` | 🟢 | Glob de `*.xlsx, *.html, *.pdf, *.csv` por `mtime >= task_start_ts` — sem teste de arquivo antigo ignorado |
| `_finalize_execution()` | 🔴 | Guard `status not in [TERMINATED, TIMEOUT]` — sem teste de execução já terminada não sendo sobrescrita |
| `run_task()` | 🔴 | `status != PENDING and != RUNNING → return silencioso` — sem teste de task reivindicada duas vezes |
| Env `LOG_FILENAME` | 🟢 | Detecta `pytest` em `sys.modules` → usa `Worker_test.jsonl` — sem teste deste guard |

### 1.4 Métricas de Qualidade

| Indicador | Valor Atual | Meta F1 | Meta Final |
|---|---|---|---|
| Cobertura Python (threshold CI) | **77%** | 82% | 90% |
| Cobertura Dashboard (unit) | **~0%** | 40% | 70% |
| `--strict-markers` enforced | ❌ | ✅ | ✅ |
| Fixture `mock_oracle_connection` | ❌ | ✅ | ✅ |
| Fixture `mock_subprocess_popen` | ❌ | ✅ | ✅ |
| Fixture `mock_requests` (worker) | ❌ | ✅ | ✅ |
| Fixture `shutdown_event` reset | ❌ | ✅ | ✅ |
| Testes de `_monitor_process` | ❌ | ✅ | ✅ |
| Testes de `_drain_process_output` caps | ❌ | ✅ | ✅ |
| Testes de `_build_subprocess_env` allowlist | ❌ | ✅ | ✅ |
| Health check E2E obrigatório | ❌ | ✅ | ✅ |
| Mutation testing | ❌ | ❌ | ✅ |
| Testes de componente React | ❌ | ❌ | ✅ |

---

## 2. Gaps Críticos Identificados

### GAP-01 — Threshold de Cobertura Insuficiente

O CI bloqueia com `--cov-fail-under=77`. Com o `conftest.py` marcando automaticamente todos os testes que usam `client`/`db_session` como `integracao`, os testes unitários puros são minoria — o que significa que **branches de erro em `worker.py` e nos serviços ficam sem cobertura real**.

### GAP-02 — `--strict-markers` ausente

`pytest_collection_modifyitems` no `conftest.py` já faz marcação automática, mas sem `--strict-markers` no `pytest.ini`, um teste com marcador tipograficamente errado (ex: `@pytest.mark.integração`) passa sem warning.

```ini
# CORRIGIR em pytest.ini:
addopts = -p no:cacheprovider --strict-markers
```

### GAP-03 — `conftest.py` sem fixtures de worker

O `conftest.py` cobre bem o FastAPI (9 patches no `client`), mas **não tem nenhuma fixture para o worker**. As 3 fixtures críticas ausentes:

```python
# 1. Mock de subprocess.Popen (para _start_process)
@pytest.fixture
def mock_popen() -> Generator[MagicMock, None, None]:
    with patch("worker.subprocess.Popen") as mock:
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = None  # processo ainda rodando
        proc.returncode = 0
        proc.stdout = iter(["linha 1\n", "linha 2\n"])
        mock.return_value = proc
        yield mock

# 2. Reset do shutdown_event global
@pytest.fixture(autouse=True)
def reset_worker_globals() -> Generator[None, None, None]:
    import worker
    worker.shutdown_event.clear()
    worker.wakeup_event.clear()
    worker.stats["tasks_completed"] = 0
    worker.stats["tasks_failed"] = 0
    worker.stats["active_tasks"] = 0
    worker.stats["active_processes"].clear()
    yield
    worker.shutdown_event.clear()
    worker.wakeup_event.clear()

# 3. Mock de requests (wakeup listener + log flusher)
@pytest.fixture
def mock_requests_worker() -> Generator[MagicMock, None, None]:
    with patch("worker.requests.get") as mock_get, \
         patch("worker.requests.post") as mock_post:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "idle"}
        yield {"get": mock_get, "post": mock_post}
```

### GAP-04 — `_monitor_process` não testado em cenário de timeout

A lógica de timeout em `_monitor_process` usa `get_now_local()` e `timedelta(minutes=max_runtime)`. Sem mock de tempo, é impossível testar timeout sem esperar os minutos reais. Além disso, **nenhum teste verifica o guard de DST** (horário de verão pode causar falso positivo de timeout com `timedelta` ingênuo).

### GAP-05 — Caps de log não testados

`_drain_process_output` tem dois caps: `MAX_LOG_LINES=10_000` e `MAX_LOG_CHARS=5_000_000`. A lógica é:
> acima do cap → continua transmitindo ao WS mas **não acumula em memória**

Sem testes para este comportamento, um bug de acumulação silenciosa (memory leak por execução) não seria detectado.

### GAP-06 — `_build_subprocess_env` allowlist sem auditoria

`_ALLOWED_ENV_KEYS` é um `set` hardcoded. Se uma variável com segredo (ex: `ORACLE_READONLY_PASSWORD`) for adicionada acidentalmente ao set, ela vaza para todos os subprocessos PowerShell. **Não há teste que valide que segredos conhecidos estão fora da allowlist.**

### GAP-07 — `client` fixture com 9 patches manuais — frágil

O `conftest.py` faz 9 patches explícitos de `SessionLocal`. Se um novo módulo usar `SessionLocal` diretamente (ex: um novo router), ele vai usar o banco real em testes de integração sem nenhum warning. **Não há teste que valide que todos os módulos estão redirecionados para o `test_engine`.**

### GAP-08 — Oracle sem mock padronizado

`lib/python/oracle_extract.py` usa `oracledb.connect` diretamente. Não há fixture `mock_oracle_connection` no `conftest.py`. Cada teste que precisar mockar Oracle vai reimplementar o mock de formas diferentes — inconsistência garantida.

### GAP-09 — `_finalize_execution` sem teste de guard de status

A função `_finalize_execution` tem o guard:
```python
if db_exec and db_exec.status not in [EXECUTION_STATUS_TERMINATED, EXECUTION_STATUS_TIMEOUT]:
```
Sem teste para esse branch, um bug que sobrescreva o status `TERMINATED` com `ERROR` não seria detectado — o histórico de execução mostraria causa de término errada.

### GAP-10 — `wakeup_event` e `shutdown_event` como globais

`worker.py` define `shutdown_event` e `wakeup_event` como variáveis globais de módulo. Sem o fixture `reset_worker_globals`, **o estado de um teste vaza para o próximo** — especialmente se um teste setar `shutdown_event` para testar graceful shutdown e não limpar depois.

### GAP-11 — Dashboard sem testes unitários React

Zero testes Vitest/Jest. Lógica crítica sem cobertura: `schedule_version=2`, autenticação `localStorage`, `action_code`/`action_label`, risk badges `CAT`/`DRIFT`/`DOCS`.

### GAP-12 — E2E sem health check obrigatório no CI

`test_e2e_dashboard.py` requer servidor ativo. Se o Orchestrator falhar no startup, os testes E2E passam como skipped silenciosamente.

### GAP-13 — Circuit Breaker Oracle sem teste

`oracle_retry.py` implementa `pybreaker + stamina`, mas nenhum teste valida a abertura do circuit breaker após N falhas, half-open e fechamento.

### GAP-14 — Notificações sem teste de idempotência granular

ADR-013 documenta estado parcial (email OK + WhatsApp falha → salvar parcial). Sem testes para retry com estado parcial.

---

## 3. Plano de Ação por Fases

### Fase 1 — Hardening Imediato (Semanas 1–2)

> **Meta:** Fechar os gaps de estado global e mock de infraestrutura.

#### F1-T1 — Adicionar fixtures de worker ao `conftest.py`

**Arquivo:** `Orchestrator/tests/conftest.py`

Adicionar as 3 fixtures abaixo ao final do arquivo:

```python
import worker as _worker_module  # noqa: E402


@pytest.fixture
def mock_popen() -> Generator[MagicMock, None, None]:
    """Mock padronizado de subprocess.Popen para testes do worker."""
    with patch("worker.subprocess.Popen") as mock:
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = None
        proc.returncode = 0
        proc.stdout = iter([])
        mock.return_value = proc
        yield mock


@pytest.fixture(autouse=False)
def reset_worker_globals() -> Generator[None, None, None]:
    """Reseta o estado global do worker entre testes para evitar vazamento."""
    _worker_module.shutdown_event.clear()
    _worker_module.wakeup_event.clear()
    _worker_module.log_buffer.clear()
    _worker_module.stats["tasks_completed"] = 0
    _worker_module.stats["tasks_failed"] = 0
    _worker_module.stats["active_tasks"] = 0
    _worker_module.stats["active_processes"].clear()
    yield
    _worker_module.shutdown_event.clear()
    _worker_module.wakeup_event.clear()


@pytest.fixture
def mock_requests_worker() -> Generator[dict, None, None]:
    """Mock padronizado de requests para o wakeup listener e log flusher."""
    with patch("worker.requests.get") as mock_get, \
         patch("worker.requests.post") as mock_post:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "idle"}
        mock_post.return_value.status_code = 200
        yield {"get": mock_get, "post": mock_post}


@pytest.fixture
def mock_oracle_connection() -> Generator[MagicMock, None, None]:
    """Mock padronizado para oracledb.connect. Retorna cursor vazio por padrão."""
    with patch("oracledb.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.description = []
        mock_cursor.fetchmany.return_value = []
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value.cursor.return_value = mock_cursor
        yield mock_conn
```

#### F1-T2 — `--strict-markers` no `pytest.ini`

```ini
[pytest]
addopts = -p no:cacheprovider --strict-markers
testpaths = tests
python_files = test_*.py
markers =
    unitario: testes unitários isolados (sem I/O externo)
    integracao: testes de integração com banco SQLite em memória
    e2e: testes Playwright fim-a-fim (requerem servidor ativo)
```

**Critério de sucesso:** `pytest --collect-only` sem warnings de marcador desconhecido.

#### F1-T3 — Criar `test_worker_core_unit.py`

**Arquivo a criar:** `Orchestrator/tests/test_worker_core_unit.py`

```python
# @pytest.mark.unitario — usa fixtures: reset_worker_globals, mock_popen, mock_requests_worker

# _force_kill
- test_force_kill_chama_taskkill_com_args_corretos
- test_force_kill_timeout_expired_loga_warning

# _build_subprocess_env allowlist
- test_subprocess_env_nao_contem_oracle_readonly_password
- test_subprocess_env_nao_contem_orchestrator_api_key
- test_subprocess_env_contem_apenas_allowed_keys
- test_subprocess_env_test_mode_propagado
- test_subprocess_env_exec_id_e_correlation_id_iguais

# _drain_process_output caps
- test_drain_cap_linhas_para_em_max_log_lines
- test_drain_cap_chars_para_em_max_log_chars
- test_drain_acima_do_cap_continua_broadcast_mas_nao_acumula

# _finalize_execution guard de status
- test_finalize_nao_sobrescreve_status_terminated
- test_finalize_nao_sobrescreve_status_timeout
- test_finalize_completa_status_pending_normalmente

# update_stat thread-safety
- test_update_stat_decremento_nao_vai_abaixo_de_zero
- test_update_stat_concorrente_nao_corrompe

# scan_for_artifacts
- test_scan_ignora_arquivo_anterior_ao_start_time
- test_scan_inclui_arquivo_gerado_durante_execucao
- test_scan_retorna_none_sem_artefatos

# LOG_FILENAME
- test_log_filename_usa_worker_test_em_pytest

# broadcast_log buffer
- test_broadcast_log_enfileira_por_exec_id
- test_broadcast_log_thread_safe_dois_threads_simultaneos
```

#### F1-T4 — Criar `test_worker_monitor_unit.py`

**Arquivo a criar:** `Orchestrator/tests/test_worker_monitor_unit.py`

```python
# @pytest.mark.unitario — usa: reset_worker_globals, mock_popen, db_session
# Mockar get_now_local() para testar timeout sem esperar tempo real

- test_monitor_detecta_timeout_via_mock_de_tempo
- test_monitor_seta_status_timeout_no_banco
- test_monitor_chama_force_kill_no_timeout
- test_monitor_detecta_terminacao_pelo_usuario
- test_monitor_chama_finalize_terminated_task
- test_monitor_retorna_false_em_shutdown_event
- test_monitor_db_check_interval_respeita_5s
- test_monitor_retorna_true_quando_processo_finaliza_normalmente
```

#### F1-T5 — Criar `test_worker_wakeup_unit.py`

**Arquivo a criar:** `Orchestrator/tests/test_worker_wakeup_unit.py`

```python
# @pytest.mark.unitario — usa: reset_worker_globals, mock_requests_worker

- test_wakeup_seta_event_ao_receber_status_wakeup
- test_wakeup_nao_seta_event_em_status_idle
- test_wakeup_backoff_aumenta_em_falha_de_rede
- test_wakeup_backoff_reseta_apos_sucesso
- test_wakeup_backoff_nao_excede_max_backoff
- test_wakeup_para_ao_shutdown_event_set

- test_log_flusher_envia_lote_em_batch
- test_log_flusher_retry_unico_em_falha_de_rede
- test_log_flusher_loga_warning_apos_2_falhas
- test_log_flusher_nao_envia_buffer_vazio
```

#### F1-T6 — Criar `test_oracle_extract_unit.py`

**Arquivo a criar:** `Orchestrator/tests/test_oracle_extract_unit.py`

```python
# @pytest.mark.unitario — usa fixture mock_oracle_connection

- test_fetch_all_retorna_colunas_e_linhas
- test_fetch_all_lotes_multiplos_concatenados
- test_fetch_all_cursor_sem_description_retorna_vazio
- test_serialize_rows_datetime_para_isoformat
- test_serialize_rows_strip_espacos
- test_serialize_rows_sort_key_aplicado
- test_compute_hash_deterministico
- test_compute_hash_sort_keys_garante_ordem
- test_read_last_hash_arquivo_ausente_retorna_string_vazia
- test_read_last_hash_json_invalido_retorna_string_vazia
- test_write_state_tmp_cria_arquivo_com_sufixo_tmp
- test_resolve_oracle_credentials_ausentes_retorna_none
- test_resolve_oracle_credentials_force_dsn_ignora_env
```

#### F1-T7 — Health check obrigatório antes dos testes E2E

**Arquivo:** `.github/workflows/governanca.yml`

```yaml
- name: Aguardar Orchestrator subir
  run: |
    for i in $(seq 1 30); do
      curl -sf http://127.0.0.1:8000/health && break
      echo "Tentativa $i/30 — aguardando..."
      sleep 2
    done
    curl -sf http://127.0.0.1:8000/health || (echo "Orchestrator não subiu" && exit 1)
```

#### F1-T8 — Auditoria da allowlist `_ALLOWED_ENV_KEYS`

**Arquivo a criar:** `Orchestrator/tests/test_worker_security.py`

```python
# @pytest.mark.unitario

# Lista de variáveis que NUNCA devem estar na allowlist
FORBIDDEN_KEYS = {
    "ORACLE_READONLY_PASSWORD",
    "ORACLE_READONLY_USER",
    "ORCHESTRATOR_API_KEY",
    "WHATSAPP_TOKEN",
    "SMTP_PASSWORD",
    "SECRET_KEY",
}

def test_allowed_env_keys_nao_contem_segredos() -> None:
    from worker import _ALLOWED_ENV_KEYS
    vazamentos = FORBIDDEN_KEYS & _ALLOWED_ENV_KEYS
    assert not vazamentos, f"Segredos na allowlist: {vazamentos}"
```

---

### Fase 2 — Ampliação de Cobertura (Semanas 3–6)

> **Meta:** Elevar threshold para 82%, cobrir domínios críticos, adicionar testes React.

#### F2-T1 — Elevar threshold para 82%

```ini
# pytest.ini — escalonamento controlado:
# 77 → 79 → 82 (medir delta após cada push)
addopts = -p no:cacheprovider --strict-markers --cov-fail-under=82
```

#### F2-T2 — Testes unitários React com Vitest

```bash
npm install --save-dev vitest @testing-library/react @testing-library/user-event jsdom
```

**Arquivos a criar em** `Dashboard/src/__tests__/`:

```
schedule.parser.test.ts     — schedule_version=2 (manual, daily, weekly, monthly, interval, once)
auth.localstorage.test.ts   — prompt, persistência, limpeza no 403
diagnostics.badges.test.ts  — CAT, DRIFT, DOCS risk badges
action.codes.test.ts        — action_code → action_label → operator_actions
beneficiamento.kpi.test.ts  — formatação de KPI e períodos
```

```json
// Dashboard/package.json — adicionar:
"scripts": {
  "test": "vitest run",
  "test:watch": "vitest",
  "test:coverage": "vitest run --coverage"
}
```

#### F2-T3 — Testes do `run_task` e `main_loop`

**Arquivo a criar:** `Orchestrator/tests/test_worker_integration.py`

```python
# @pytest.mark.integracao — usa: reset_worker_globals, mock_popen, db_session, mock_requests_worker

- test_run_task_status_nao_pending_retorna_silenciosamente
- test_run_task_reivindicada_duas_vezes_nao_duplica
- test_run_task_execucao_nao_encontrada_no_banco
- test_run_task_exception_chama_apply_internal_worker_error
- test_run_task_decrementa_active_tasks_no_finally
- test_main_loop_para_ao_shutdown_event
- test_main_loop_despacha_tarefa_para_thread_pool
- test_main_loop_backoff_quando_sem_tarefas
- test_main_loop_acorda_via_wakeup_event
```

#### F2-T4 — Testes de idempotência de notificações

**Arquivo:** `Orchestrator/tests/test_notifications.py` (ampliar)

```python
- test_email_ok_whatsapp_falha_salva_estado_parcial
- test_retry_com_estado_parcial_reenvia_apenas_whatsapp
- test_falha_ambos_canais_reseta_estado_para_retry_completo
- test_idempotencia_nao_reenvia_canal_ja_confirmado
```

#### F2-T5 — Testes de Circuit Breaker Oracle

**Arquivo a criar:** `Orchestrator/tests/test_oracle_circuit_breaker.py`

```python
- test_circuit_breaker_abre_apos_n_falhas_consecutivas
- test_circuit_breaker_half_open_permite_tentativa
- test_circuit_breaker_fecha_apos_sucesso_em_half_open
- test_stamina_retry_espera_intervalo_correto
```

#### F2-T6 — Testes do `portfolio_catalog.py`

**Arquivo a criar:** `Orchestrator/tests/test_portfolio_catalog_unit.py`

```python
- test_calcular_drift_detecta_manifesto_divergente
- test_calcular_drift_retorna_healthy_manifesto_alinhado
- test_docs_obrigatorias_ausentes_gera_finding
- test_scoring_criticidade_high_peso_maior
- test_portfolio_health_summary_status_incident
- test_sla_violation_detectada_corretamente
- test_ownership_orfao_detectado
```

#### F2-T7 — Testes do `scheduler_runtime.py`

**Arquivo a criar:** `Orchestrator/tests/test_scheduler_runtime_unit.py`

```python
- test_cron_expression_valida_aceita
- test_cron_expression_invalida_rejeitada
- test_schedule_version2_todos_os_tipos
- test_schedule_preview_retorna_proximas_execucoes
- test_timezone_america_sao_paulo_aplicada
- test_trigger_worker_wakeup_usa_call_soon_threadsafe
- test_wakeup_sem_event_loop_registrado_nao_lanca_excecao
```

#### F2-T8 — Teste de auditoria do `client` fixture

**Arquivo a criar:** `Orchestrator/tests/test_conftest_coverage.py`

```python
# @pytest.mark.integracao
# Garante que todos os módulos com SessionLocal estão redirecionados para test_engine

def test_todos_os_modulos_usam_test_engine(client: TestClient) -> None:
    import app.database as db
    import app.services.scheduler_runtime as sched
    import app.routers.websocket as ws
    assert db.SessionLocal is testing_session_local
    assert getattr(sched, "SessionLocal") is testing_session_local
    assert getattr(ws, "SessionLocal") is testing_session_local
```

---

### Fase 3 — Qualidade Avançada (Meses 2–3)

> **Meta:** Cobertura 90%, mutation testing, performance, regressão visual.

#### F3-T1 — Mutation Testing com `mutmut`

```bash
pip install mutmut
```

```toml
# pyproject.toml
[tool.mutmut]
paths_to_mutate = [
    "Produção Beneficimento/src/beneficiamento/core/",
    "lib/python/oracle_extract.py",
    "Orchestrator/app/services/scoring.py",
    "Orchestrator/app/services/operational_baseline.py",
]
tests_dir = "Orchestrator/tests/"
```

**Meta:** Mutation score > 80% nos módulos de lógica pura.

#### F3-T2 — Property-Based Testing com `hypothesis`

```bash
pip install hypothesis
```

**Arquivo a criar:** `Orchestrator/tests/test_beneficiamento_property.py`

```python
@given(st.floats(min_value=0, max_value=1e9))
def test_coercao_metrica_sempre_float_nao_negativo(valor: float) -> None: ...

@given(st.text(min_size=1, max_size=50))
def test_nome_turno_nunca_vazio_apos_normalizacao(nome: str) -> None: ...

@given(st.datetimes())
def test_calculo_turno_deterministico_para_qualquer_datetime(dt: datetime) -> None: ...
```

#### F3-T3 — Performance Testing com `pytest-benchmark`

```bash
pip install pytest-benchmark
```

```python
# test_performance_baseline.py
- bench_system_diagnostics_build_payload      (< 50ms)
- bench_portfolio_catalog_calculate_health    (< 100ms)
- bench_scheduler_runtime_parse_cron          (< 5ms)
- bench_oracle_extract_serialize_rows_1000    (< 20ms)
```

```yaml
# CI — job não-bloqueante:
- name: Benchmark
  run: pytest -m benchmark --benchmark-json=benchmark-results.json || true
- uses: actions/upload-artifact@v4
  with:
    name: benchmark-results
    path: benchmark-results.json
```

#### F3-T4 — Regressão Visual com Playwright Screenshots

```python
# Adicionar em test_e2e_dashboard.py:
- test_screenshot_dashboard_overview_estado_healthy
- test_screenshot_diagnostics_com_findings
- test_screenshot_automacoes_com_risk_badges
- test_screenshot_beneficiamento_kpi_carregado
```

Baseline em `docs/playwright-screenshots/baseline/`.

#### F3-T5 — Elevar threshold para 90%

```
Progresso: 77% → F1: 79% → F2: 85% → F3: 90%
```

---

## 4. Modernização de Ferramentas

| Área | Atual | Recomendado | Justificativa |
|---|---|---|---|
| Testes unitários React | ❌ | **Vitest** + Testing Library | Nativo ao Vite, zero-config |
| Componentes React isolados | ❌ | **`@playwright/experimental-ct-react`** | Reutiliza Playwright já no stack |
| Mutation testing Python | ❌ | **`mutmut`** | Leve, integra ao pytest |
| Property-based testing | ❌ | **`hypothesis`** | Ideal para lógica pura em `beneficiamento/core/` |
| Performance regression | ❌ | **`pytest-benchmark`** | Detecta regressões de latência no CI |
| Cobertura diferencial de PR | ❌ | **`diff-cover`** | Exige cobertura só nas linhas modificadas |
| Mock de tempo | ❌ | **`freezegun`** ou **`time-machine`** | Indispensável para testar timeout do `_monitor_process` sem esperar |
| Load testing API | ❌ | **`locust`** | `/api/system/diagnostics` e `/api/portfolio/health` sob carga |

> **Adição nova (descoberta pelo `worker.py`):** `freezegun` ou `time-machine` são **essenciais** para testar o timeout do `_monitor_process` que usa `get_now_local()` — sem eles os testes de timeout seriam não-deterministas ou dependeriam de `time.sleep()`.

```bash
pip install time-machine  # mais rápido que freezegun, sem monkey-patch global
```

```python
import time_machine

@time_machine.travel(datetime(2026, 7, 3, 10, 0, 0), tick=False)
def test_monitor_detecta_timeout_via_mock_de_tempo() -> None:
    # get_now_local() retornará 10:00:00; avanço de 31 min dispara timeout de 30 min
    ...
```

---

## 5. Melhorias no Processo de QA

### 5.1 Separação de Jobs no CI

```
Job: lint-python (ruff, black, isort, bandit)   ← independente
Job: lint-frontend (ESLint + tsc)                ← independente
Job: testes-unitarios (-m unitario)             ← depende de lint-python
Job: testes-integracao (-m integracao)          ← depende de testes-unitarios
Job: testes-e2e (-m e2e)                        ← depende de testes-integracao + health check
Job: governanca (ValidarAutomacoes.ps1)         ← depende de lint-python
Job: benchmark (não bloqueante)                 ← depende de testes-unitarios
```

### 5.2 `diff-cover` para PRs

```yaml
- name: Coverage diferencial do PR
  run: |
    pytest --cov=Orchestrator/app --cov-report=xml
    diff-cover coverage.xml --compare-branch=origin/main --fail-under=85
```

### 5.3 Convenção de Commits para Testes

```
tests(worker): adiciona cenários de timeout e graceful shutdown
tests(oracle): mock unitário de oracle_extract.py via conftest
tests(conftest): fixtures mock_popen, reset_worker_globals, mock_oracle_connection
tests(dashboard): Vitest para schedule parser e auth
```

---

## 6. Checklist de Implementação

### Fase 1 — Semanas 1–2 (implementada em 03/07/2026)

- [x] **F1-T1** — Adicionado `mock_popen`, `reset_worker_globals`, `mock_requests_worker`, `mock_oracle_connection` ao `conftest.py`
- [x] **F1-T2** — `--strict-markers` em `pytest.ini`
- [x] **F1-T3** — Criado `test_worker_core_unit.py` (20 cenários; 2 a menos que a estimativa original — `update_stat` não faz clamp em zero no código real, esse comportamento pertence ao `finally` de `run_task`, fora do escopo unitário desta função)
- [x] **F1-T4** — Criado `test_worker_monitor_unit.py` (7 cenários) + instalado `time-machine` (`requirements-test.in`/`.txt`)
- [x] **F1-T5** — Criado `test_worker_wakeup_unit.py` (10 cenários)
- [x] **F1-T6** — Criado `test_oracle_extract_unit.py` (14 cenários)
- [x] ~~**F1-T7**~~ — **Não implementado.** A premissa do GAP-12 estava desatualizada: a fixture `uvicorn_server` em `test_e2e_dashboard.py` já sobe seu próprio subprocesso e levanta `RuntimeError` (com stdout/stderr) se o servidor não subir em 5s — não há skip silencioso. O job `testes-e2e` do CI também não depende de um servidor pré-existente na porta 8000; adicionar o curl proposto quebraria o job sem necessidade.
- [x] **F1-T8** — Criado `test_worker_security.py` (1 cenário de allowlist)
- [x] Verificado que todos os novos testes passam em `--cov-fail-under=77` (suite completa: 275 passed, cobertura 80.34%)
- [x] Rodado `ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` ✅ (mypy --strict, pylint 10/10, black, isort, arquitetura, encoding — todos limpos)

### Fase 2 — Semanas 3–6 (backend implementado em 03/07/2026)

- [x] **F2-T1** — Threshold elevado para 82% (`--cov-fail-under=82` em `.github/workflows/governanca.yml`; cobertura medida: 82.66%)
- [ ] **F2-T2** — Setup Vitest + 5 arquivos de teste React — **adiado deliberadamente** para uma próxima onda (escopo de frontend, decisão do usuário em 03/07/2026)
- [x] **F2-T3** — Criado `test_worker_integration.py` (8 cenários de `run_task`/`main_loop`; achado documentado: `run_task` não bloqueia reentrada para exec_id já RUNNING — mitigado na prática pelo UPDATE atômico de `claim_next_task`, não corrigido)
- [x] **F2-T4** — Ampliado `test_notifications.py` (13 cenários novos). **Escopo corrigido**: a idempotência do ADR-013 (e-mail OK + WhatsApp falha → estado parcial) vive no PowerShell de `Receitas Bloqueadas`, não em `app/notifications.py` (motor de alerta interno do Orchestrator) — os testes novos cobrem os gaps reais desse módulo (escalada de cooldown, eviction LRU, dispatch por canal, paths de erro)
- [x] **F2-T5** — Criado `test_oracle_circuit_breaker.py` (5 cenários; contagem de falhas até abrir o circuito ajustada após validar o comportamento real do `pybreaker`)
- [x] **F2-T6** — Criado `test_portfolio_catalog_unit.py` (31 cenários das funções puras)
- [x] **F2-T7** — Criado `test_scheduler_runtime_unit.py` (24 cenários; inclui `app/runtime.py.trigger_worker_wakeup`, que o plano atribuía erroneamente a `scheduler_runtime.py`). **Bug real corrigido**: `list_scheduled_jobs` quebrava com `TypeError` ao ordenar jobs quando havia mistura de `next_run_time` real (convertido a string BR) e `None` — corrigido com uma chave de ordenação `(has_run_time, valor)` que nunca compara tipos incompatíveis
- [x] **F2-T8** — Criado `test_conftest_coverage.py` (auditoria dinâmica via varredura de `app/**/*.py`, não lista estática)
- [ ] Adicionar `diff-cover` ao job de PR — não implementado nesta onda
- [x] Verificado cobertura acima de 82% ✅ (358 testes passando, 82.66%)

### Fase 3 — Meses 2–3

- [ ] **F3-T1** — Setup `mutmut` + mutation score > 80% nos módulos de lógica pura
- [ ] **F3-T2** — Criar `test_beneficiamento_property.py` com `hypothesis`
- [ ] **F3-T3** — Setup `pytest-benchmark` + job não-bloqueante no CI
- [ ] **F3-T4** — Screenshots de regressão visual no Playwright
- [ ] **F3-T5** — Elevar threshold para 90%
- [ ] Separar jobs do CI em paralelo
- [ ] Verificar cobertura acima de 90% ✅

---

## 7. Referências Internas

- [`CLAUDE.md`](../CLAUDE.md) — Contratos de governança, pytest, mypy, pylint
- [`CONTEXT.md`](../CONTEXT.md) — ADRs e histórico arquitetural
- [`docs/playwright-e2e-standard.md`](playwright-e2e-standard.md) — Padrão E2E
- [`docs/architecture-standard.md`](architecture-standard.md) — Camadas arquiteturais
- [`Tools/ValidarAutomacoes.ps1`](../Tools/ValidarAutomacoes.ps1) — Quality gate
- [`Orchestrator/tests/conftest.py`](../Orchestrator/tests/conftest.py) — Fixtures base
- [`Orchestrator/worker.py`](../Orchestrator/worker.py) — Motor de execução (26 KB)

---

*v2 — Atualizado após leitura integral de `worker.py` (26 KB) e `conftest.py`. Fechar cada fase e marcar os checkboxes acima.*
