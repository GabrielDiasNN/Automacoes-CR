# Ferramentas de Manutenção (Tools)

Este diretório contém utilitários para garantir a governança, integridade e conformidade da Central de Automações.

## 🛠️ Ferramentas Ativas (Modernas)

### Governança e Testes (CI/CD Local)
- **Test-ZeroTrust.ps1:** Garante que nenhuma senha ou segredo esteja hardcoded.
- **Test-SqlPerformance.ps1:** Bloqueia o uso de `SELECT *` e valida queries.
- **Test-PythonGovernance.ps1:** Valida Type Hints e padrões Python.
- **Test-PowerShellGovernance.ps1:** Valida tipagem estrita em PS.
- **Test-PortablePaths.ps1:** Impede o uso de caminhos absolutos (`C:\...`).
- **Test-SourceEncoding.ps1:** Valida encoding por extensão: `.md/.py/.js/.json/.txt/.sql/.html/.css` em UTF-8 sem BOM e `.ps1/.psm1` em UTF-8 with BOM, com detecção de mojibake em Markdown.
- **Test-PlaywrightEvidence.ps1:** Valida se o padrão, template e evidências Playwright registram URL real, ordem final, console limpo e resultado aprovado.
- **Padrão E2E com Playwright:** A validação final para mudanças de UI/fluxo operacional deve seguir `docs/playwright-e2e-standard.md`.

### Operação e Utilitários
- **New-Automation.ps1:** Scaffold mínimo e atual para criar pasta de automação com `README.md`, `CONTEXT.md`, `run.ps1` e `Logs/`, deixando o cadastro operacional para o Dashboard/API do Orchestrator.
- **Open-LatestLog.ps1:** Atalho rápido para o log da última execução.
- **AplicarPoliticaRetencao.ps1:** Limpeza segura e auditável do workspace com modo `-DryRun`, retenção por idade e bloqueio contra remoção de itens rastreados pelo Git.
- **ValidarAutomacoes.ps1:** Health check completo de todo o hub.

---

## 🧹 Política Atual de Limpeza

- O modo padrão da limpeza é conservador: remove resíduos Python, Playwright, artefatos E2E do Orchestrator, logs/backups expirados e temporários operacionais elegíveis.
- Itens de ambiente local e autenticação são preservados por contrato, incluindo `.env`, `.venv`, `.gemini/` e sessões em `.wwebjs_auth/`.
- Nenhum item rastreado pelo Git pode ser removido pelo script, mesmo que coincida com um padrão de limpeza.
