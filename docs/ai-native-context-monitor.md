# Monitor de Contexto AI-Native

Este arquivo é o snapshot curado para bootstrap de agentes no Hub de Automações. Ele não substitui o `CHANGELOG.md`; resume apenas o estado operacional e os marcos recentes que afetam decisões futuras.

## Estado Atual

- **Versão operacional de referência**: Hub em linha `v9.3.2`, com Orchestrator/Dashboard operando sobre baseline Alembic, ownership do worker, baseline operacional formalizado e governança compartilhada entre Codex, Gemini CLI e Antigravity.
- **Stack ativa**: Python/FastAPI, PowerShell corporativo, Node.js para comunicações, Dashboard SPA estático e SQLite em WAL com Alembic.
- **Skills do workspace**: `.github/skills/` é a fonte canônica; `.gemini/skills/` é apenas mirror por junction/symlink.
- **Skills globais obrigatórias**: `ai-engineering-discipline`, `protocolo-valeg` e `git-ide-governance-skill`.
- **Contratos críticos**: Zero Trust, encoding governado, documentação viva, validação de skills, governança agregada, Playwright como última validação para UI/front-back.
- **Validação de referência mais recente**: em 26/05/2026, a suíte completa do Orchestrator executou com `151 passed`, a governança agregada fechou sem erros e o dashboard permaneceu com `8 passed` na rodada E2E final após elevar o resumo do portfólio para o overview principal.
- **Catálogo governado do hub (24/05/2026)**: automações ativas agora carregam `automation.manifest.json` versionado, com criticidade, SLA, dependências, smoke tests e vínculo para runbook. O dashboard consome `/api/portfolio/health` para expor esse cruzamento operacional.
- **Baseline operacional do hub (25/05/2026)**: `GET /api/system/baseline`, `diagnostics.operational_baseline` e `history.baseline_status` compartilham thresholds únicos para worker, fila, WAL, execuções acima do limite e ownership órfão.
- **Governança do portfólio no overview (26/05/2026)**: `/api/portfolio/health.summary` e `/api/system/overview.portfolio` agora publicam `status`, `top_issue`, `recommended_action` e contagem de itens em incidente/atenção para o painel principal.
- **Preflight governado no cadastro (26/05/2026)**: `POST /api/automations/preflight` agora compara o payload com `automation.manifest.json` quando a pasta já está governada, devolvendo bloqueios de manifesto/docs/smoke antes de `create/update`.
- **Scaffold governado de nova automação (26/05/2026)**: `Tools/New-Automation.ps1` passa a gerar manifesto parametrizado, `queue_group` inicial, runbook com owner/SLA/criticidade básicos e smoke test mínimo em `Orchestrator/tests/`.

## Mudanças Recentes Relevantes

- **Disciplina global de engenharia com IA (22/05/2026)**: adicionada `ai-engineering-discipline` como skill global canônica e obrigatória para alinhar Codex, Gemini CLI e Antigravity. Ver `CHANGELOG.md`.
- **Baseline operacional formalizado (25/05/2026)**: o Orchestrator agora expõe um resumo único `healthy` / `attention` / `incident` em `GET /api/system/baseline`, reaproveitado em `diagnostics`, `history` e no snapshot de qualidade local. Ver `CHANGELOG.md`.
- **Resumo operacional do portfólio (26/05/2026)**: a saúde governada do catálogo passou a ser sintetizada no backend e replicada em `/api/system/overview`, permitindo ao dashboard principal tratar drift, docs pendentes e runtime não reconciliado como risco operacional de primeira classe. Ver `CHANGELOG.md`.
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
