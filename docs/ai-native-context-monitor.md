# Monitor de Contexto AI-Native

Este arquivo é o snapshot curado para bootstrap de agentes no Hub de Automações. Ele não substitui o `CHANGELOG.md`; resume apenas o estado operacional e os marcos recentes que afetam decisões futuras.

## Estado Atual

- **Versão operacional de referência**: Hub em linha `v9.3.6`, com Orchestrator/Dashboard operando sobre baseline Alembic, governança semântica, testes offline de Node/WhatsApp, cobertura ampliada de runtime e o Agente de Revisão de Código declarativo estruturado ativo.
- **Stack ativa**: Python/FastAPI, PowerShell corporativo, Node.js para comunicações, Dashboard SPA estático e SQLite em WAL com Alembic.
- **Padrão arquitetural governado**: `docs/architecture-standard.md` registra camadas e severidades oficiais, e `Tools/Test-ArchitectureStandard.ps1` valida o contrato no quality gate falhando apenas violações críticas no v1.
- **Skills do workspace**: `.github/skills/` é a fonte canônica; `.gemini/skills/` é apenas mirror por junction/symlink.
- **Skills globais obrigatórias**: `ai-engineering-discipline`, `protocolo-valeg` e `git-ide-governance-skill`.
- **Contratos críticos**: Zero Trust, encoding governado, documentação viva, validação de skills, governança de catálogo de automações, Playwright como última validação para UI/front-back, conformidade estrita de datas DD/MM/YYYY e o novo Agente de Revisão de Código declarativo estruturado (`.agents/agents/code-review-agent/agent.json` e `Tools/Review-Code.ps1`).
- **Validação de referência mais recente**: em 27/05/2026, a governança passou a usar classificação compartilhada de diff entre `pre-commit` e GitHub Actions, adicionou validação semântica de versões/catálogo/dependências e passou a executar teste offline de Node/WhatsApp no quality gate.
- **Catálogo governado do hub (24/05/2026)**: automações ativas agora carregam `automation.manifest.json` versionado, com criticidade, SLA, dependências, smoke tests e vínculo para runbook. O dashboard consome `/api/portfolio/health` para expor esse cruzamento operacional.
- **Baseline operacional do hub (25/05/2026)**: `GET /api/system/baseline`, `diagnostics.operational_baseline` e `history.baseline_status` compartilham thresholds únicos para worker, fila, WAL, execuções acima do limite e ownership órfão.
- **Governança do portfólio no overview (26/05/2026)**: `/api/portfolio/health.summary` e `/api/system/overview.portfolio` agora publicam `status`, `top_issue`, `recommended_action` e contagem de itens em incidente/atenção para o painel principal.
- **Preflight governado no cadastro (26/05/2026)**: `POST /api/automations/preflight` agora compara o payload com `automation.manifest.json` quando a pasta já está governada, devolvendo bloqueios de manifesto/docs/smoke antes de `create/update`.
- **Beneficiamento V1 operacional (31/05/2026)**: a aba Beneficiamento permanece como tela única para PCP diário sobre SQLite histórico local, mas agora acrescenta filtro por Alternativo, visão geral por turno, bloco dedicado de Tingimento e drill-down local por clique. O contrato principal continua sendo `GET /api/beneficiamento/overview`, complementado por `GET /api/beneficiamento/detail` para modal operacional e por `/historico` para busca compacta.
- **Guardrail sem Oracle em GET (31/05/2026)**: a UI V0 não chama runner, SQL template ou refresh; leituras do Dashboard permanecem restritas ao SQLite histórico e snapshots locais. O indicador principal deve ser tratado como "Eficiência de tempo" (`MIN_PREV / MIN_REAL * 100`), não como OEE industrial completo.
- **Beneficiamento V1 otimizado (08/06/2026)**: o histórico local agora persiste chaves derivadas de turno, máquina, fase e código operacional, e o `/overview` reaproveita um recorte temporário filtrado por request. A montagem direta do overview caiu para a faixa de centenas de milissegundos na base promovida, sem alterar o contrato HTTP nem reintroduzir Oracle em `GET`.
- **Beneficiamento tipado e Orchestrator endurecido (12/06/2026)**: o domínio ganhou `core/`, `data` e `contracts/`; a implementação histórica canônica está em `contracts/`, consultas usam colunas SQLite e reservam o blob para auditoria. Worker e scheduler usam escopo centralizado de sessão, WAL periódico `PASSIVE`, fases explícitas de execução e serviço único de broadcast.

## Mudanças Recentes Relevantes

