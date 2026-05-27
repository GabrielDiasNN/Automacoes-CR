# Estratégia de Testes — Hub de Automações

> **Versão:** v9.3.6 | **Atualizado:** 27/05/2026

---

## 1. Visão Geral

O ecossistema de testes do Hub de Automações é organizado em três camadas:

```
┌─────────────────────────────────────┐
│   E2E (Playwright) — Interface UI   │  ← Validação final obrigatória
├─────────────────────────────────────┤
│   Integração (pytest + TestClient)  │  ← Rotas FastAPI + fluxos de fila
├─────────────────────────────────────┤
│   Unitários (pytest + mock)         │  ← Lógica de negócio isolada
└─────────────────────────────────────┘
```

---

## 2. Suítes Existentes

| Arquivo | Camada | O que cobre |
|---|---|---|
| `tests/test_api.py` | Integração | Smoke test das rotas principais com banco real |
| `tests/test_api_smoke_critical.py` | Integração | Endpoints de sistema críticos e erros operacionais |
| `tests/test_filters.py` | Integração | Matriz de filtros do backend: automações, execuções, auditoria, paginação e inválidos |
| `tests/test_database_schema.py` | Unitário | Valida colunas do schema contra `EXPECTED_SCHEMA` |
| `tests/test_diagnostics.py` | Integração | Cenários de diagnóstico: worker offline, fila parada, WAL risk, ownership órfão |
| `tests/test_queue_rules.py` | Integração | Regras de requeue, claim por `queue_group`, max_retries e prioridade |
| `tests/test_sanitization.py` | Unitário | `sanitize_log_payload`: mascaramento de segredos |
| `tests/test_schedule_advanced.py` | Unitário | Normalização avançada de agenda, cron, intervalos, `anchor_time` e previews |
| `tests/test_timezone_contract.py` | Unitário | Contrato de datas/horários em BRT nos endpoints e no preview |
| `tests/test_e2e_dashboard.py` | E2E | Navegação real do dashboard, busca/filtros visíveis, atalhos operacionais, logs e evidência Playwright |
| `tests/test_portfolio.py` | Integração | Catálogo governado, drift entre manifesto e runtime e leitura segura de runbook |
| `tests/test_receitas_emitidas.py` | Unitário | Smoke da geração HTML e sanitização básica de Receitas Emitidas |
| `tests/test_validation.py` | Integração | Validação de schedule, `.env` e preflight administrativo |

> **Total atual:** 165 testes coletados | Cobertura atual: 81% | Meta de cobertura: ≥ 60% (`pytest-cov`)

---

## 3. Como Rodar a Suíte Localmente

```powershell
# A partir do diretório Orchestrator/
cd Orchestrator

# Suite completa
.venv\Scripts\python.exe -m pytest tests/ -v

# Catálogo governado + automações
.venv\Scripts\python.exe -m pytest tests/test_portfolio.py tests/test_receitas_emitidas.py -q

# Apenas unitários (sem banco real)
.venv\Scripts\python.exe -m pytest tests/ -v -m "not integration"

# Com cobertura
.venv\Scripts\python.exe -m pytest tests/ --cov=app --cov-report=term-missing -q

# Parar no primeiro erro
.venv\Scripts\python.exe -m pytest tests/ -x -q
```

---

## 4. Como Rodar no CI (GitHub Actions)

O pipeline `.github/workflows/ci.yml` executa automaticamente em `push` e `pull_request`:

1. Instala dependências do `requirements.txt`
2. Aplica migrações de schema (`run_schema_migrations()`)
3. Roda `pytest tests/ -q --tb=short`
4. Falha o PR se qualquer teste quebrar

> Para mudanças de UI, o Playwright E2E **não é executado no CI** (requer servidor ativo).
> A evidência E2E deve ser gerada e anexada manualmente ao PR.

---

## 5. Política de Cobertura Mínima

| Módulo | Cobertura Mínima |
|---|---|
| `app/security.py` | ≥ 85% |
| `app/services/` | ≥ 70% |
| `app/routers/` | ≥ 60% |
| `app/schemas/` | ≥ 60% |
| Total do projeto | ≥ 60% |

Verificar com:
```powershell
.venv\Scripts\python.exe -m pytest tests/ --cov=app --cov-fail-under=60 -q
```

---

## 6. Convenções de Mock e Fixtures

### Fixtures Padrão (`conftest.py`)

```python
@pytest.fixture
def db():
    """Banco SQLite em memória com schema completo e migrações aplicadas."""
    # Usa engine in-memory para isolamento total

@pytest.fixture
def client(db):
    """TestClient FastAPI com injeção do banco de teste."""
    # Usa override de dependency injection do FastAPI
```

### Regras de Mock

- **Nunca mockar o modelo de dados** (`models.py`) — testes de integração usam banco real em memória.
- Mockar **apenas dependências externas**: Oracle, WhatsApp/Puppeteer, SMTP, filesystem.
- Usar `unittest.mock.patch` com contexto `with` ou decorador `@patch`.
- Fixtures de dados devem ser **atômicas e auto-limpas** — nunca deixar estado entre testes.

### Exemplos de Mock

```python
# Mock de dependência externa
with patch("app.services.notifier.send_whatsapp") as mock_wa:
    mock_wa.return_value = {"status": "sent"}
    response = client.post("/api/automations/1/start")

# Mock de timestamp para testes de SLA
with patch("app.timezone.get_now_local", return_value=datetime(2026, 1, 1, 12, 0)):
    result = calculate_sla_status(automation_id=1, db=db_session)
```

---

## 7. Adicionando Novos Testes

Ao implementar uma nova feature:

1. **Unitário**: Criar `tests/test_<modulo>.py` para lógica de negócio isolada.
2. **Integração**: Adicionar cenários em `test_api_smoke_critical.py` ou criar novo arquivo.
   Para filtros e paginação, preferir consolidar a matriz em `test_filters.py`.
3. **Nomenclatura**: `test_<o_que_faz>_<quando>_<resultado_esperado>`.
4. **Exemplos:**
   - `test_sla_status_returns_violated_when_avg_exceeds_limit`
   - `test_requeue_is_blocked_when_queue_group_has_active_execution`

---

## 🧠 Gestão de Contexto (AI-Native)

- Este documento descreve a estratégia de testes em `v9.3.6`.
- Atualize quando novas suítes forem criadas ou quando a meta de cobertura mudar.
