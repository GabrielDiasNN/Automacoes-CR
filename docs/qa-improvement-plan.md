# Plano de Melhoria de QA — Automações Hub v9.5.0

> **Gerado em:** 02/07/2026  
> **Versão analisada:** v9.5.0 (Operational Baseline)  
> **Escopo:** Leitura completa do repositório — Orchestrator, Dashboard, domínios, lib compartilhada, CI, testes

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
| `test_portfolio.py` | 8 KB | Portfólio |
| `test_diagnostics.py` | 8 KB | Diagnósticos |
| `test_montagem_terceirizados.py` | 12 KB | Montagem Terceirizados |
| `test_receitas_bloqueadas.py` | 12 KB | Receitas Bloqueadas |
| `test_worker_queue.py` | 7 KB | Fila do Worker |
| `test_beneficiamento_unit.py` | 9 KB | Beneficiamento (unitário) |
| `test_queue_rules.py` | 6 KB | Regras de Fila |
| `test_sanitization.py` | 5 KB | Sanitização |
| `test_worker_loop.py` | 4 KB | Loop do Worker |
| `test_api_contracts.py` | 3 KB | Contratos de API |
| `test_audit_utils.py` | 1 KB | Auditoria |
| `test_database_schema.py` | 1 KB | Schema do Banco |
| `test_notifications.py` | 4 KB | Notificações |
| `test_obs_paradas_fase.py` | 2 KB | OBs Paradas |
| `test_receitas_emitidas.py` | 1 KB | Receitas Emitidas |
| `test_recovery.py` | 1 KB | Recovery |
| `test_timezone_contract.py` | 3 KB | Fuso Horário |
| `test_validation.py` | 3 KB | Validação |
| `test_scaffold_governance.py` | 2 KB | Scaffold Governança |
| `test_log_broadcast.py` | 1 KB | Log Broadcast |
| `test_websocket_broadcast_auth.py` | 1 KB | WebSocket Auth |
| `test_purge_retention.py` | 2 KB | Purge/Retenção |
| `test_automations_ide.py` | 3 KB | IDE de Automações |

**Total estimado:** 31 arquivos de teste | ~200 KB de código de teste

### 1.2 Métricas Atuais de Qualidade

| Indicador | Valor Atual | Meta Fase 1 | Meta Final |
|---|---|---|---|
| Cobertura Python (threshold CI) | **77%** mínimo | 82% | 90% |
| Cobertura Dashboard (unit) | **~0%** | 40% | 70% |
| Marcadores enforced (`--strict-markers`) | ❌ Ausente | ✅ | ✅ |
| Mock de Oracle nos testes unitários | ❌ Ausente | ✅ | ✅ |
| Mutation testing | ❌ Ausente | ❌ | ✅ |
| Property-based testing | ❌ Ausente | ❌ | ✅ |
| Health check E2E obrigatório | ❌ Ausente | ✅ | ✅ |
| Performance regression no CI | ❌ Ausente | ❌ | ✅ |
| Testes de componente React | ❌ Ausente | ❌ | ✅ |
| Circuit breaker testado | ❌ Ausente | ✅ | ✅ |

### 1.3 Módulos de Alto Risco sem Cobertura Adequada

| Módulo | Tamanho | Risco | Justificativa |
|---|---|---|---|
| `Orchestrator/worker.py` | 26 KB | 🔴 Crítico | Spawn de processos, timeout, taskkill, graceful shutdown, AbandonedMutex |
| `services/portfolio_catalog.py` | 37 KB | 🔴 Crítico | Maior serviço do sistema; drift, docs, SLA, scoring — sem testes dedicados visíveis |
| `services/execution_runtime.py` | 15 KB | 🔴 Crítico | Requeue, validação de concorrência por queue_group |
| `services/scheduler_runtime.py` | 16 KB | 🔴 Crítico | APScheduler runtime, wake-up thread-safe, cron parsing |
| `services/system_diagnostics.py` | 18 KB | 🟡 Alto | Lógica de findings, severity, action_code — usada pelo Dashboard em tempo real |
| `lib/python/oracle_extract.py` | Compartilhado | 🔴 Crítico | Usado pelos 4 domínios de extração; falha = paralisia total |
| `app/notifications.py` | 7 KB | 🟡 Alto | Canal WhatsApp + Email; falha silenciosa impacta SLA |
| `app/middleware.py` | 7 KB | 🟡 Alto | Auth middleware; sem teste de injeção de header / API Key inválida |
| `services/operational_baseline.py` | 10 KB | 🟡 Alto | Thresholds compartilhados entre diagnostics, history e baseline — regressão silenciosa |
| `Produção Beneficimento/src/` | Domínio | 🟡 Alto | Lógica pura em `core/` (coerção, métricas, turnos) parcialmente testada |

