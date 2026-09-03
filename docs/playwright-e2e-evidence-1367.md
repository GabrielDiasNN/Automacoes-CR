# Evidência E2E — revisão geral do frontend (Dashboard) [1.3.64]–[1.3.67]

## Evidência E2E Final
- Data/Hora (BRT): `02-09-2026 21:33:57`
- URL validada: `http://127.0.0.1:8000/dashboard/`
- Ordem de execução: `Governança -> Testes de contrato/backend -> Playwright E2E (último)`
- Build: `Dashboard/dist/` reconstruído a cada onda (`npm run build`, vite 8.2.0) contra a instância viva de produção nesta máquina (`.venv\Scripts\python .claude\skills\run-orchestrator\driver.py smoke`, sem reiniciar o Orchestrator).
- Suíte oficial: `pytest -m e2e` em `Orchestrator/tests/test_e2e_dashboard.py` — **12 passed** (banco de teste isolado, `TEST_DB_PATH` dedicado por PID).
- Módulos navegados:
  - `Painel`
  - `Execuções`
  - `Monitor`
  - `Beneficiamento`
  - `Automações`
  - `Sistema`
  - `Rota inexistente` (nova `NotFoundPage`)
- Ações críticas validadas:
  - `test_e2e_dashboard_navigation` — 6 rotas, console limpo
  - `test_e2e_dashboard_executions_detail_and_filter` — drawer de detalhe, filtro de status, e agora `automation_id` (novo filtro de drill-down)
  - `test_e2e_dashboard_automations_visible` — cards e botão Disparar presentes
  - **`test_e2e_dashboard_automations_dispatch_confirm_and_cancel` (novo, Onda 5.5)** — clicar em "Disparar" abre o `ConfirmModal` (`role="alertdialog"`, título "Disparar automação"); "Cancelar" fecha o modal; contagem de `Execution` no banco de teste **antes == depois**, confirmando que nenhuma execução é enfileirada ao cancelar
  - `test_e2e_dashboard_system_instruments` — gauges, WAL Checkpoint
  - `test_screenshot_*` (4 testes) — **passaram dentro da tolerância de 5%** (`VISUAL_DIFF_TOLERANCE`) mesmo após as mudanças visuais das Ondas 2 (contraste do `StatusTag`, legenda do `TimeSeries`) e 3 (reforma completa do card de Automações — SLA vivo, links de drill-down, faixa de falha). **Nenhum baseline precisou ser regenerado.**
  - Fora da suíte oficial, verificação manual com Playwright (scripts pontuais, não versionados) contra a instância real de produção: rail mobile (`inert` correto em desktop/mobile, foco move para dentro da gaveta ao abrir, Escape fecha); Treemap navegável por Enter (15 células, `role="button"`); `ConfirmModal`/Drawer/`CommandPalette` fecham por clique-fora e Escape sem fechar em clique interno; `Pager` de Execuções ("página 1/142" → "página 2/142" contra 3549 registros reais); `ProductAutocomplete` populando opções reais; toast "WAL Checkpoint executado com sucesso." (mensagem real do backend) após `useAction`.
- Console do navegador:
  - `Erros: 0`
  - `Warnings: 0`
  - `Resumo: sem erros` — 6 rotas + login, `driver.py smoke` exit 0, repetido a cada onda (1 a 5.1)
- Resultado final:
  - `Aprovado`
- Pendências (se houver):
  - `nenhuma` — a pendência de regeneração de baseline anotada nos CHANGELOGs das Ondas 2 e 3 foi verificada nesta rodada e não se concretizou: os 4 testes `test_screenshot_*` passam dentro da tolerância configurada.

## Notas da rodada
- Suíte completa do backend (`pytest`, sem filtro de marker): **1034 passed** (Onda 3, após expor `avg_duration_24h_seconds` em `AutomationResponse`).
- `mypy`/`pylint` (`Tools/Test-PythonGovernance.ps1`): limpo.
- Suíte do frontend (`vitest`): **125 passed** (11 arquivos), +10 desde o início da revisão (`extractTimeBr`, `useAction` ×6, `ApiError`/`Retry-After`, backoff de 429).
- Bundle inicial medido (Onda 5.1, code-splitting): 348 KB → 310 KB bruto (348→310 KB), 116,5 KB → 107 KB gzip.
