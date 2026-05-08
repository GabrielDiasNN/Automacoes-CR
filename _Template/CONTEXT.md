# Cognitive Context: [Nome da Automação]

## Repository Philosophy
Esta automação faz parte do ecossistema AI-Native e opera sob o Protocolo V.A.L.E.G. (Validação, Arquitetura, Logging, Escala e Governança).

## System Architecture
- **Orquestração:** `run.ps1` gerencia a execução e invoca as lógicas de negócio.
- **Lógica de Negócio:** [Python / Powershell / JS]
- **Integração:** [Oracle / WhatsApp / Outlook / etc]

## Security & Resilience (Zero Trust)
- Credenciais lidas estritamente de variáveis de ambiente (`.env`).
- Tolerância a falhas via blocos `try/catch/finally` em `run.ps1`.
- Cleanup garantido para arquivos temporários e conexões.

---

## 🧠 Gestão de Contexto (AI-Native)
- **Obrigação:** Mantenha este documento atualizado a cada mudança de arquitetura ou regra de negócio.
- **Objetivo:** Fornecer o mapa mental e limites operacionais para a IA atuar com soberania.