---

## 2. Gaps Críticos Identificados

### GAP-01 — Threshold de Cobertura Insuficiente

O CI bloqueia com `--cov-fail-under=77`. Isso significa que **23% do código não tem cobertura garantida**. Com 31 arquivos de teste e ~200 KB de testes, a distribuição não é uniforme — módulos grandes como `portfolio_catalog.py` (37 KB) e `worker.py` (26 KB) provavelmente puxam a média para cima enquanto os caminhos críticos de falha ficam sem cobertura.

**Impacto:** Um bug em `worker.py` pode paralisar todas as automações sem ser detectado pelos testes.

### GAP-02 — Marcadores sem Enforcement

`pytest.ini` define os marcadores `unitario`, `integracao` e `e2e`, mas **não usa `--strict-markers`**. Testes sem marcador passam silenciosamente:

```ini
# ATUAL — incompleto
[pytest]
addopts = -p no:cacheprovider

# CORRETO
[pytest]
addopts = -p no:cacheprovider --strict-markers
```

Sem enforcement, a triagem de velocidade no CI é quebrada: testes E2E lentos podem ser executados no job de unitários sem aviso.

### GAP-03 — Oracle sem Mock Unitário

`lib/python/oracle_extract.py` é o **único ponto de acesso Oracle** dos 4 domínios (Receitas Emitidas, Receitas Bloqueadas, Montagem Terceirizados, OBs Paradas Fase). Não há arquivo `test_oracle_extract_unit.py` com mock de `oracledb.connect`. Um bug neste módulo quebra todos os 4 domínios simultaneamente.

### GAP-04 — Worker sem Testes de Falha Real

`test_worker_loop.py` (4 KB) e `test_worker_queue.py` (7 KB) cobrem caminhos felizes. Faltam:
- Processo PowerShell que trava além de `max_runtime_minutes`
- `AbandonedMutexException` durante concorrência de `queue_group`
- Worker kill com fila não vazia (graceful shutdown parcial)
- Processo filho que ignora SIGTERM (taskkill /T obrigatório)
- Exit codes de canal: `WHATSAPP_SESSION_EXPIRED`, `CHANNEL_DELIVERY_FAILED`

### GAP-05 — Dashboard sem Testes Unitários de Componente

O React/TypeScript usa apenas: lint (ESLint) + build (tsc + vite) + Playwright E2E. **Zero testes Vitest/Jest**. Lógica crítica sem cobertura:
- Parsing de `schedule_version=2` e tipos de agenda
- Autenticação via `localStorage` (prompt, persistência, limpeza no 403)
- `action_code` / `action_label` / `operator_actions` do diagnóstico
- Exibição de risk badges: `CAT`, `DRIFT`, `DOCS`

### GAP-06 — E2E Frágil por Ausência de Health Check

`test_e2e_dashboard.py` requer servidor ativo em `http://127.0.0.1:8000/dashboard/`. No CI (`governanca.yml`), se o Orchestrator falhar no startup, os testes E2E são silenciosamente ignorados em vez de falhar explicitamente. Sem `wait-for` ou health check obrigatório, a validação E2E é falível.

### GAP-07 — Sem Testes de Mutation

Nenhuma evidência de `mutmut` ou `cosmic-ray`. Com 77% de cobertura, é possível ter `assert True` passando em módulos críticos. Módulos de lógica pura como `beneficiamento/core/` (coerção, métricas, turnos) são candidatos ideais para mutation testing — sem I/O, rápidos, alto impacto.

### GAP-08 — `middleware.py` sem Testes de Segurança

