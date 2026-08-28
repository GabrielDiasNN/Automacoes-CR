# Evidência E2E — revisão Orchestrator/Dashboard [1.3.57]

## Evidência E2E Final
- Data/Hora (BRT): `28-08-2026 11:16:00`
- URL validada: `http://127.0.0.1:8000/dashboard/`
- Ordem de execução: `Governança -> Testes de contrato/backend -> Playwright E2E (último)`
- Build: `Dashboard/dist/` reconstruído (`npm run build`, Rolldown/vite 8.2.0) e Orchestrator reiniciado via `Infrastructure/Start-Orchestrator.ps1` (0 execuções ativas no momento do reset).
- Módulos navegados:
  - `Comando` (Ctrl+K / CommandPalette)
  - `Painel`
  - `Execuções`
  - `Monitor` (Observabilidade)
  - `Beneficiamento`
  - `Automações`
  - `Sistema`
- Ações críticas validadas:
  - `Login real` (gate de API Key + Entrar) — driver `smoke`
  - `Listagem/refresh de execuções` — tabela carrega dados reais
  - `Abertura do drawer de logs de uma execução` (achado nº 3) — drawer hidrata todos os campos (`Início`, `Solicitado por`, `Tentativas 0/2`, `Exit code`), 57 linhas de log com chips de nível; sem `undefined/undefined` durante o carregamento
  - `Ctrl+K -> "Receitas" -> Enter` — navega para `/automacoes?focus=Receitas%20Emitidas` e o card correspondente recebe destaque (outline ciano)
  - `Página Sistema` — `getHealth` -> `GET /api/system/health/full` (autenticada): CPU/RAM/WAL/Disco/`banco: online · scheduler: executando`/Worker ONLINE renderizam
  - `StatusBar global` — indicador `● OK` (liveness público `GET /api/system/health`) e `SINAL` do WebSocket
  - `Monitor` — 3 gráficos uPlot (`Tendência da fila`, `Taxa de sucesso 14d`, `Duração média 14d`) renderizam; console de telemetria aguardando eventos via WebSocket compartilhado (`LiveStatusProvider`)
- Console do navegador:
  - `Erros: 0`
  - `Warnings: 0`
  - `Resumo: sem erros` — 6 rotas + login + drawer + Ctrl+K, driver `smoke` exit 0
- Resultado final:
  - `Aprovado`
- Pendências (se houver):
  - `nenhuma`

## Notas da rodada
- Durante o E2E foi detectada e corrigida uma regressão do achado nº 4: `Infrastructure/Start-Orchestrator.ps1` e `Infrastructure/MonitorAutomacoes.ps1` liam `.database`/`.scheduler` de `GET /api/system/health` (agora liveness reduzido). O primeiro passou a checar `status != "unhealthy"` na rota pública; o segundo (que já envia `X-API-Key`) passou a consumir `GET /api/system/health/full`.
- Screenshots: `Logs/driver/rota-*--pos-1357.png`, `Logs/driver/e2e-drawer-execucao.png`, `Logs/driver/e2e-cmdk-focus.png` (`Logs/` é gitignored).