- **Padronização dos contratos de agentes (13/06/2026)**: `AGENTS.md`, `CLAUDE.md` e `GEMINI.md` local foram unificados em hierarquia coesa. `CLAUDE.md` foi reescrito em PT-BR e promovido a contrato de nível 3 (junto com `GEMINI.md`). Seção "Princípios Comportamentais" consolidada em `AGENTS.md` como fonte canônica dos 4 princípios para todos os agentes. Regra de resolução de conflito simplicidade vs. governança adicionada à ordem de precedência. Bootstrap atualizado para incluir `CLAUDE.md`. `GEMINI.md` global e skill `ai-engineering-discipline` alinhados com cross-references. Ver `AGENTS.md` e `CLAUDE.md`.
- **Reestruturação de performance e runtime (12/06/2026)**: schema v2 do histórico do Beneficiamento exige recarga retroativa após recriação, reduz parsing JSON no hot path e estabelece contratos modulares. No Orchestrator, sessões, checkpoint WAL e execução do worker foram endurecidos sem mudar estados ou exit codes. Ver `CHANGELOG.md`.
- **DX do quality gate local (10/06/2026)**: `Tools/ValidarAutomacoes.ps1` agora publica o modo de seleção governada e o tempo por etapa do ciclo local, além de aceitar exportação opcional via `-SummaryJsonPath`. O objetivo é acelerar triagem de gargalos locais sem afrouxar o gate canônico. Ver `CHANGELOG.md`.
- **Telemetria leve do Orchestrator (10/06/2026)**: `GET /api/system/diagnostics` e `GET /api/system/overview` agora expõem `performance.timings_ms` para custo de montagem por etapa. A refatoração permaneceu interna e aditiva, preservando os endpoints públicos enquanto melhora a triagem de hotspots de payload. Ver `CHANGELOG.md`.
- **Evolução V1 do Beneficiamento (31/05/2026)**: a UI passa a abrir modal local de detalhe ao clicar em produto, turno, fase, máquina/fase ou OB. O backend normaliza turno a partir de `TURNO_DESC`/`TURNO_PROD`, trata `CODIGO_ALTERNATIVO` como eixo principal do produto e expõe bloco dedicado de Tingimento com médias, reprocesso e percentuais.
- **Refatoração de performance do Beneficiamento (08/06/2026)**: o filtro principal do overview deixa de usar `date(DATA_FIM)`, passa a depender de colunas persistidas/normalizadas do SQLite e monta dataset temporário por request para KPIs, rankings, turnos e Tingimento. O frontend também ganha debounce curto e render progressivo da aba.
- **API de Produção do Beneficiamento (31/05/2026)**: o Orchestrator agora expõe saúde, frescor e metadados Oracle dos snapshots de Beneficiamento; `timeout_applied=false` vira atenção operacional, preservando baixo custo no Oracle e limite de 20 segundos. Ver `Produção Beneficimento/docs/arquitetura.md`.
- **Agente de Revisão de Código e Reposicionamento do Pre-commit (27/05/2026)**: criação do Agente de Revisão de Código declarativo estruturado (`.agents/agents/code-review-agent/agent.json` e `Tools/Review-Code.ps1`) com reestruturação do `ValidarAutomacoes.ps1`. O contrato correto agora é: hook local rápido para diffs comuns, escalonamento para scan completo em caminhos críticos e CI completo como fonte final de verdade. Ver `CHANGELOG.md`.
- **Governança semântica e testes offline (27/05/2026)**: criado `Tools/Test-SemanticGovernance.ps1` para bloquear drift entre monitor, constantes, docs, skills, catálogo e dependências Node; `Tools/Test-NodeCommunications.ps1` passa a validar o contrato offline de WhatsApp sem sessão real. Ver `CHANGELOG.md`.
- **Disciplina global de engenharia com IA (22/05/2026)**: adicionada `ai-engineering-discipline` como skill global canônica e obrigatória para alinhar Codex, Gemini CLI e Antigravity. Ver `CHANGELOG.md`.
- **Baseline operacional formalizado (25/05/2026)**: o Orchestrator agora expõe um resumo único `healthy` / `attention` / `incident` em `GET /api/system/baseline`, reaproveitado em `diagnostics`, `history` e no snapshot de qualidade local. Ver `CHANGELOG.md`.
- **Resumo operacional do portfólio (26/05/2026)**: a saúde governada do catálogo passou a ser sintetizada no backend e replicada em `/api/system/overview`, permitindo ao dashboard principal tratar drift, docs pendentes e runtime não reconciliado como risco operacional de primeira classe. Ver `CHANGELOG.md`.
- **Contrato de Governança de Datas (26/05/2026)**: estabilizado o guardrail de conformidade de datas. O Quality Gate (`ValidarAutomacoes.ps1`) passa a exigir a aprovação estática do novo validador de datas para prevenir regressões de formatação de exibição. Ver `CHANGELOG.md`.
- **Bloqueio administrativo por manifesto (26/05/2026)**: o modal de revisão da aba `Automações` passou a mostrar quando o save está bloqueado pelo manifesto canônico, e a grade administrativa ganhou sinal explícito de catálogo (`CAT`), drift (`DRIFT`) e documentação (`DOCS`). Ver `CHANGELOG.md`.
- **Scaffold endurecido (26/05/2026)**: o onboarding de novas automações agora nasce mais próximo do contrato governado e menos dependente de preenchimento manual pós-geração. Ver `CHANGELOG.md`.
- **Observabilidade histórica e ownership do worker (24/05/2026)**: o Orchestrator passou a registrar `claimed_at`, `worker_instance_id` e `worker_pid` nas execuções, identificar `RUNNING` órfão no diagnóstico e persistir snapshots em `system_health_snapshots`, expostos por `GET /api/system/history`. Ver `CHANGELOG.md`.
- **Preflight administrativo de automações (24/05/2026)**: `POST /api/automations/preflight` torna-se a etapa única de validação antes de `create/update`, normalizando canais e validando o entrypoint real. Ver `CHANGELOG.md`.
- **Governança de catálogo (24/05/2026)**: `Tools/Test-AutomationCatalog.ps1` passa a validar manifesto, runbook, smoke tests e entrypoint; `Tools/New-Automation.ps1` cria manifesto e runbook inicial por padrão.
- **Reorganização do contexto AI-Native (22/05/2026)**: `GEMINI.md` passa a ser contrato local estável; este monitor concentra o snapshot curado para agentes. Ver `CHANGELOG.md`.
- **Receitas Bloqueadas v2.3.2 (22/05/2026)**: diff de estado passou a classificar alteração somente quando a coluna "Data Bloqueio" muda, reduzindo alertas redundantes. Ver `CHANGELOG.md`.
- **Refatoração e estabilização de testes v9.2.0 (22/05/2026)**: suíte monolítica foi decomposta, testes de notificações/worker foram adicionados e fixtures E2E ficaram mais resilientes. Ver `CHANGELOG.md`.
- **Anchor time em intervalos v9.1.0 (20/05/2026)**: agendamentos por intervalo ganharam horário de âncora (`anchor_time`) no backend, scheduler e frontend. Ver `CHANGELOG.md`.
- **Alembic Schema Evolution v9.0.0 (20/05/2026)**: migrações estruturadas substituem evolução manual de schema, com startup programático e modo batch para SQLite. Ver `CONTEXT.md` e `CHANGELOG.md`.
- **Playwright Evidence Governance v6.5.4 (18/05/2026)**: evidências E2E passaram a ser validadas por governança e devem registrar URL real, console limpo e resultado aprovado. Ver `docs/playwright-e2e-standard.md`.
- **Shared Skills Canonicalization (16/05/2026)**: `.github/skills/` consolidada como fonte canônica do workspace, com `.gemini/skills/` como mirror de compatibilidade. Ver `AGENTS.md` e `.github/skills/README.md`.

## Ponteiros de Contexto

- `README.md`: visão geral, arquitetura e estado geral do hub.
- `CONTEXT.md`: regras de negócio, contratos operacionais, integrações e ADRs principais.
- `SECURITY.md`: guardrails Zero Trust e tratamento de dados sensíveis.
- `CHANGELOG.md`: histórico completo e auditável de versões.
- `AGENTS.md`: contrato unificado entre agentes e ordem de precedência.
- `GEMINI.md`: contrato local estável para Gemini CLI e Antigravity.
- `.github/skills/README.md`: taxonomia canônica de skills do workspace.
- `docs/quality-dashboard.md`: snapshot de qualidade e métricas de referência.
- `docs/release-checklist.md`: checklist de promoção, governança e evidência E2E.

## Critério de Atualização

Atualize este monitor quando uma mudança alterar arquitetura, governança, contrato operacional, validação obrigatória, stack, taxonomia de skills ou comportamento que afete decisões futuras de agentes.

Não atualize este monitor para correções pequenas sem impacto contextual. Nesses casos, mantenha apenas o registro em `CHANGELOG.md` quando aplicável.
