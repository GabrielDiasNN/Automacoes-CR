# Monitor de Contexto AI-Native

Snapshot curado para bootstrap de agentes: o estado vigente e as armadilhas que ainda derrubam quem trabalha aqui. Histórico fica no `CHANGELOG.md` e, até 07/10/2026, em `docs/historico/ai-native-context-monitor-ate-07-10-2026.md` (busque com `Grep`, não carregue inteiro). Cada armadilha cita a data da entrada completa.

## Estado Atual

- **Versão operacional de referência**: Hub em linha `v1.0.0` (versão de runtime do Orchestrator, `ORCHESTRATOR_VERSION` em `Orchestrator/app/constants.py`; reset em 05/07/2026 no novo repositório). A numeração `1.3.x` do `CHANGELOG.md` é a série de releases do repositório, independente desta. `Tools/Test-SemanticGovernance.ps1` extrai a versão desta linha — não mude o formato.
- **Stack**: Python/FastAPI + APScheduler + SQLite WAL/Alembic (Orchestrator); automações orquestradas em Python (`lib/python/hub_runner.py` + `run_*.py`; o `run.ps1` é shim chamado por `powershell.exe` 5.1, deliberado — `pwsh` 7 falhou em silêncio no cron); Outlook COM e `Send-WhatsApp.ps1` seguem em PowerShell atrás de CLIs; Node.js só para WhatsApp (`lib/WhatsApp-Core.js` por processo ou daemon opcional `lib/whatsapp-daemon.js`, `WHATSAPP_DAEMON_ENABLED=1`); Dashboard React + TypeScript + Vite servido pelo FastAPI.
- **Automações em produção**: RB-01, MT-02, RE-03, OBP-04, OFST-06, ORB-07 (manifesto + `run.ps1` shim → runner Python, `queue_group="oracle"`), Beneficiamento (snapshot, sem manifesto nem `run.ps1` — exceção deliberada) e 10 **Consultas Promovidas** em `Consultas Promovidas/<slug>/` (`CP-01`..`CP-10`, motor `lib/python/promovidas/`, modo `sombra` via `AUTOMACAO_ALERT_WHATSAPP`, snapshot em `Consultas Promovidas/snapshots/`). Criticidade/SLA/cadência: `docs/governanca/automation-criticality-map.md`.
- **Oracle**: servidor 19c, mas a conta usa verificador legado (DPY-3015); `ORACLE_DRIVER_MODE`: `auto` (Thin, Thick só se exigido), `thick` ou `queue` (produção). `bridge` (node-oracledb) foi removido em 18/11/2026 e `get_driver_mode` o recusa com `ValueError`. `queue` envia o SQL por fila SMB (`lib/python/oracle_queue.py`) ao worker `v2.6.2` no TSplus (heartbeat, claim de 90 s, `--#max_rows:N`, cleanup por `exec_id`); usam a fila `fetch_all`, Beneficiamento, preflight do RE-03 e `Tools/oracle/oracle_queue_tools.py`. Config: `ORACLE_QUEUE_DIR`, `ORACLE_QUEUE_TIMEOUT_SECONDS` (padrão 180 s); o `.mcp.json` delega o modo ao `.env`. Sem `V$SQL`/`DISPLAY_CURSOR`. MCP somente leitura: `Tools/oracle/mcp_server.py` (ferramenta `oracle`). **A rede derruba qualquer sessão em ~4-6 s** (`ORA-00028`/`DPY-1001`/`DPY-4011`): conexão nova por consulta, retry só em queda de sessão (`SESSION_DROP_MARKERS` em `lib/python/oracle_session.py`); consulta mais longa não roda daqui — reescreva-a.
- **Skills**: padrão em `.github/skills/` (única árvore editável), operacionais em `.claude/skills/`; o Claude Code vê as de padrão por junction. Taxonomia e regras: `.github/skills/README.md`.
- **Acervo SQL**: `docs/oracle-schema/consultas/` (catálogo `CATALOGO_QUERIES.md`, 215 consultas validadas de 229 arquivos; busca por `Tools/oracle/oracle_catalog.py queries`). Runtime do Beneficiamento: `Produção Beneficimento/sql/templates/`. Promover consulta a runtime é `git mv`, nunca cópia.

## Armadilhas Vigentes

Cada item custa caro quando ignorado. Detalhe na entrada da data indicada no arquivo de histórico.

### Ambiente e gates

