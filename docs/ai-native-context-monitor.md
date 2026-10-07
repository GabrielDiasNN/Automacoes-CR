# Monitor de Contexto AI-Native

Snapshot curado para bootstrap de agentes no Hub de Automações: o estado vigente e as armadilhas que ainda derrubam quem trabalha aqui. Não é histórico — esse fica no `CHANGELOG.md` e, até 07/10/2026, em `docs/historico/ai-native-context-monitor-ate-07-10-2026.md` (consulte por data/termo com `Grep`, não carregue inteiro). Cada armadilha abaixo cita a data da entrada completa naquele arquivo.

## Estado Atual

- **Versão operacional de referência**: Hub em linha `v1.0.0` (versão de runtime do Orchestrator, `ORCHESTRATOR_VERSION` em `Orchestrator/app/constants.py`; reset em 05/07/2026 no novo repositório). A numeração `1.3.x` do `CHANGELOG.md` é a série de releases do repositório, independente desta. `Tools/Test-SemanticGovernance.ps1` extrai a versão desta linha — não mude o formato.
- **Stack**: Python/FastAPI + APScheduler + SQLite WAL/Alembic (Orchestrator), PowerShell 5.1 nos runtimes de automação (deliberado — `pwsh` 7 causou falha silenciosa no cron), Node.js só para WhatsApp, Dashboard React + TypeScript + Vite servido pelo FastAPI.
- **Automações em produção**: RB-01, MT-02, RE-03, OBP-04, OFST-06, ORB-07 (manifesto + `run.ps1`, `queue_group="oracle"`) e o Beneficiamento (snapshot, sem manifesto nem `run.ps1` — exceção deliberada, não lacuna). Criticidade/SLA/cadência: `docs/governanca/automation-criticality-map.md`.
- **Oracle**: 12.2 Standard Edition, client 12.2 (sem `call_timeout`), usuário de leitura sem `V$SQL`/`DISPLAY_CURSOR`. **A rede desta máquina derruba qualquer sessão em ~4-6 s** (`ORA-00028`/`DPY-1001`/`DPY-4011`): conexão nova por consulta e retry só em queda de sessão (lista única `SESSION_DROP_MARKERS` em `lib/python/oracle_session.py`). Consulta que precisa de mais que isso não roda daqui — reescreva-a.
- **Skills**: padrão em `.github/skills/` (única árvore editável), operacionais em `.claude/skills/`; o Claude Code vê as de padrão por junction. Taxonomia e regras: `.github/skills/README.md`.
- **Acervo SQL**: `docs/oracle-schema/consultas/` (referência sobre o ERP; catálogo gerado `CATALOGO_QUERIES.md`, 199 consultas validadas no Oracle em 07/10/2026). SQL de runtime do Beneficiamento: `Produção Beneficimento/sql/templates/`. Promoção de consulta para runtime é `git mv`, nunca cópia.

## Armadilhas Vigentes

Cada item custa caro quando ignorado. Detalhe na entrada da data indicada no arquivo de histórico.

### Ambiente e gates
- **`.venv` fica na raiz do repositório**; de dentro de `Orchestrator/` é `..\.venv\Scripts\`. O Python do sistema dá falso verde (08/09/2026).
- **Suíte verde não é gate verde**: rode `/preflight` (ruff/bandit no escopo exato do CI, black/isort no diff, mypy/pylint) antes de dar trabalho por pronto (08/09/2026).
- **`Test-PythonGovernance.ps1` só enxerga arquivos rastreados** (`git ls-files`): para `.py` novo, passe `-Paths` explícito antes do `git add` (06/10/2026).
- **Teste de mutação é o critério de "este teste protege o comportamento"**: quebre a linha de produção e confirme que o teste falha (08/09/2026).
- **Hook `Stop`**: automatizar governança exige `-Paths` **e** `-NoCriticalPromotion`; sem o segundo, um caminho crítico promove a full scan (~340 s) e estoura o timeout (01/09/2026).
- **`ruff` é pinado no workflow**, não em `requirements-dev.in` (08/09/2026). `ruff --fix` em lote já removeu imports usados por teste via `importlib` e quebrou `mypy --strict` (B009/B010) — revise o diff (26/08 e 07/10/2026).

### Orchestrator
- **Regra de negócio vive em `services/`, não em routers**: o service levanta `DomainRuleError(status, detail)` e o router só traduz em `HTTPException`. `db.query(...)` em router é bloqueado por gate (`ORM_QUERY_IN_API_ROUTER`); escritas ORM restantes são exceção documentada em `docs/architecture-standard.md` (07/10/2026).
- **`GET /api/system/health` é liveness público reduzido**; o payload completo é `GET /api/system/health/full`, autenticada (28/08/2026).
- **`EXIT_CODE_MAP`**: `3` é ERROR (`DATA_EXTRACTION_FAILED`, requeue seguro) e `22` é SUCCESS (adiamento) — semântica mudou em 31/07/2026.
- **Agendador não descarta tick com `queue_group` ocupado**: cria execução que expira (`EXPIRED`) — as 6 automações compartilham `queue_group="oracle"` (26/08/2026).
- **Editar `.py` não muda o processo em produção** até reiniciar o Orchestrator; cheque `driver.py health` antes de reiniciar (esta máquina roda produção) (02/09/2026).

### Automações e WhatsApp
- **Os `run.ps1` resolvem o Python por `Resolve-HubPythonExe`** (funciona em worktree); não hardcode o venv (08/09/2026).
- **OFST-06 e ORB-07 são irmãs, não simétricas**: a guarda que aborta sem tocar no state quando todas as linhas falham evita re-anunciar todas as OBs no WhatsApp; `test_ofst_orb_parity_unit.py` prende as invariantes (08/09/2026).
- **MT-02 sai com `exit` cru** e precisa fechar a telemetria em cada saída precoce, senão deixa execução `RUNNING` órfã (08/09/2026).
- **Sessão WhatsApp vive em `%LOCALAPPDATA%\Automacoes\wwebjs_auth\`** (credencial da conta; nunca na árvore do repo). Perda de sessão sai com `ExitCode 21` (27-28/07/2026).
- **Sucesso de envio é decidido pelo dispatch, não pelo ACK** do `whatsapp-web.js` (15/07/2026).

### Oracle e SQL
- **Use o catálogo local antes de escrever SQL** (`Tools/oracle/oracle_catalog.py`, skill `oracle-schema-navigator`); documentação curada já teve valor de domínio errado — confirme valores no catálogo (14/09/2026).
- **A unidade de tempo depende da tabela**: `OB.TEMPO_*`/`OB_FASES.TEMPO_*` contam a partir de 01/01/1996; `UNIDADE_PROGRAMACAO.TEMPO*` a partir de 30/12/1899. Dicionário verificado: `docs/oracle-schema/consultas/REGRAS_NEGOCIO.md` (29/09/2026).
- **"0 linhas" não é aprovação**: prove com uma variante relaxada (29/09/2026).
- **Reescrita só vale com prova**: `medir_sql_oracle.py --dump` antes/depois + `comparar_equivalencia.py`, ou comparação das CTEs isoladas quando a original não roda; padrões e anti-patterns de performance na skill `oracle-sql-patterns` (29/09 e 07/10/2026).
- **Filiação de peça ao lote de NF é `GERAPECANOTAENTRADA.IDLOTEITENSNFE`, nunca `PADRAO_QUALIDADE_SIN`** (mutável por reclassificação, mov. 695) (02/10/2026).
- **Guard SQL**: código de saída 3 do guard canônico significa "só parse", não erro de ferramenta (06/10/2026).

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