O middleware de autenticação (7 KB) não tem testes para:
- API Key ausente → 401
- API Key inválida → 403
- API Key válida em rota pública → pass-through
- Injeção de header `X-API-Key` com caracteres especiais
- Tentativa de bypass via rota estática do Dashboard

### GAP-09 — Circuit Breaker Oracle sem Teste

`lib/python/oracle_retry.py` implementa `pybreaker + stamina` (`make_oracle_retry()`), mas não há teste que valide a abertura do circuit breaker após N falhas consecutivas e o comportamento de half-open.

### GAP-10 — `notifications.py` sem Teste de Canal Parcial

O ADR-013 documenta idempotência granular (e-mail enviado, WhatsApp falha → salvar estado parcial), mas `test_notifications.py` (4 KB) provavelmente não cobre:
- Email OK + WhatsApp falha → estado parcial salvo
- Retry de automação com estado parcial → só WhatsApp é reenviado
- Falha em ambos os canais → estado zerado para retry completo

---

## 3. Plano de Ação por Fases

### Fase 1 — Hardening Imediato (Semanas 1–2)

> **Meta:** Fechar os gaps de maior risco operacional. Todos entram no pre-commit hook.

#### F1-T1 — Habilitar `--strict-markers` no pytest

**Arquivo:** `Orchestrator/pytest.ini`

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

#### F1-T2 — Mock unitário de `oracle_extract.py`

**Arquivo a criar:** `Orchestrator/tests/test_oracle_extract_unit.py`

Cenários obrigatórios:

```python
# @pytest.mark.unitario
# Usando unittest.mock.patch("oracledb.connect")

- test_fetch_all_retorna_linhas_esperadas
- test_fetch_all_lotes_multiplos (fetch_size forçado pequeno)
- test_serialize_rows_datetime_para_isoformat
- test_serialize_rows_strip_espacos
- test_compute_hash_deterministico
- test_read_last_hash_arquivo_ausente_retorna_none
- test_write_state_tmp_cria_arquivo_temp
- test_resolve_oracle_credentials_le_dotenv
- test_resolve_oracle_credentials_force_dsn_ignora_dotenv
- test_init_thick_mode_ja_inicializado_nao_chama_novamente
```

#### F1-T3 — Testes de falha do Worker

**Arquivo a criar:** `Orchestrator/tests/test_worker_failure_scenarios.py`

Cenários obrigatórios:

```python
# @pytest.mark.integracao

- test_worker_mata_processo_apos_max_runtime_minutes
- test_worker_graceful_shutdown_com_fila_nao_vazia
- test_worker_requeue_bloqueado_por_queue_group_ativo
- test_worker_classifica_exit_code_whatsapp_session_expired
- test_worker_classifica_exit_code_channel_delivery_failed
- test_worker_abandoned_mutex_nao_trava_fila
- test_worker_taskkill_arvore_processo_filho
```

#### F1-T4 — Health check obrigatório antes dos testes E2E

**Arquivo:** `.github/workflows/governanca.yml` — job `testes-e2e`

```yaml
# Adicionar step antes de `pytest -m e2e`
- name: Aguardar Orchestrator subir
  run: |
    for i in $(seq 1 30); do
      curl -sf http://127.0.0.1:8000/health && break
      echo "Tentativa $i/30 — aguardando..."
      sleep 2
    done
    curl -sf http://127.0.0.1:8000/health || (echo "Orchestrator não subiu" && exit 1)
```

#### F1-T5 — Testes de segurança do middleware

**Arquivo a criar:** `Orchestrator/tests/test_middleware_auth.py`

```python
# @pytest.mark.integracao

- test_rota_protegida_sem_api_key_retorna_401
- test_rota_protegida_api_key_invalida_retorna_403
- test_rota_protegida_api_key_valida_retorna_200
- test_rota_publica_dashboard_sem_auth_retorna_200
- test_api_key_com_caracteres_especiais_rejeitada
- test_bypass_via_rota_estatica_bloqueado
```

---

### Fase 2 — Ampliação de Cobertura (Semanas 3–6)

> **Meta:** Elevar threshold para 82%, cobrir domínios críticos e adicionar testes React.

#### F2-T1 — Elevar threshold de cobertura

**Arquivo:** `Orchestrator/pytest.ini` e `.github/workflows/governanca.yml`

