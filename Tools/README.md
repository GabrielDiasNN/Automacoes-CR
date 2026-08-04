# Ferramentas de Manutenção (Tools)

Este diretório contém utilitários para garantir a governança, integridade e conformidade da Central de Automações.

## 🛠️ Ferramentas Ativas (Modernas)

> **Como ler esta lista:** cada ferramenta declara **quem a invoca**. Isso evita que um script vire
> gate imaginário — só é gate o que `Tools\ValidarAutomacoes.ps1`, `.githooks/pre-commit` ou
> `.github/workflows/governanca.yml` de fato executa.

### Gates estáticos — executados por `ValidarAutomacoes.ps1 -OnlyGovernance`

Rodam no pre-commit (com `-StagedOnly`) e no job `governanca-agregada` do CI. Não exigem servidor,
banco nem rede.

- **Test-ZeroTrust.ps1:** Garante que nenhuma senha ou segredo esteja hardcoded.
- **Test-SqlPerformance.ps1:** Bloqueia o uso de `SELECT *` e valida queries.
- **Test-PythonGovernance.ps1:** Valida Type Hints e padrões Python; bloqueia `pylint: disable=all` em arquivos novos (débito histórico congelado em `pylint-disable-all-baseline.txt`, hoje com 0 bytes — ou seja, nenhum débito técnico "grandfathered" desse tipo existe atualmente no repositório).
- **Test-PowerShellGovernance.ps1:** Valida tipagem estrita em PS.
- **Test-PortablePaths.ps1:** Impede o uso de caminhos absolutos (`C:\...`).
- **Test-SourceEncoding.ps1:** Valida encoding por extensão: `.md/.py/.js/.json/.txt/.sql/.html/.css` em UTF-8 sem BOM e `.ps1/.psm1` em UTF-8 with BOM, com detecção de mojibake em Markdown.
- **Test-PlaywrightEvidence.ps1:** Valida se o padrão, template e evidências Playwright registram URL real, ordem final, console limpo e resultado aprovado.
- **Test-AutomationCatalog.ps1:** Valida `automation.manifest.json`, runbooks, smoke tests e coerência mínima do catálogo governado das automações.
- **Test-ArchitectureStandard.ps1:** Valida o padrão arquitetural descrito em `docs/architecture-standard.md`, usando `Tools/architecture-standard.rules.json` para allowlists versionadas e falhando apenas violações críticas no v1.
- **Test-SkillsGovernance.ps1:** Valida skills canônicas em `.github/skills/`.
- **Test-SemanticGovernance.ps1:** Detecta drift entre documentação viva, catálogo, versão operacional e skills.
- **Test-LogConformidade.ps1 / Test-DateConformidade.ps1:** Guardrails de convenção de datas BR em logs e documentação.
- **Test-JsonConfig.ps1:** Valida sintaxe JSON de configs e arquivos de estado.
- **Test-NodeCommunications.ps1:** Testes offline de comunicações Node.js (sem WhatsApp/internet).
- **Test-DashboardTemplate.ps1:** Valida contrato HTML/CSS do template de dashboard.
- **Test-PowerShellApprovedVerbs.ps1:** Valida verbos aprovados em funções PowerShell.

### Gates do CI — executados apenas por `.github/workflows/governanca.yml`

- **Test-ChangelogUpdated.ps1:** Valida que mudanças em código (`.py`, `.ps1/.psm1/.psd1`, `.js/.mjs/.cjs`, `.sql`) no diff do PR vêm acompanhadas de atualização do `CHANGELOG.md`; permite override com `-AllowSkip` (marcador `[skip-changelog]` no título do PR). Roda no job `governanca-agregada`, somente em pull request.
- **Get-GovernanceTargetSummary.ps1:** Classifica o diff do CI (alvos críticos e de log) para seleção de jobs. Roda no job `preparar-diff`.
- **Fix-MarkdownStyle.ps1:** Lint/correção de estilo Markdown. Roda no job `markdown` com `-DryRun`, apenas quando o diff contém arquivos `.md` (`needs.preparar-diff.outputs.has_md == 'true'`). Fora do CI, pode ser invocada sem `-DryRun` para aplicar as correções.

### Verificações de runtime — **não são gates de commit**

Exigem Orchestrator no ar (e `ORCHESTRATOR_API_KEY` no ambiente). Por isso ficam fora de
`ValidarAutomacoes.ps1`, que precisa rodar offline no pre-commit. Invoque manualmente após subir o
serviço, ou em validação pós-deploy.

