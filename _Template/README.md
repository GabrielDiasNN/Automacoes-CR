# [Nome da Automação]

## 🌟 Visão Geral
[Descreva o objetivo da automação de forma clara e concisa].

## 🏗️ Estrutura e Orquestração
A execução inicia através do script `run.ps1`, em conformidade com o Hub central (`MonitorAutomacoes.ps1`).

- **Frequência:** [Ex: A cada hora, Diário às 07h00]
- **Dependências Externas:** [Banco de Dados, APIs, etc]
- **Manifesto canônico:** `automation.manifest.json`
- **Runbook operacional:** `docs/runbooks/TEMPLATE_SLUG-runbook.md`

## 🛠️ Protocolo V.A.L.E.G. Aplicado
- **Validação:** Validações rigorosas antes da execução e processamento de dados.
- **Arquitetura:** Separação de orquestração (PowerShell) e lógica pesada (Python/Node).
- **Logging:** Uso da biblioteca padronizada de logs.
- **Escala e Governança:** Execução controlada e aderência ao padrão Zero Trust.

---

## 🧠 Gestão de Contexto (AI-Native)
Este arquivo (em conjunto com o `CONTEXT.md`) serve como fundação cognitiva. A seção deve ser atualizada em caso de alterações no comportamento macro da automação.

## Governança mínima
- Preencher `automation.manifest.json` com criticidade, SLA, owner, dependências e smoke tests antes do cadastro no Orchestrator.
- Manter `README.md`, `CONTEXT.md` e runbook sincronizados com o fluxo real da automação.