```ini
# pytest.ini
addopts = -p no:cacheprovider --strict-markers --cov-fail-under=82
```

Subir em etapas: `77 → 79 → 82`. Medir o delta após cada push.

#### F2-T2 — Testes unitários React com Vitest

**Setup:** Adicionar `vitest` + `@testing-library/react` + `@testing-library/user-event` ao `Dashboard/package.json`

```bash
npm install --save-dev vitest @testing-library/react @testing-library/user-event jsdom
```

**Arquivos a criar em** `Dashboard/src/__tests__/`:

```
schedule.parser.test.ts      — parsing schedule_version=2 (todos os tipos)
auth.localstorage.test.ts    — prompt, persistência, limpeza no 403
diagnostics.badges.test.ts  — CAT, DRIFT, DOCS risk badges
action.codes.test.ts         — action_code → action_label → operator_actions
beneficiamento.kpi.test.ts  — formatação de KPI e períodos
```

Adicionar ao `Dashboard/package.json`:

```json
"scripts": {
  "test": "vitest run",
  "test:watch": "vitest",
  "test:coverage": "vitest run --coverage"
}
```

#### F2-T3 — Testes de notificação com idempotência granular

**Arquivo:** `Orchestrator/tests/test_notifications.py` (ampliar existente)

Cenários adicionais obrigatórios:

```python
# @pytest.mark.unitario

- test_email_ok_whatsapp_falha_salva_estado_parcial
- test_retry_com_estado_parcial_reenvia_apenas_whatsapp
- test_falha_ambos_canais_reseta_estado_para_retry_completo
- test_whatsapp_ok_email_falha_salva_estado_parcial_invertido
- test_idempotencia_nao_reenvia_canal_ja_confirmado
```

#### F2-T4 — Testes de Circuit Breaker Oracle

**Arquivo a criar:** `Orchestrator/tests/test_oracle_circuit_breaker.py`

```python
# @pytest.mark.unitario

- test_circuit_breaker_abre_apos_n_falhas_consecutivas
- test_circuit_breaker_half_open_permite_tentativa
- test_circuit_breaker_fecha_apos_sucesso_em_half_open
- test_stamina_retry_espera_intervalo_correto
- test_circuit_breaker_error_propaga_para_chamador
```

#### F2-T5 — Testes do `portfolio_catalog.py`

`portfolio_catalog.py` (37 KB) é o maior serviço do sistema e não tem arquivo de teste dedicado.

**Arquivo a criar:** `Orchestrator/tests/test_portfolio_catalog_unit.py`

```python
# @pytest.mark.integracao

- test_calcular_drift_detecta_manifesto_divergente
- test_calcular_drift_retorna_healthy_manifesto_alinhado
- test_docs_obrigatorias_ausentes_gera_finding
- test_scoring_criticidade_high_peso_maior
- test_portfolio_health_summary_status_incident
- test_portfolio_health_summary_status_healthy
- test_sla_violation_detectada_corretamente
- test_ownership_orfao_detectado
```

#### F2-T6 — Testes do `scheduler_runtime.py`

**Arquivo a criar:** `Orchestrator/tests/test_scheduler_runtime_unit.py`

```python
# @pytest.mark.unitario (mock de APScheduler)

- test_cron_expression_valida_aceita
- test_cron_expression_invalida_rejeitada
- test_schedule_version2_todos_os_tipos (manual, daily, weekly, monthly, interval, once)
- test_schedule_preview_retorna_proximas_execucoes
- test_timezone_america_sao_paulo_aplicada
- test_trigger_worker_wakeup_usa_call_soon_threadsafe
- test_wakeup_sem_event_loop_registrado_nao_lanca_excecao
```

---

### Fase 3 — Qualidade Avançada (Meses 2–3)

> **Meta:** Cobertura 90%, mutation testing, performance e regressão visual.

#### F3-T1 — Mutation Testing com `mutmut`

**Instalação:**

```bash
pip install mutmut
```

**Configuração em** `pyproject.toml`:

```toml
[tool.mutmut]
paths_to_mutate = [
    "Produção Beneficimento/src/beneficiamento/core/",
    "lib/python/oracle_extract.py",
    "Orchestrator/app/services/scoring.py",
    "Orchestrator/app/services/operational_baseline.py",
]
tests_dir = "Orchestrator/tests/"
```