- **Test-OrchestratorIntegrity.ps1:** Smoke pós-deploy — processos ativos, API online, contratos operacionais (`diagnostics`/`baseline`/`history`/`portfolio`) e suíte PyTest completa. Referenciado por `docs/operational-improvement-baseline.md`.
- **Test-EncodingResilience.ps1:** Trava de regressão para acentuação PT-BR ponta a ponta (logs, API, DB). Requer `-ApiKey` ou `ORCHESTRATOR_API_KEY` no ambiente; falha imediatamente sem ela.

### Ferramentas manuais de estilo

- **Padrão E2E com Playwright:** A validação final para mudanças de UI/fluxo operacional deve seguir `docs/playwright-e2e-standard.md`.

### Operação e Utilitários
- **New-Automation.ps1:** Scaffold governado para criar pasta de automação com `README.md`, `CONTEXT.md`, `run.ps1`, `automation.manifest.json`, runbook inicial e smoke test mínimo em `Orchestrator/tests/`, com parâmetros para owner, criticidade, fila e dependências básicas.
- **Update-PythonDependency.ps1:** **Caminho canônico para atualizar UMA dependência Python nos lockfiles.** Substitui só o bloco do pacote em `requirements*.txt` com os hashes reais da API do PyPI, preservando a anotação `# via` e os line endings de cada arquivo. **Não use `pip-compile` para isso**: os lockfiles são uma união cross-platform mantida à mão (contêm `uvloop`, só-Linux, *e* `colorama`, só-Windows) e nenhuma execução de `pip-compile` produz os dois — recompilar no Windows perde `uvloop` e quebra o CI, recompilar no Linux perde `colorama` e quebra a instalação local (ambos comprovados empiricamente). Tem `-WhatIf`, falha sem tocar arquivos quando o pacote não está no lock, e imprime o checklist de validação obrigatório. Contexto: issue #16.
- **Open-LatestLog.ps1:** Atalho rápido para o log da última execução.
- **AplicarPoliticaRetencao.ps1:** Limpeza segura e auditável do workspace com modo `-DryRun`, retenção por idade e bloqueio contra remoção de itens rastreados pelo Git.
- **ValidarAutomacoes.ps1:** Health check completo de todo o hub, com resumo de tempo por etapa, modo de seleção governada e opção de exportar um sumário JSON do ciclo local.
- **Audit-DailyStatus.ps1:** Consolida falhas das últimas 24h para análise por IA/humano.
- **Get-QualitySnapshot.ps1:** Snapshot agregado de qualidade do repositório.
- **Review-Code.ps1:** Revisão estática local com relatório de governança.
- **ConfigurarEmailTeste.ps1:** Define/remove o e-mail de redirecionamento do modo de teste.
- **CargarHistoricoBeneficiamento.ps1:** Carga de histórico do Beneficiamento por janela de datas.
- **Get-WhatsAppGroups.ps1:** Lista os grupos da sessão WhatsApp já autenticada e seus IDs (parâmetro `-ClientId`, padrão `hub-global`), para descobrir o ID do grupo destino de uma automação.
- **AtivarModoTeste.bat / DesativarModoTeste.bat:** Ativam/desativam o Modo Teste (sandbox) via API do Orchestrator, globalmente ou para uma automação específica; carregam `ORCHESTRATOR_API_KEY` do `.env` via `Lib-Config.psm1`.
- **Watch-CI.ps1:** Monitora execuções do GitHub Actions em tempo real (`-RunId`, `-Branch`, `-Follow`); autentica via `GH_TOKEN` ou `gh auth login`.
- **Install-Hooks.ps1:** Configura `core.hooksPath=.githooks` na raiz do repositório, garantindo que o hook de pre-commit versionado (governança) seja executado em vez do hook padrão de `.git/hooks`. Idempotente.

---

## 🧹 Política Atual de Limpeza

- O modo padrão da limpeza é conservador: remove resíduos Python, Playwright, artefatos E2E do Orchestrator, logs/backups expirados e temporários operacionais elegíveis.
- A agenda canônica dessa limpeza é o job interno `enterprise_file_cleanup` do Orchestrator; `Tools/AplicarPoliticaRetencao.ps1` não deve ser cadastrado como automação recorrente comum no painel.
- Itens de ambiente local e autenticação são preservados por contrato, incluindo `.env`, `.venv`, `.gemini/` e sessões em `.wwebjs_auth/`.
- Nenhum item rastreado pelo Git pode ser removido pelo script, mesmo que coincida com um padrão de limpeza.
