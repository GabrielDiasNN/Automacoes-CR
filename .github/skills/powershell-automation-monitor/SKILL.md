---
name: powershell-automation-monitor
description: Use when developing or reviewing PowerShell entrypoints, infrastructure scripts, monitors, and shared modules that must conform to the repository's corporate runtime and governance rules.
---

## Purpose
Padronizar como PowerShell e usado no hub para entrypoints, infraestrutura, monitoramento e modulos compartilhados, preservando compatibilidade corporativa, legibilidade e governanca automatizada.

## When to Use
- Use ao alterar scripts em `Infrastructure/`, `Tools/`, `lib/*.psm1` ou `run.ps1` das automacoes.
- Use ao decidir se uma logica deve viver em um script `.ps1` ou em um modulo `.psm1`.
- Use ao revisar parametros, tipagem, `CmdletBinding`, tratamento de excecoes e organizacao do codigo PowerShell.

## Do Not Use When
- Nao use para decidir regras de `ExecId`, idempotencia ou ownership de estado entre runtimes; nesses casos use `enterprise-orchestration-contract`.
- Nao use para politicas de segredo, encoding ou logs; nesses casos use `automation-runtime-safety`.
- Nao use para canais Node.js ou contratos visuais de HTML/CSS; esses dominios possuem skills proprias.

## Related Skills
- `enterprise-orchestration-contract` para o papel do script dentro do fluxo corporativo.
- `automation-runtime-safety` para seguranca, logs e falhas.
- `ai-native-development-standard` quando o script exigir atualizacao de documentacao ou governanca de contexto.

## Non-Negotiable Rules
- Use `[CmdletBinding()]` e bloco `param(...)` em scripts operacionais com interface publica.
- Declare tipos explicitos para parametros relevantes e inicialize `ErrorActionPreference = "Stop"` quando o fluxo exigir falha controlada.
- Use `.ps1` para entrypoints e operacoes executaveis; use `.psm1` para logica reutilizavel compartilhada em `lib/`.
- Em fronteiras operacionais com IO, processos, API, banco ou arquivos, prefira `try/catch/finally` defensavel; nao deixe erro escapar de forma opaca.
- Preserve compatibilidade com PowerShell 5.1 quando o script fizer parte do runtime corporativo ou for consumido pela esteira atual.

## Repo-Specific Constraints
- Considere `lib/Lib-Config.psm1`, `lib/Lib-Logging.psm1`, `lib/Lib-Process.psm1` e `lib/Lib-Retry.psm1` como modulos compartilhados preferenciais antes de duplicar funcoes.
- Trate `Infrastructure/MonitorAutomacoes.ps1`, `Infrastructure/Start-Orchestrator.ps1` e `Tools/ValidarAutomacoes.ps1` como referencias de scripts corporativos de controle.
- Mantenha approved verbs e estrutura de modulo compativeis com `Tools/Test-PowerShellApprovedVerbs.ps1`.
- Ao alterar governanca de skills em PowerShell, preserve compatibilidade com `Tools/Test-SkillsGovernance.ps1`.

## Validation
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PowerShellGovernance.ps1 -RootPath .`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PowerShellApprovedVerbs.ps1 -RootPath .`.
- Rode `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` quando a mudanca afetar scripts de governanca ou infraestrutura.

## Troubleshooting
- Se o validador acusar `catch` generico, refine a captura para uma excecao ou familia de excecoes defensavel.
- Se um script crescer demais ou for reutilizado em mais de um fluxo, extraia a logica para `lib/*.psm1` em vez de duplicar.
- Se a compatibilidade com PowerShell 5.1 quebrar, procure primeiro sintaxe moderna nao suportada ou dependencia de modulo ausente.
- Se o comportamento depender de contexto de execucao, revise uso de `$PSScriptRoot`, paths relativos e importacao de modulos locais.

## Pre-Delivery Checklist
- Confirme que `.ps1` e `.psm1` foram usados com responsabilidades corretas.
- Confirme que parametros relevantes estao tipados e o fluxo falha de forma controlada.
- Confirme que a logica reutilizavel foi extraida para `lib/` quando apropriado.
- Confirme que os checks PowerShell do repositorio continuam passando.