**Executar:**

```bash
mutmut run
mutmut results
mutmut show <id>   # ver mutante sobrevivente
```

**Meta:** Mutation score > 80% nos módulos de lógica pura.

#### F3-T2 — Property-Based Testing com `hypothesis`

**Instalação:**

```bash
pip install hypothesis
```

**Arquivo a criar:** `Orchestrator/tests/test_beneficiamento_property.py`

```python
from hypothesis import given, strategies as st

# Exemplos de propriedades a testar:

@given(st.floats(min_value=0, max_value=1e9))
def test_coercao_metrica_sempre_retorna_float_nao_negativo(valor: float) -> None:
    ...

@given(st.text(min_size=1, max_size=50))
def test_nome_turno_nunca_vazio_apos_normalizacao(nome: str) -> None:
    ...

@given(st.datetimes())
def test_calculo_turno_deterministico_para_qualquer_datetime(dt: datetime) -> None:
    ...
```

#### F3-T3 — Performance Testing com `pytest-benchmark`

**Instalação:**

```bash
pip install pytest-benchmark
```

**Arquivo a criar:** `Orchestrator/tests/test_performance_baseline.py`

```python
# @pytest.mark.unitario

- bench_system_diagnostics_build_payload      (< 50ms)
- bench_portfolio_catalog_calculate_health    (< 100ms)
- bench_scheduler_runtime_parse_cron          (< 5ms)
- bench_database_purge_old_executions         (< 200ms)
- bench_oracle_extract_serialize_rows_1000    (< 20ms)
```

Adicionar ao CI como job não-bloqueante com artefato de comparação:

```yaml
- name: Benchmark (não bloqueante)
  run: pytest -m benchmark --benchmark-json=benchmark-results.json || true
- uses: actions/upload-artifact@v4
  with:
    name: benchmark-results
    path: benchmark-results.json
```

#### F3-T4 — Regressão Visual do Dashboard com Playwright Screenshots

**Arquivo:** `Orchestrator/tests/test_e2e_dashboard.py` (ampliar)

```python
# Adicionar aos testes E2E existentes:

- test_screenshot_dashboard_overview_estado_healthy
- test_screenshot_dashboard_diagnostics_com_findings
- test_screenshot_aba_automacoes_com_risk_badges
- test_screenshot_modal_revisao_bloqueado_por_drift
- test_screenshot_beneficiamento_kpi_carregado
```

Referenciar screenshots base em `docs/playwright-screenshots/baseline/` e comparar via `expect(page).toHaveScreenshot()`.

#### F3-T5 — Elevar Threshold Final para 90%

```ini
# pytest.ini — progressão final
addopts = -p no:cacheprovider --strict-markers --cov-fail-under=90
```

Escalada controlada:

```
Atual: 77% → F1 completa: 79% → F2 completa: 85% → F3 completa: 90%
```

---

## 4. Modernização de Ferramentas

### 4.1 Substituições e Adições Recomendadas

| Área | Atual | Recomendado | Justificativa |
|---|---|---|---|
| Testes unitários React | ❌ Nenhum | **Vitest** + Testing Library | Nativo ao Vite, zero-config, 10x mais rápido que Jest |
| Testes de componente React | ❌ Nenhum | **`@playwright/experimental-ct-react`** | Reutiliza Playwright já no stack; testa componentes isolados sem servidor |
| Mutation testing Python | ❌ Nenhum | **`mutmut`** | Leve, integra ao pytest, relatório de sobreviventes |
| Property-based testing | ❌ Nenhum | **`hypothesis`** | Ideal para lógica pura do `beneficiamento/core/` e `oracle_extract.py` |
| Performance regression | ❌ Nenhum | **`pytest-benchmark`** | Detecta regressões de latência antes do deploy |
| Cobertura diferencial | ❌ Nenhum | **`diff-cover`** | Exige cobertura apenas nas linhas modificadas no PR |
| Load testing API | ❌ Nenhum | **`locust`** | Testar `/api/system/diagnostics` e `/api/portfolio/health` sob carga |

