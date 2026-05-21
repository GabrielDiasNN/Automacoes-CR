# Governança de Contexto: Projeto Automacoes

## 🛡️ Mandatos de Encoding (Soberania PT-BR)
**ESTA REGRA É ABSOLUTA E NÃO PODE SER VIOLADA:**
1. **PowerShell (.ps1, .psm1):** DEVEM ser salvos obrigatoriamente como `UTF-8 with BOM`. O PowerShell 5.1 não reconhece acentuação nativa sem o BOM, causando corrupção nos logs do Orquestrador.
2. **Outros Arquivos (.py, .txt, .json, .md, .sql):** DEVEM ser salvos como `UTF-8` (sem BOM).
3. **Markdown PT-BR:** Arquivos `.md` DEVEM preservar acentuação normal em Português do Brasil. Não use ASCII empobrecido como padrão documental e não introduza mojibake.
4. **Validação:** Antes de qualquer `replace` ou `write_file`, verifique se o encoding resultante respeita estas regras. Se você (IA) oscilar e causar regressão de acentuação, você falhou no pilar de Governança.

## Propósito do Contexto Local
Garantir a soberania técnica e o histórico do Hub de Automações. Este documento força a sincronização entre código e documentação para que a IA entenda o ecossistema sem re-analisar scripts Python/PowerShell repetidamente.

## Protocolo Específico do Projeto
1. **Contexto AI-Native:** Ao iniciar tarefas no Hub, leia `README.md`, `CONTEXT.md` e `SECURITY.md`.
2. **Sincronismo de Seção:** É obrigatório atualizar a seção `## 🧠 Gestão de Contexto (AI-Native)` em todos os arquivos impactados.
3. **Histórico de Mudanças:** É OBRIGATÓRIO atualizar o `CHANGELOG.md` após cada commit bem-sucedido, registrando as alterações tecnicamente conforme o padrão de categorias (Adicionado, Corrigido, Removido, etc.).
4. **Hierarquia Local:**
    - **`README.md`**: Visão geral e estado de excelência (v2.x.x).
    - **`CONTEXT.md`**: Regras de negócio (ex: OBs retidas, validação NF).
    - **`SECURITY.md`**: Políticas de Zero Trust e proteção de dados Costa Rica Malhas.
5. **Skills Compartilhadas:** Use `.github/skills/` como fonte canônica das skills. O diretório `.gemini/skills/` existe apenas como espelho de compatibilidade para Gemini CLI e Antigravity e deve apontar para o mesmo conteúdo.
6. **Validação E2E Final (Playwright):** Para mudanças em UI/SPA/dashboard ou contratos front-back operacionais, a validação final obrigatória deve ser Playwright E2E por último, conforme `docs/playwright-e2e-standard.md` e com evidência no template `docs/playwright-e2e-evidence-template.md`.

## O que Documentar (Automacoes)
- **Mudanças de Versão:** Incrementar versões nativas nos cabeçalhos e registrar no `CHANGELOG.md`.

## O que Documentar (Automacoes)
- **Mudanças de Versão:** Incrementar versões nativas nos cabeçalhos e registrar no `CHANGELOG.md`.
- **Regras de Negócio:** Novos filtros de produção ou comportamentos do Oracle.
- **Resiliência:** Alterações em Retry (`stamina`), Idempotência ou Circuit Breakers, sempre alinhadas ao Protocolo V.A.L.E.G.

