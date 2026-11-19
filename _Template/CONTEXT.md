# Cognitive Context: [Nome da Automação]

## Repository Philosophy

Esta automação faz parte do ecossistema AI-Native e opera sob o Protocolo V.A.L.E.G. (Validação, Arquitetura, Logging, Escala e Governança).

## System Architecture

- **Entrypoint:** `run.ps1` é só o shim: resolve o Python do projeto, chama o runner e repassa o exit code.
- **Orquestração:** `TEMPLATE_RUNNER` (runner Python sobre `lib/python/hub_runner.py`) faz pre-flight, lock, telemetria, etapas, entrega e commit do estado.
- **Lógica de Negócio:** [Python / Powershell / JS]
- **Integração:** [Oracle / WhatsApp / Outlook / etc]
- **Catálogo canônico:** `automation.manifest.json`
- **Runbook:** `docs/runbooks/TEMPLATE_SLUG-runbook.md`

## Security & Resilience (Zero Trust)

- Credenciais lidas estritamente de variáveis de ambiente (`.env`).
- Tolerância a falhas no runner Python: a falha crítica fecha a execução com exit 4 e o lock é liberado pelo `with` do `hub_runner`.
- Cleanup garantido para arquivos temporários e conexões.

---

## 🧠 Gestão de Contexto (AI-Native)

- **Obrigação:** Mantenha este documento atualizado a cada mudança de arquitetura ou regra de negócio.
- **Objetivo:** Fornecer o mapa mental e limites operacionais para a IA atuar com soberania.
- **Governança:** O manifesto, o README e o runbook devem refletir o mesmo entrypoint, as mesmas dependências e o mesmo SLA operacional.
