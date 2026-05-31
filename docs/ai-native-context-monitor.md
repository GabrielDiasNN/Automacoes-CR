# Monitor de Contexto AI-Native

Este arquivo é o snapshot curado para bootstrap de agentes no Hub de Automações. Ele não substitui o `CHANGELOG.md`; resume apenas o estado operacional e os marcos recentes que afetam decisões futuras.

## Estado Atual

- **Versão operacional de referência**: Hub em linha `v9.3.6`, com Orchestrator/Dashboard operando sobre baseline Alembic, governança semântica, testes offline de Node/WhatsApp, cobertura ampliada de runtime e o Agente de Revisão de Código declarativo estruturado ativo.
- **Stack ativa**: Python/FastAPI, PowerShell corporativo, Node.js para comunicações, Dashboard SPA estático e SQLite em WAL com Alembic.
- **Skills do workspace**: `.github/skills/` é a fonte canônica; `.gemini/skills/` é apenas mirror por junction/symlink.
- **Skills globais obrigatórias**: `ai-engineering-discipline`, `protocolo-valeg` e `git-ide-governance-skill`.
- **Contratos críticos**: Zero Trust, encoding governado, documentação viva, validação de skills, governança de catálogo de automações, Playwright como última validação para UI/front-back, conformidade estrita de datas DD/MM/YYYY e o novo Agente de Revisão de Código declarativo estruturado (`.agents/agents/code-review-agent/agent.json` e `Tools/Review-Code.ps1`).
- **Validação de referência mais recente**: em 27/05/2026, a governança passou a usar classificação compartilhada de diff entre `pre-commit` e GitHub Actions, adicionou validação semântica de versões/catálogo/dependências e passou a executar teste offline de Node/WhatsApp no quality gate.
- **Catálogo governado do hub (24/05/2026)**: automações ativas agora carregam `automation.manifest.json` versionado, com criticidade, SLA, dependências, smoke tests e vínculo para runbook. O dashboard consome `/api/portfolio/health` para expor esse cruzamento operacional.
- **Baseline operacional do hub (25/05/2026)**: `GET /api/system/baseline`, `diagnostics.operational_baseline` e `history.baseline_status` compartilham thresholds únicos para worker, fila, WAL, execuções acima do limite e ownership órfão.
- **Governança do portfólio no overview (26/05/2026)**: `/api/portfolio/health.summary` e `/api/system/overview.portfolio` agora publicam `status`, `top_issue`, `recommended_action` e contagem de itens em incidente/atenção para o painel principal.
- **Preflight governado no cadastro (26/05/2026)**: `POST /api/automations/preflight` agora compara o payload com `automation.manifest.json` quando a pasta já está governada, devolvendo bloqueios de manifesto/docs/smoke antes de `create/update`.
- **Cockpit PCP & OEE Têxtil (31/05/2026)**: A aba beneficiamento agora é um cockpit completo de PCP e eficiência OEE alimentado diretamente pela base SQLite histórica indexada (81.354 registros reais de 2026), com filtros de data operacionais e rastreabilidade na timeline de fases. Painéis técnicos de Data Ops ("Qualidade do Dado" e "Perfil de Dados") foram totalmente removidos para despoluição visual.
- **Análise Dinâmica de Produtos e Filtros Cruzados (31/05/2026)**: introduzida barra de filtros cruzados avançados (busca, máquina, fase, turno) que atualiza instantaneamente KPIs vivos e rankings, acompanhada por tabela dinâmica de produtos e painel lateral de top artigos/cores, amparada por agregação compacta `fato_producao` no backend para máximo desempenho.

## Mudanças Recentes Relevantes

- **Cockpit PCP & OEE Têxtil com SQLite Histórico (31/05/2026)**: Evolução completa da aba de beneficiamento para controle de PCP e eficiência OEE sobre os 81.354 registros reais de 2026. Criada a rota FastAPI `GET /api/beneficiamento/historico/analytics` agregando KPIs complexos de OEE, reprocesso %, desvio de setup e turnos em milissegundos. No frontend, adicionado seletor de range de data, 8 KPIs premium unificados, gráficos ApexCharts de OEE, setup stacked e turnos, além do ranking pódio de operadores de chão de fábrica. Painéis de Data Ops foram completamente eliminados. Homologado 100% verde nos 168 testes do Pytest e quality gate.
- **Análise Dinâmica de Produtos e Filtros Cruzados (31/05/2026)**: a aba beneficiamento agora suporta filtros cruzados interativos em tempo real na tela, tabela dinâmica de produtos, painel de top artigos/cores, e recálculo dinâmico de KPIs vivos e rankings, com dados pré-agregados no backend (fato_producao), 100% homologado via testes E2E Playwright.
- **Refatoração Premium do Beneficiamento (31/05/2026)**: a aba beneficiamento foi atualizada para um design sofisticado e altamente interativo com 8 KPIs unificados, animação de contagem pt-BR, pódio com medalhas/barras de progresso nas tabelas, e accordions colapsáveis de qualidade e profiling de snapshots no final, 100% validado por testes Playwright E2E e verificador de encoding.
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
