---
name: automation-runtime-safety
description: Use when enforcing Zero Trust, structured logging, secret handling, encoding safety, portable paths, and runtime failure policies across PowerShell, Python, Node.js, Orchestrator, and automation entrypoints.
---

## Purpose
Centralizar os guardrails operacionais do hub: segredos, logs, severidade, encoding, portabilidade e tratamento de falhas recuperaveis versus terminais.

## When to Use
- Use ao alterar qualquer fluxo que leia `.env`, manipule credenciais ou interaja com APIs, banco ou canais de notificacao.
- Use ao criar ou revisar logs em `lib/`, `Infrastructure/`, `Orchestrator/` ou nas pastas de automacao.
- Use ao ajustar rotinas que escrevem arquivos, trafegam texto PT-BR ou transitam mensagens entre PowerShell, Python e Node.js.
- Use ao definir politica de erro, retry, supressao de envio ou degradacao segura.

## Do Not Use When
- Nao use para decidir topologia de orquestracao, `ExecId` ou idempotencia ponta a ponta; nesses casos use `enterprise-orchestration-contract`.
- Nao use para padroes de sintaxe PowerShell ou modularizacao `.psm1`; nesses casos use `powershell-automation-monitor`.
- Nao use para detalhes de layout HTML/CSS ou componentes de dashboard; nesses casos use `html-css-enterprise-standard`.

## Related Skills
- `enterprise-orchestration-contract` para propagar `ExecId` e regras de estado.
- `powershell-automation-monitor` para aplicar esses guardrails em scripts e modulos PowerShell.
- `nodejs-communications` quando o canal de risco for WhatsApp/headless/bootstrap.

## Non-Negotiable Rules
- Nunca hardcode segredos, tokens, senhas, API keys ou credenciais; use `.env` ou variaveis de ambiente do processo.
- Todo log operacional relevante deve ser correlacionavel por `ExecId` quando fizer parte de um fluxo executado.
- Diferencie severidade no minimo em `INFO`, `WARN` e `ERROR`; nao esconda falha operacional em mensagem neutra.
- Classifique como recuperavel apenas erros que podem ser repetidos sem corromper estado; falhas que geram risco de duplicidade, perda de rastreabilidade ou vazamento devem ser tratadas como terminais.
- Preserve o contrato de encoding do workspace: `.ps1` e `.psm1` em UTF-8 com BOM; `.py`, `.json`, `.md`, `.sql` e demais textos em UTF-8 sem BOM, conforme `GEMINI.md`.

## Repo-Specific Constraints
- Use `.env` como fonte primaria de configuracao sensivel; `lib/Lib-Config.psm1` e os scripts Python devem consumir esse contexto sem duplicar segredo em codigo.
- Nao introduza caminhos absolutos; os checks de portabilidade bloqueiam dependencias de `C:\` ou `D:\`.
- Mantenha logs compativeis com os guardrails de `lib/Lib-Logging.psm1`, `Logs/` e `Orchestrator/Logs/`.
- Considere `Tools/Test-ZeroTrust.ps1`, `Tools/Test-PortablePaths.ps1`, `Tools/Test-LogConformidade.ps1` e `Tools/Test-EncodingResilience.ps1` como contrato vivo do repositorio.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-ZeroTrust.ps1 -RootPath .`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PortablePaths.ps1 -RootPath .`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-LogConformidade.ps1 -RootPath . -All`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-EncodingResilience.ps1` quando a mudanca afetar round-trip de texto, API ou escrita de log.

## Troubleshooting
- Se o check de Zero Trust falhar, procure primeiro atribuicoes literais de `password`, `token`, `secret` ou `api_key`.
- Se a portabilidade falhar, substitua caminhos absolutos por `$PSScriptRoot`, caminhos relativos ou funcoes de configuracao.
- Se houver corrupcao de acentuacao, valide o encoding gravado e confira as regras de `GEMINI.md` antes de inspecionar a logica de negocio.
- Se logs ficarem dificeis de correlacionar, confirme que o `ExecId` esta sendo recebido e propagado antes de escrever a linha.

## Pre-Delivery Checklist
- Confirme que nenhum segredo foi introduzido em codigo ou JSON versionado.
- Confirme que logs relevantes possuem severidade clara e contexto suficiente para auditoria.
- Confirme que o encoding final do arquivo alterado respeita `GEMINI.md`.
- Confirme que erros recuperaveis e terminais foram diferenciados de forma defensavel.
