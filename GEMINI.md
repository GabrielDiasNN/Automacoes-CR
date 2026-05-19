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
- **Regras de Negócio:** Novos filtros de produção ou comportamentos do Oracle.
- **Resiliência:** Alterações em Retry (`stamina`), Idempotência ou Circuit Breakers, sempre alinhadas ao Protocolo V.A.L.E.G.

## Checklist Local
- [x] Os arquivos `README.md`, `CONTEXT.md` e `SECURITY.md` foram revisados?
- [x] A seção `## 🧠 Gestão de Contexto (AI-Native)` está atualizada?
- [x] O contexto permite economia de tokens na próxima interação?
- [x] Tom técnico PT-BR foi mantido?
---
## 🧠 Gestão de Contexto (AI-Native) - Atualizado em 19/05/2026
- **Testes Automatizados de Extensão de Resiliência v6.5.7 (19/05/2026):** Homologada a suite completa de **59 testes** unitários e de integração 100% verdes, cobrindo diagnosticos profundos de concorrência (`queue_group`), retry limits, classificação operacional de exit codes e validação sintática rigorosa de `.env` e schedules cron.
- **Playwright Evidence Governance v6.5.4 (18/05/2026):** `Tools/Test-PlaywrightEvidence.ps1` foi integrado ao `ValidarAutomacoes.ps1 -OnlyGovernance` para bloquear evidência E2E sem URL real, Playwright como última etapa, console limpo e resultado aprovado.
- **Contrato Operacional Versionado v6.5.4 (18/05/2026):** payloads agregados de sistema agora carregam `contract_version`, checks mínimos de runtime e recovery em duas camadas, permitindo evolução controlada do Dashboard sem quebrar o contrato existente.
- **Runtime Compartilhado v6.5.4 (18/05/2026):** scheduler, wake-up do worker e helpers de execução foram extraídos para módulos comuns, reduzindo drift entre `main.py`, routers e `worker.py`.
- **Recovery Guard v6.5.3 (18/05/2026):** Worker classifica falhas de canal por exit code e requeue respeita `queue_group` ativo para impedir concorrência operacional indevida antes de novo retry.
- **Console Operacional v6.5.2 (18/05/2026):** Diagnóstico operacional enriquecido com prioridade, impacto, `action_code`, `operator_actions`, hotspots de falha 24h e fila ativa por prioridade/grupo. A tela de execuções expõe `failure_reason`, `recovery_action`, retries e requeue auditável para reduzir leitura manual de logs.
- **Enterprise Operations (17/05/2026):** Orchestrator evoluído para `v6.4.0` com migração leve de schema, `schema_version` persistida e payloads tipados para `overview`, `diagnostics` e ações de fila.
- **Requeue Auditável (17/05/2026):** Execuções agora mantêm `retry_count`, `max_retries`, `failure_reason`, `recovery_action` e `queue_group`; requeue manual fica bloqueado por execução ativa e por limite de retry.
- **Validação Administrativa (17/05/2026):** API valida `schedule` e conteúdo de `.env` antes de gravar alterações sensíveis.
- **Observabilidade Acionável (17/05/2026):** `/api/system/diagnostics` consolidado como contrato operacional com `overall_status`, `findings`, risco do WAL, idade de heartbeat e idade das execuções mais antigas em `PENDING`/`RUNNING`; Dashboard exibe achados com severidade e ação sugerida.
- **Padronização Runtime (17/05/2026):** Automações de negócio usam `Lib-Config` para `.env`, Python da venv por caminho explícito, fallback de variável Oracle e governança Python/JSON/PowerShell estável.
- **Validação E2E Padronizada (17/05/2026):** Playwright definido como etapa final obrigatória de validação para mudanças de dashboard/UI e fluxos operacionais front-back, com template de evidência dedicado em `docs/playwright-e2e-evidence-template.md`.
- **Estado:** Evoluído v6.3.2 (Enterprise Observability).
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
