# Copilot Instructions ??? Automacoes Hub

Voc?? est?? trabalhando em um reposit??rio de automa????es operacionais cr??ticas.

## Contexto
- O projeto usa PowerShell como orquestrador principal.
- O monitor central ?? `MonitorAutomacoes.ps1`.
- Algumas automa????es entram por `TriggerAutomation.vbs` e outras por `run.ps1`.
- A l??gica de neg??cio ainda passa por Excel/VBA + Power Query.
- Oracle ?? a principal fonte de dados.
- Outlook COM ?? usado para e-mail.
- Node.js ?? usado no bridge de WhatsApp.

## Regras obrigat??rias e Governan??a AI-Native
- **NUNCA use caminhos absolutos** (`.\...`). O reposit??rio ?? 100% din??mico e port??vel. Sempre use `.\` ou `$PSScriptRoot`.
- **Zero Trust:** Nenhuma credencial, token ou senha hardcoded ?? permitida (use `.env`).
- **Python & SQL:** Exija performance O(n), vetoriza????o (Pandas/NumPy) e nunca fa??a `SELECT *` no Oracle.
- **PowerShell:** Tipagem estrita (`[string]`, `[int]`) e blocos `try/catch` espec??ficos s??o mandat??rios.
- As automa????es obedecem ??s 8 SKILLs can??nicas presentes em `.github/skills/`.
- Preserve compatibilidade com o fluxo atual e nunca fa??a rewrite total.
- Preserve logs humanos existentes e proteja dados sens??veis (Auto-Masking).

## Prioridades t??cnicas
1. Timeout e prote????o contra travamento.
2. Clareza operacional de erros.
3. Watchdog e observabilidade.
4. Valida????o de configura????o.
5. Governan??a e rollback simples.

## Estilo de resposta esperado
Sempre responder neste formato:

Objetivo:
[uma frase]

Arquivos:
- [arquivo]
- [arquivo]

Plano:
- [a????o]
- [a????o]
- [a????o]

Riscos:
- [risco]
- [risco]

Valida????o:
- [comando/check]
- [comando/check]

Rollback:
- [como desfazer]

## O que evitar
- mudan??as amplas sem necessidade
- refactor junto com migra????o grande
- trocar stack inteira
- remover VBA/Excel de uma vez
- respostas longas e gen??ricas

## Antes de concluir qualquer tarefa
- indique os arquivos tocados
- explique o menor teste seguro
- informe impacto operacional
- descreva rollback
