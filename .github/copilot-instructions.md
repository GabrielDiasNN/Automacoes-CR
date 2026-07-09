# Copilot Instructions — Automacoes Hub

Você está trabalhando em um repositório de automações operacionais críticas.

## Contexto
- O projeto usa PowerShell como orquestrador principal.
- O monitor central é `MonitorAutomacoes.ps1`.
- As automações entram pelo `run.ps1` de cada dominio e sao coordenadas pela camada `Infrastructure/` e pelo `Orchestrator/`.
- A stack é 100% Nativa (Soberana), tendo migrado processos legados de Excel/VBA para Python/PowerShell.
- Oracle é a principal fonte de dados.
- Outlook COM é usado para e-mail.
- Node.js é usado no bridge de WhatsApp.

## Regras obrigatórias e Governança AI-Native
- **NUNCA use caminhos absolutos** (ex.: `C:\...`). O repositório é 100% dinâmico e portável. Sempre use `.\` ou `$PSScriptRoot`.
- **Zero Trust:** Nenhuma credencial, token ou senha hardcoded é permitida (use `.env`).
- **Python & SQL:** Exija performance O(n), vetorização (Pandas/NumPy) e nunca faça `SELECT *` no Oracle.
- **PowerShell:** Tipagem estrita (`[string]`, `[int]`) e blocos `try/catch` específicos são mandatórios.
- As automações obedecem às 7 skills canônicas presentes em `.github/skills/`.
- O diretório `.gemini/skills/` e apenas um espelho de compatibilidade para Gemini CLI e Antigravity; a fonte de verdade continua sendo `.github/skills/`.
- Preserve compatibilidade com o fluxo atual e nunca faça rewrite total.
- Preserve logs humanos existentes e proteja dados sensíveis (Auto-Masking).

## Prioridades técnicas
1. Timeout e proteção contra travamento.
2. Clareza operacional de erros.
3. Watchdog e observabilidade.
4. Validação de configuração.
5. Governança e rollback simples.

## Estilo de resposta esperado
Sempre responder neste formato:

Objetivo:
[uma frase]

Arquivos:
- [arquivo]
- [arquivo]

Plano:
- [ação]
- [ação]
- [ação]

Riscos:
- [risco]
- [risco]

Validação:
- [comando/check]
- [comando/check]

Rollback:
- [como desfazer]

## O que evitar
- mudanças amplas sem necessidade
- refactor junto com migração grande
- trocar stack inteira
- reintroduzir VBA/Excel
- respostas longas e genéricas

## Antes de concluir qualquer tarefa
- indique os arquivos tocados
- explique o menor teste seguro
- informe impacto operacional
- descreva rollback