### 4.2 `diff-cover` para PRs (Quick Win)

```bash
pip install diff-cover
```

Adicionar ao job de PR no CI:

```yaml
- name: Coverage diferencial do PR
  run: |
    pytest --cov=Orchestrator/app --cov-report=xml
    diff-cover coverage.xml --compare-branch=origin/main --fail-under=85
```

Isso garante que **cada linha nova tem ≥ 85% de cobertura**, sem exigir refatoração do código legado de uma vez.

---

## 5. Melhorias no Processo de QA

### 5.1 Separação de Jobs no CI

**Situação atual:** Pipeline único `governanca.yml` mistura lint, testes unitários, integração e E2E.

**Proposta:** Dividir em jobs paralelos com dependências explícitas:

```
Job: lint-python (ruff, black, isort, bandit)    ← independente
Job: lint-frontend (ESLint + tsc)                 ← independente
Job: testes-unitarios (-m unitario)              ← depende de lint-python
Job: testes-integracao (-m integracao)           ← depende de testes-unitarios
Job: testes-e2e (-m e2e)                         ← depende de testes-integracao
Job: governanca (ValidarAutomacoes.ps1)          ← depende de lint-python
Job: benchmark (não bloqueante)                  ← depende de testes-unitarios
```

Benefício: falha rápida + feedback em paralelo.

### 5.2 `conftest.py` — Fixtures Ausentes

Analisar e adicionar ao `conftest.py` existente:

```python
# Fixtures recomendadas a adicionar:

@pytest.fixture
def mock_oracle_connection() -> Generator[MagicMock, None, None]:
    """Mock padronizado para oracledb.connect em todos os testes unitários."""
    with patch("oracledb.connect") as mock_conn:
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value.cursor.return_value.fetchmany.return_value = []
        yield mock_conn

@pytest.fixture
def worker_env_vars() -> Generator[None, None, None]:
    """Garante variáveis de ambiente mínimas para testes de worker."""
    env = {
        "API_HOST": "127.0.0.1",
        "API_PORT": "8000",
        "WORKER_MAX_CONCURRENT": "1",
    }
    with patch.dict(os.environ, env):
        yield
```

### 5.3 Labels de Teste no CHANGELOG

Adotar convenção nos commits de teste para rastreabilidade:

```
tests(worker): adiciona cenários de timeout e graceful shutdown
tests(oracle): adiciona mock unitário de oracle_extract.py
tests(dashboard): adiciona testes Vitest para schedule parser
```

---

## 6. Checklist de Implementação

### Fase 1 — Semanas 1–2

- [ ] **F1-T1** — `--strict-markers` em `pytest.ini`
- [ ] **F1-T2** — Criar `test_oracle_extract_unit.py` (10 cenários)
- [ ] **F1-T3** — Criar `test_worker_failure_scenarios.py` (7 cenários)
- [ ] **F1-T4** — Health check antes do job E2E no CI
- [ ] **F1-T5** — Criar `test_middleware_auth.py` (6 cenários)
- [ ] Verificar que todos os testes novos passam em `--cov-fail-under=77`
- [ ] Rodar `ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` ✅

### Fase 2 — Semanas 3–6

- [ ] **F2-T1** — Elevar threshold para 82%
- [ ] **F2-T2** — Setup Vitest no Dashboard + 5 arquivos de teste
- [ ] **F2-T3** — Ampliar `test_notifications.py` (5 cenários de idempotência)
- [ ] **F2-T4** — Criar `test_oracle_circuit_breaker.py` (5 cenários)
- [ ] **F2-T5** — Criar `test_portfolio_catalog_unit.py` (8 cenários)
- [ ] **F2-T6** — Criar `test_scheduler_runtime_unit.py` (7 cenários)
- [ ] Adicionar `diff-cover` ao job de PR
- [ ] Verificar cobertura acima de 82% ✅

### Fase 3 — Meses 2–3

- [ ] **F3-T1** — Setup e execução de `mutmut` nos módulos de lógica pura
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
- [`Tools/Test-PythonGovernance.ps1`](../Tools/Test-PythonGovernance.ps1) — mypy + pylint

---

*Documento gerado via análise full do repositório. Atualizar ao fechar cada fase do checklist.*
