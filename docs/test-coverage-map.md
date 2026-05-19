# Mapa de Cobertura de Testes (Test Coverage Map)

Este documento mapeia os módulos críticos do backend do **Orquestrador (FastAPI & SQLite)**, identificando as suites de teste correspondentes, os cenários cobertos e as lacunas (gaps).

---

## 🗺️ Matriz de Mapeamento de Cobertura

O quadro abaixo descreve a cobertura dos módulos prioritários de runtime do produto:

| Módulo / Serviço | Arquivo Fonte | Suite de Testes | Cenários Cobertos | Estado |
|---|---|---|---|---|
| **Controle de Fila & Requeue** | `services/execution_runtime.py` | `test_queue_rules.py`<br>`test_worker_queue.py` | - Retry limitado por `max_retries`<br>- Bloqueio de requeue por `queue_group` ativo<br>- Prioridade de execução | ✅ Coberto |
| **Diagnóstico do Sistema** | `services/system_diagnostics.py` | `test_diagnostics.py` | - Detecção de worker offline via heartbeat<br>- Análise de fila parada (stalled queue)<br>- Verificação de riscos de concorrência e WAL | ✅ Coberto |
| **Agendamento de Jobs** | `services/scheduler_runtime.py` | `test_diagnostics.py`<br>`test_api.py` | - Sincronização de agenda<br>- Recuperação automática de órfãos | ✅ Coberto |
| **Validação de Entradas & Env** | `services/env_admin.py`<br>`routers/automations.py` | `test_validation.py` | - Rejeição de cron schedule inválido<br>- Proteção contra segredos vazados no `.env` | ✅ Coberto |
| **Contrato e Resiliência da API**| `routers/executions.py`<br>`routers/automations.py` | `test_api_contracts.py`<br>`test_api.py` | - Versionamento com `contract_version`<br>- Mascaramento de chaves secretas em erros<br>- Validação de payloads dinâmicos | ✅ Coberto |

---

## 🎯 Gaps Mitigados

### 1. Regras de Fila (`queue_group`)
*   **Gap anterior:** Requeues manuais podiam ignorar a concorrência por grupo ativo.
*   **Mitigação:** Criada a suite `test_queue_rules.py` validando os limites de concorrência, retries máximos e tratamento de exit codes conhecidos.

### 2. Monitoramento Ativo (Diagnósticos)
*   **Gap anterior:** O endpoint de diagnósticos operacionais (`/api/system/diagnostics`) não era coberto por testes unitários dedicados.
*   **Mitigação:** Criada a suite `test_diagnostics.py` simulando cenários de heartbeats expirados, travas de banco SQLite em perigo e alertas operacionais corretivos.

### 3. Validação de Segurança e Agenda
*   **Gap anterior:** Riscos de gravação de cron schedules mal-formatados ou injeção de segredos em arquivos `.env`.
*   **Mitigação:** Criada a suite `test_validation.py` forçando validações estritas de inputs operacionais da API administrativa.

### 4. Estabilidade de Contratos
*   **Gap anterior:** O cabeçalho de integridade e o campo `contract_version` podiam sofrer desvios entre builds.
*   **Mitigação:** Criada a suite `test_api_contracts.py` garantindo que os contratos expostos aos consumidores (FastAPI) sigam a risca a especificação de resposta padrão.