- **`.venv` fica na raiz do repositório**; de dentro de `Orchestrator/` é `..\.venv\Scripts\`. O Python do sistema dá falso verde (08/09/2026).
- **Suíte verde não é gate verde**: rode `/preflight` (ruff/bandit no escopo exato do CI, black/isort no diff, mypy/pylint) antes de dar trabalho por pronto (08/09/2026).
- **`Test-PythonGovernance.ps1` só enxerga arquivos rastreados** (`git ls-files`): para `.py` novo, passe `-Paths` explícito antes do `git add` (06/10/2026).
- **Teste de mutação é o critério de "este teste protege o comportamento"**: quebre a linha de produção e confirme que o teste falha (08/09/2026).
- **Hook `Stop`**: automatizar governança exige `-Paths` **e** `-NoCriticalPromotion`; sem o segundo, um caminho crítico promove a full scan (~340 s) e estoura o timeout (01/09/2026).
- **Pre-commit com caminho crítico roda `pylint` (com dependentes) e `PSScriptAnalyzer` só no diff**; o resto segue completo, e o `governanca-agregada` do CI roda tudo. Liste caminhos do git com `-c core.quotepath=false` e console UTF-8, senão `Produção Beneficimento/` some do gate (18/11/2026).
- **`ruff` é pinado no workflow**, não em `requirements-dev.in` (08/09/2026). `ruff --fix` em lote já removeu imports usados por teste via `importlib` e quebrou `mypy --strict` (B009/B010) — revise o diff (26/08 e 07/10/2026).

### Orchestrator

- **Regra de negócio vive em `services/`, não em routers**: o service levanta `DomainRuleError(status, detail)` e o router traduz em `HTTPException`. `db.query(...)` em router é barrado pelo gate `ORM_QUERY_IN_API_ROUTER`; exceções em `docs/architecture-standard.md` (07/10/2026).
- **`GET /api/system/health` é liveness público reduzido**; o payload completo é `GET /api/system/health/full`, autenticada (28/08/2026).
- **`EXIT_CODE_MAP`**: `3` é ERROR (`DATA_EXTRACTION_FAILED`, requeue seguro), `22` é SUCCESS (adiamento), `26` é `ORACLE_WORKER_OFFLINE` e `27` é `ORACLE_QUEUE_TIMEOUT` (ambos ERROR mapeados no contrato de falha de fila Oracle).
- **Agendador não descarta tick com `queue_group` ocupado**: cria execução que expira (`EXPIRED`) — as 6 automações compartilham `queue_group="oracle"` (26/08/2026).
- **Editar `.py` não muda o processo em produção** até reiniciar o Orchestrator; cheque `driver.py health` antes de reiniciar (esta máquina roda produção) (02/09/2026).

### Automações e WhatsApp

- **Os `run.ps1` resolvem o Python por `Resolve-HubPythonExe`** (funciona em worktree); não hardcode o venv (08/09/2026).
- **Mudança de fluxo de automação vai no `run_*.py`, não no `run.ps1`** (shim desde 18/11/2026). Valide com `run.ps1 -DryRun` (extract real, sem envio nem state). O modo teste de RB-01/MT-02 lê `AUTOMACAO_TEST_EMAIL` só do escopo User (`hr.user_environment_variable`): o processo carrega o `.env` e desviaria e-mail de produção.
- **OFST-06 e ORB-07 são irmãs, não simétricas**: a guarda que aborta sem tocar no state quando todas as linhas falham evita re-anunciar todas as OBs no WhatsApp; `test_ofst_orb_parity_unit.py` prende as invariantes (08/09/2026).
- **`_Template` no runner Python e limpeza da camada PS legada (18/11/2026):** `Tools/New-Automation.ps1` usa `-Runtime "python"` por padrão, lê templates com `-Encoding UTF8` (inclusive no PS 5.1) e gera `run.ps1` (shim), `run_<id>.py` (sobre `hub_runner.py`) e `RunWhatsApp.bat` com `-ConfigPath "%~dp0whatsapp-config.json"`. Na 1.3.118 saíram as funções sem chamador de `Lib-WhatsAppBatch` e os módulos `Lib-Oracle`, `Lib-OracleEndpoint`, `Lib-Idempotency` e `Lib-LogEvent`; `Lib-Logging` ficou com `Protect-SensitiveData`/`Write-AutomacaoLog` e `Lib-Retry` com `Send-AlertaFalhaDefinitiva`. Paridade do lote WhatsApp: fixture do PS 5.1 em `Orchestrator/tests/fixtures/`. Scaffold grava `.ps1`/`.psm1` com BOM. Contratos: `test_run_ps1_bootstrap_unit.py`, `test_scaffold_governance.py`.
- **Códigos de saída:** `1` (erro fatal genérico, RE/MT) e `4` (falha de orquestração/canal, ORB/OFST/OBP/RB) são contratos distintos, ambos ERROR em `EXIT_CODE_MAP`; não unifique. Os códigos `40`/`23` são mortos (`WhatsApp-Core.js` só sai com `0`, `21` e `24`), mas `22` vem de `Send-WhatsApp.ps1` (mutex/cooldown) e é SUCCESS em ORB-07, OFST-06, OBP-04 e RB-01.
- **MT-02 fecha a telemetria sempre via `hr.finish`** (`_encerrar` no `run_montagem.py`), eliminando risco de execução `RUNNING` órfã em saída precoce (08/09/2026; migrado em 18/11/2026).
- **Daemon WhatsApp segura o perfil** (18/11/2026): com `lib/whatsapp-daemon.js` vivo, todo envio do mesmo `clientId` passa por ele (BATCH e AUTO); daemon não pronto devolve `22` (state preservado, reenvio no próximo ciclo, status SUCCESS). VISUAL, LIST_GROUPS, `Authenticate-WhatsApp.bat` e `Keep-WhatsApp-Open.ps1` recusam com ele vivo: pare o `node ... whatsapp-daemon.js` antes de reautenticar. `WHATSAPP_DAEMON_ENABLED` só governa a subida pelo `Start-Orchestrator.ps1`.
- **Sessão WhatsApp vive em `%LOCALAPPDATA%\Automacoes\wwebjs_auth\`** (credencial; nunca no repo). Perda de sessão sai com `ExitCode 21` (27-28/07/2026).
- **Sucesso de envio é decidido pelo dispatch, não pelo ACK** do `whatsapp-web.js` (15/07/2026).

### Oracle e SQL

- **Use o catálogo local antes de escrever SQL** (`Tools/oracle/oracle_catalog.py`, skill `oracle-schema-navigator`); documentação curada já teve valor de domínio errado — confirme valores no catálogo (14/09/2026).
- **A unidade de tempo depende da tabela**: `OB.TEMPO_*`/`OB_FASES.TEMPO_*` contam a partir de 01/01/1996; `UNIDADE_PROGRAMACAO.TEMPO*` a partir de 30/12/1899. Dicionário verificado: `docs/oracle-schema/consultas/REGRAS_NEGOCIO.md` (29/09/2026).
- **"0 linhas" não é aprovação**: prove com uma variante relaxada (29/09/2026).
- **Reescrita só vale com prova**: `medir_sql_oracle.py --dump` antes/depois + `comparar_equivalencia.py`, ou comparação das CTEs isoladas quando a original não roda; padrões e anti-patterns de performance na skill `oracle-sql-patterns` (29/09 e 07/10/2026).
- **Filiação de peça ao lote de NF é `GERAPECANOTAENTRADA.IDLOTEITENSNFE`, nunca `PADRAO_QUALIDADE_SIN`** (mutável por reclassificação, mov. 695) (02/10/2026).
- **Guard SQL**: saída 3 do guard canônico é "só parse", não erro (06/10/2026). O canônico é a cópia em `lib/vendor/oracle-sql-guard/` (o da skill só por `ORACLE_SQL_GUARD_CANONICAL`); "só função" é a classe `chamada_funcao`, nunca o texto do motivo; todo executor roda a `consulta_verificacao` (`guard_sql.verificar_objetos`) antes da primeira execução, porque função sem parênteses passa no texto (19/10/2026).

### Dashboard

- **`LiveStatusProvider` é o dono único do polling de health e do WebSocket**; componente novo consome `useLiveStatus`/`useLiveEvents` (28/08/2026).
- **Use `useAction` e `useAsyncResource`** em vez de reimplementar busy/toast/fetch; trate `ApiError` (tem `status`/`retryAfter`) (02/09/2026).
- **`eslint-plugin-jsx-a11y` é gate**; não use `role="img"` em contêiner com conteúdo real (02/09/2026).

## Ponteiros de Contexto

- `README.md`: visão geral, arquitetura e estado geral do hub.
- `CONTEXT.md`: regras de negócio, contratos operacionais, integrações e ADRs principais.
- `SECURITY.md`: guardrails Zero Trust e tratamento de dados sensíveis.
- `CHANGELOG.md`: versões desde `[1.3.70]`; anteriores em `docs/historico/CHANGELOG.md` (busque a versão com `Grep`, não carregue inteiro).
- `AGENTS.md`: contrato unificado entre agentes e ordem de precedência.
- `GEMINI.md`: contrato local estável para Gemini CLI e Antigravity.
- `.github/skills/README.md`: taxonomia canônica de skills do workspace.
- `docs/qualidade/quality-dashboard.md`: snapshot de qualidade e métricas de referência.
- `docs/operacao/release-checklist.md`: checklist de promoção, governança e evidência E2E.
- `docs/qualidade/ci.md`: estrutura, regras e operação da esteira de CI do monorepo.
- `docs/governanca/padroes-nomenclatura-powershell.md`: convenções de nomenclatura para scripts e módulos PowerShell do hub.
- `Produção Beneficimento/CONTEXT.md`: exceção arquitetural deliberada — única automação sem `automation.manifest.json` e sem `run.ps1`.

## Critério de Atualização

Atualize este monitor quando uma mudança alterar arquitetura, governança, contrato operacional, validação obrigatória, stack, taxonomia de skills ou comportamento que afete decisões futuras de agentes.

- **Estado Atual** reflete só o vigente: edite no lugar, não acrescente.
- **Armadilha nova**: um item de no máximo duas linhas, com a data; o relato completo vai para o `CHANGELOG.md`. Remova o item quando a armadilha deixar de existir (código corrigido de forma que não dá mais para errar).
- **Teto**: mantenha o arquivo abaixo de ~12 KB. Passou disso, mova itens antigos para `docs/historico/`.

Não atualize este monitor para correções pequenas sem impacto contextual. Nesses casos, mantenha apenas o registro em `CHANGELOG.md` quando aplicável.
