# [Nome da Automação]

## 🌟 Visão Geral
[Descreva o objetivo da automação de forma clara e concisa].

## 🏗️ Estrutura e Orquestração
A execução inicia pelo shim `run.ps1`, que resolve o Python do projeto e chama o runner Python da pasta (`run_<id>.py`). O runner usa `lib/python/hub_runner.py` para pre-flight, lock global, telemetria, etapas, retry e exit code, em conformidade com o Hub central (`MonitorAutomacoes.ps1`).

- **Frequência:** [Ex: A cada hora, Diário às 07h00]
- **Dependências Externas:** [Banco de Dados, APIs, etc]
- **Manifesto canônico:** `automation.manifest.json`
- **Runbook operacional:** `docs/runbooks/TEMPLATE_SLUG-runbook.md`

## 🛠️ Protocolo V.A.L.E.G. Aplicado
- **Validação:** Validações rigorosas antes da execução e processamento de dados.
- **Arquitetura:** Shim PowerShell (`run.ps1`) e runner Python (`run_<id>.py`), com a lógica de negócio nas etapas do runner.
- **Logging:** Uso da biblioteca padronizada de logs.
- **Escala e Governança:** Execução controlada e aderência ao padrão Zero Trust.

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo (em conjunto com o `CONTEXT.md`) serve como fundação cognitiva. A seção deve ser atualizada em caso de alterações no comportamento macro da automação.

## Governança mínima
- Preencher `automation.manifest.json` com criticidade, SLA, owner, dependências e smoke tests antes do cadastro no Orchestrator.
- Manter `README.md`, `CONTEXT.md` e runbook sincronizados com o fluxo real da automação.
