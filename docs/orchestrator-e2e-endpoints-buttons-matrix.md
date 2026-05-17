# Matriz E2E Crítica — Orchestrator (17/05/2026)

## Escopo Validado
- Fluxo crítico: cadastro -> agenda -> execução -> parada -> logs.
- Controles globais do dashboard: `resume_all`, `pause_all`, `backup`, `purge`.
- Filtros de execuções: `status`, `automation_id`, `requested_by`, `date_from`, `date_to`.

## Matriz Endpoint x Origem UI
| Origem UI | Endpoint | Método | Payload/Query | Resposta Esperada | Erro Esperado |
|---|---|---|---|---|---|
| Modal de automação (`Salvar`) | `/api/automations` | `POST` | `name`, `script_path`, `schedule`, `enabled`, `test_mode`, `notification_channels` | `201` com automação criada | `409` nome duplicado, `422` path/schedule inválido |
| Modal de automação (`Salvar` edição) | `/api/automations/{id}` | `PUT` | Campos alterados | `200` com automação atualizada | `404` não encontrada, `422` validação |
| Botão `Executar` | `/api/automations/{id}/start` | `POST` | - | `200` com `exec_id` | `404` não encontrada, `409` execução ativa |
| Botão `Parar` | `/api/executions/{exec_id}/stop` | `POST` | - | `200` com sinal de parada | `404` execução não encontrada, `400` já finalizada |
| Modal de logs | `/api/executions/{exec_id}` + `/logs` + `/artifacts` | `GET` | `offset`, `limit` | `200` com logs/artefatos | `404` execução inexistente |
| Ação global `Retomar Todas` | `/api/automations/control/resume-all` | `POST` | - | `200` | `403` sem API Key |
| Ação global `Pausar Todas` | `/api/automations/control/pause-all` | `POST` | - | `200` | `403` sem API Key |
| Ação global `Backup` | `/api/system/backup` | `POST` | - | `200` com `path` e `size_mb` | `500` falha operacional controlada |
| Ação global `Purge` | `/api/system/purge` | `POST` | `retention_days>=7` | `200` com removidos | `400` retenção inválida |
| Visão executiva | `/api/system/overview` | `GET` | - | `200` com `kpis`, `status_breakdown`, `recent` | `403` sem API Key |
| Filtros de execuções | `/api/executions` | `GET` | `status`, `automation_id`, `requested_by`, `date_from`, `date_to`, `page`, `per_page` | `200` paginado | `422` status/data/page/per_page inválidos |

## Bugs Fechados
| ID | Causa raiz | Impacto | Correção aplicada | Regressão coberta |
|---|---|---|---|---|
| E2E-UI-001 | Submit duplicado no formulário (`onsubmit` inline + `addEventListener`) | Duplicidade de requisição e erro 409/UX inconsistente ao salvar automação | Removido binding duplicado e adicionado lock de submit com botão desabilitado durante persistência | `test_smoke_automations_flow_and_controls` + validação manual |
| E2E-AUTH-002 | API Key inválida após `403` permanecia em memória da SPA | Botões/ações sem efeito até recarregar página | `api.js` agora limpa sessão, notifica usuário e solicita nova chave imediatamente | `test_smoke_system_endpoints_success_and_operational_errors` + validação manual |
| E2E-TEXT-003 | Mensagem com mojibake em `resume-all` | Feedback textual inconsistente no dashboard | Ajuste literal para `Todas as automações retomadas.` | `test_smoke_automations_flow_and_controls` |
| E2E-API-004 | Filtros inválidos em `/api/executions` eram silenciosamente ignorados | Diagnóstico difícil e divergência UI x API | Validação explícita com `422` para `status`, `date_from`, `date_to`, `page`, `per_page` | `test_smoke_executions_filters_and_errors` |
| E2E-AUDIT-005 | Ações críticas de sistema (`backup`, `purge`, `checkpoint`) registravam ator genérico | Rastreabilidade incompleta | Auditoria padronizada via `log_audit` com `get_client_ip(request)` | `test_smoke_system_endpoints_success_and_operational_errors` |
| E2E-ENV-006 | `PROJECT_ROOT` do router `system` apontava para nível incorreto | Tela de Administração `.env` carregava conteúdo vazio mesmo com arquivo válido | Ajuste de `PROJECT_ROOT` para raiz do repositório e teste de contrato para evitar regressão | `test_system_router_project_root_points_to_repo_root` |

## Checklist Final de Botões
- `Retomar Todas`: dispara endpoint correto, exibe confirmação, atualiza cards/tabelas.
- `Pausar Todas`: dispara endpoint correto, exibe confirmação, atualiza cards/tabelas.
- `Backup DB`: dispara endpoint correto, retorna feedback de sucesso/falha.
- `Purge de Execuções`: exige retenção válida, bloqueia inválido na UI e valida no backend.
- `Salvar Automação`: sem dupla submissão, com feedback claro de sucesso/erro.
- `Executar` / `Parar`: refletem status da execução e logs em tempo real.

## Evidências de Aceite Técnico (17/05/2026)
- `C:\Automacoes\.venv\Scripts\python.exe -m pytest tests/test_api_smoke_critical.py tests/test_api.py -q` (workdir `Orchestrator`) -> `33 passed`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-OrchestratorIntegrity.ps1 -RootPath .` -> `OK`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-DashboardTemplate.ps1 -BasePath .` -> `OK`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` -> `OK`.
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-SourceEncoding.ps1 -RootPath .` -> `OK`.

## Pendências Remanescentes
- Nenhuma pendência crítica identificada no fluxo E2E validado (cadastro -> agenda -> execução -> parada -> logs).

## Template de Evidência para Entregas Futuras
- Padrão obrigatório: `docs/playwright-e2e-evidence-template.md`.