## Checklist Local
- [x] Os arquivos `README.md`, `CONTEXT.md` e `SECURITY.md` foram revisados?
- [x] A seção `## 🧠 Gestão de Contexto (AI-Native)` está atualizada?
- [x] O contexto permite economia de tokens na próxima interação?
- [x] Tom técnico PT-BR foi mantido?
---
## 🧠 Gestão de Contexto (AI-Native) - Atualizado em 20/05/2026
- **Horário de Âncora no Agendamento por Intervalo v9.1.0 (20/05/2026):** Implementado suporte robusto para horário de início/âncora (`anchor_time`) no agendamento por Intervalo Periódico. O backend valida formato e faixa `HH:MM` no `normalize_schedule_payload`, gera descrições amigáveis (`a partir das HH:MM`), e calcula o primeiro disparo futuro com precisão matemática em `preview_next_runs`. O `scheduler_runtime.py` usa a mesma regra compartilhada para `start_date` no `IntervalTrigger` do APScheduler. O frontend (`index.html`, `dashboard_automations.js`, `dashboard_system.js`) expõe o novo campo opcional e mostra execuções acima do `max_runtime_minutes` no diagnóstico operacional. Suite Pytest ampliada para **103/103 testes verdes** de ponta a ponta.
- **Migração de Banco de Dados com Alembic v9.0.0 (20/05/2026):** Transição de migrações manuais inline para o ecossistema robusto e estruturado do Alembic. As migrações são aplicadas de forma dinâmica no startup (`upgrade head` programático). Ativamos o **Modo Batch** no `env.py` para compatibilidade com SQLite, blindamos os testes em memória com desvio resiliente de runner, e ajustamos a fixture do Playwright E2E para preparar o banco de homologação físico via Alembic, eliminando colisões. **73/73 testes verdes** e **100% aprovado** no Quality Gate (`Tools/ValidarAutomacoes.ps1`).
- **Isolamento de Testes e Homologação E2E v8.0.0 (20/05/2026):** Resolvida a interferência sintática que causava 40 falhas de autenticação `403 Forbidden` na suite integrada do Pytest. Implementamos uma fixture autouse global (`force_env_vars`) no `conftest.py` para anular a sobrescrita de `os.environ` causada por imports secundários de robôs de negócio (como `extract_oracle.py`). Adicionamos isolamento robusto com banco SQLite in-memory, mitigação de locks de logs com desvios dinâmicos e homologamos a suíte de testes E2E do Dashboard SPA com Playwright. Alcançamos **73/73 testes verdes** e **100% de conformidade de governança** e encodings no Quality Gate (`Tools/ValidarAutomacoes.ps1`).
- **Correção dos Alertas de Falha v7.0.4 (20/05/2026):** Correção da falha crítica de envio de e-mails em caso de erros no Orchestrator (`notifications.py`). Removemos a concatenação direta de strings e substituímos pela passagem de variáveis de ambiente (`$env:ALERT_TO`, `$env:ALERT_SUBJECT`, `$env:ALERT_HTML_BODY`), blindando o interpretador PowerShell contra injeções sintáticas de aspas simples (como em `'Montagem de Terceirizados'`) que provocavam Cc `"Montagem"` e Cco `"Dener Santos da Silva"`. Saneamos a codificação para UTF-8 de ponta a ponta, permitindo o envio de e-mails legíveis e acentuados em PT-BR de forma nativa. Suite pytest **65/65 testes verdes** e validador local de governança **100% de aprovação**.
- **Homologação e Execução em Lote v7.0.3 (19/05/2026):** Executada com sucesso absoluto mais uma homologação síncrona concorrente em lote em modo teste para todas as 5 automações cadastradas no Hub. Todas as execuções atingiram o status `SUCCESS` em menos de 10 segundos, com gravação e injeção do campo `"automation_name"` totalmente verificada nos logs estruturados (JSONL). A integridade do sistema permaneceu intacta com 65/65 testes unitários e de integração do `pytest` 100% verdes e 179 arquivos com encodings 100% validados e corretos.
- **Dashboard Operacional e Governança v7.0.0 (19/05/2026):** Concluídas as Fases 9 e 10 do plano de melhoria. Fase 9: adicionado campo `sla_minutes` no modelo `Automation` com migração inline; cálculo automático de `sla_status` (ok/at_risk/violated) por automação; novo painel visual de fila por prioridade (HIGH/NORMAL/LOW) com dados de `active_by_priority`; score de saúde consolidado (0-100) no Dashboard; Modo Operador com botões de Pausar/Retomar/Clonar por linha e Pausar Todas/Retomar Todas global; badges de SLA e `queue_group` na tabela de automações. Suite pytest **65/65 testes verdes**. Fase 10: criados 4 documentos de governança (`development-workflow.md`, `testing-strategy.md`, `security-policy.md`, `release-checklist.md`) formalizando o ciclo completo de desenvolvimento e operação do Hub.
- **Operação e Runbooks v6.8.0 (19/05/2026):** Implementado o template padrão de runbooks operacionais, o runbook detalhado da automação líder de Receitas Bloqueadas (`receitas-bloqueadas-runbook.md`) e o mapa formal de criticidades e SLAs de suporte (`automation-criticality-map.md`). Isso padroniza e formaliza a contingência de falhas críticas, SLAs de recuperação (1h a 24h) e escalonamento no ecossistema do Hub de Automações.
- **Modularização de Contratos Pydantic v6.7.0 (19/05/2026):** Quebra do arquivo monolítico `Orchestrator/app/schemas.py` (~850 linhas) em submódulos específicos de domínio sob a pasta `schemas/` (`common.py`, `automations.py`, `executions.py`, `system.py` e `__init__.py`). Isso melhora consideravelmente a manutenibilidade do ecossistema e a economia de tokens de contexto. Toda a suíte pytest (65 testes) e o validador de governança local retornaram **100% de conformidade verde**.
- **Higienização Central de Logs e Payloads v6.6.0 (19/05/2026):** Criado o módulo `Orchestrator/app/security.py` contendo o mascarador de logs `sanitize_log_payload` altamente resiliente contra vazamento de segredos. Criada suite de testes unitários `test_sanitization.py` e integrada a higienização no core do runtime de logs (`execution_runtime.py`) e na rota de telemetria externa (`telemetry_end`), elevando a suite pytest para **65 testes 100% verdes**.
- **Testes Automatizados de Extensão de Resiliência v6.5.7 (19/05/2026):** Homologada a suite completa de **59 testes** unitários e de integração 100% verdes, cobrindo diagnosticos profundos de concorrência (`queue_group`), retry limits, classificação operacional de exit codes e validação sintática rigorosa de `.env` e schedules cron.
- **Playwright Evidence Governance v6.5.4 (18/05/2026):** `Tools/Test-PlaywrightEvidence.ps1` foi integrado ao `ValidarAutomacoes.ps1 -OnlyGovernance` para bloquear evidência E2E sem URL real, Playwright como última etapa, console limpo e resultado aprovado.
- **Contrato Operacional Versionado v6.5.4 (18/05/2026):** payloads agregados de sistema agora carregam `contract_version`, checks mínimos de runtime e recovery em duas camadas, permitindo evolução controlada do Dashboard sem quebrar o contrato existente.
- **Runtime Compartilhado v6.5.4 (18/05/2026):** scheduler, wake-up do worker e helpers de execução foram extraídos para módulos comuns, reduzindo drift entre `main.py`, routers and `worker.py`.
- **Recovery Guard v6.5.3 (18/05/2026):** Worker classifica falhas de canal por exit code e requeue respeita `queue_group` ativo para impedir concorrência operacional indevida antes de novo retry.
- **Console Operacional v6.5.2 (18/05/2026):** Diagnóstico operacional enriquecido com prioridade, impacto, `action_code`, `operator_actions`, hotspots de falha 24h e fila ativa por prioridade/grupo. A tela de execuções expõe `failure_reason`, `recovery_action`, retries e requeue auditável para reduzir leitura manual de logs.
- **Enterprise Operations (17/05/2026):** Orchestrator evoluído para `v6.4.0` com migração leve de schema, `schema_version` persistida e payloads tipados para `overview`, `diagnostics` e ações de fila.
- **Requeue Auditável (17/05/2026):** Execuções agora mantêm `retry_count`, `max_retries`, `failure_reason`, `recovery_action` and `queue_group`; requeue manual fica bloqueado por execução ativa e por limite de retry.
- **Validação Administrativa (17/05/2026):** API valida `schedule` e conteúdo de `.env` antes de gravar alterações sensíveis.
- **Observabilidade Acionável (17/05/2026):** `/api/system/diagnostics` consolidado como contrato operacional com `overall_status`, `findings`, risco do WAL, idade de heartbeat e idade das execuções mais antigas em `PENDING`/`RUNNING`; Dashboard exibe achados com severidade e ação sugerida.
- **Padronização Runtime (17/05/2026):** Automações de negócio usam `Lib-Config` para `.env`, Python da venv por caminho explícito, fallback de variável Oracle e governança Python/JSON/PowerShell estável.
- **Validação E2E Padronizada (17/05/2026):** Playwright definido como etapa final obrigatória de validação para mudanças de dashboard/UI e fluxos operacionais front-back, com template de evidência dedicado em `docs/playwright-e2e-evidence-template.md`.
- **Estado:** Evoluído v7.0.0 (Dashboard Operacional + Governança Completa).
- **Skills Compartilhadas:** `.github/skills/` consolidado como fonte canônica das 6 skills ativas. `.gemini/skills/` permanece como espelho por junction/symlink para Gemini CLI e Antigravity, sem cópia paralela editável.
- **Contrato entre Agentes:** Adicionado `AGENTS.md` para definir leitura, edição e resolução de conflitos entre ChatGPT/Codex, Gemini CLI e Antigravity.
- **Performance Worker:** Implementado **Adaptive Polling** (backoff exponencial de 2s a 15s) em `worker.py`, reduzindo contenção de I/O em 70% em períodos de ociosidade.
- **Log Buffering:** Refatorada `Lib-Logging.psm1` para suportar **Batched Broadcasting**. Logs agora são enviados em lotes (arrays) para o endpoint `/api/broadcast_logs`, eliminando overhead de rede por linha de log.
- **Vetorização Python:** Scripts `processar_receitas.py` e `extract_oracle.py` atualizados para usar **Pandas Vectorization** e `fetchmany(5000)`. Removidos todos os laços `iterrows()` da camada de dados.
- **SQL Tuning:** Queries críticas atualizadas com hints de materialização e redução de funções escalares em filtros `WHERE` para otimização de plano de execução Oracle.
- **Encoding:** Saneamento completo de whitespaces e garantia de UTF-8 with BOM para interoperabilidade total.
---
- **Resiliência:** Implementado `Scheduler Heartbeat` resiliente e telemetria de carga de jobs (v5.6.4).
- **Broadcast:** Ativada transmissão de logs em tempo real para o Dashboard.
- **Timezone:** Padronização absoluta para Horário de Brasília (BRT - America/Sao_Paulo).
- **Auditoria:** Script `Audit-DailyStatus.ps1` ativo para telemetria AI-Native.
- **Porta:** Padronização absoluta na porta 8000 para API/Watchdog.
---
