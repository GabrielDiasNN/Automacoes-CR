---
name: powershell-automation-monitor
description: Use when writing or reviewing PowerShell in this repo (Infrastructure lifecycle scripts, Tools governance checks, the shared lib/*.psm1 modules, and the domain run.ps1 entrypoints) so the PowerShell 5.1 runtime and the pre-commit governance stay intact.
---

## Purpose
Fixar as decisões de PowerShell do hub: qual runtime é alvo (5.1, não 7), como capturar exceção e processo sem quebrar nesse runtime, quais módulos `lib/` já existem antes de duplicar função, e quais scripts de `Tools/` validam o resultado. O objetivo é o script passar no pre-commit e rodar no cron de produção sem falha silenciosa.

## When to Use
- Ao editar scripts de ciclo de vida em `Infrastructure/` (`Start-Orchestrator.ps1`, `Recover-Orchestrator.ps1`, `MonitorAutomacoes.ps1`).
- Ao editar checks de governança em `Tools/` (`ValidarAutomacoes.ps1`, `Test-*Governance.ps1`) ou módulos em `lib/*.psm1`.
- Ao alterar o `run.ps1` de uma das 6 automações de domínio.
- Ao decidir se uma lógica nova vira `.ps1` (entrypoint) ou `.psm1` (reuso em `lib/`), e ao revisar `param(...)`, `CmdletBinding`, catch tipado e uso de `$PSScriptRoot`.

## Do Not Use When
- Para regras de `ExecId`, idempotência e ownership de estado entre runtimes: use a skill enterprise-orchestration-contract.
- Para política de segredo, mascaramento, severidade de log e degradação segura: use a skill automation-runtime-safety.
- Para o código Python que o `run.ps1` chama (extratores Oracle, `session_scope`, mypy): use a skill python-enterprise-standard.
- Para canais WhatsApp/headless em Node ou contratos visuais de dashboard: use a skill nodejs-communications ou a skill html-css-enterprise-standard.

## Related Skills
- `enterprise-orchestration-contract` para o papel do script dentro do fluxo de execuções.
- `automation-runtime-safety` para Zero Trust, portabilidade de caminho e logging que o script PowerShell deve seguir.
- `python-enterprise-standard` quando o mesmo PR toca o `.py` que o `run.ps1` invoca.
- `ai-native-development-standard` quando a mudança exigir atualizar documentação ou governança de contexto.

## Non-Negotiable Rules
- Compatibilidade com PowerShell 5.1 é regra, não preferência. O runtime de produção usa `powershell.exe`; `pwsh` 7 já causou falha silenciosa no cron das 02:00. Não use sintaxe exclusiva do 7 em script consumido pela esteira.
- Todo `catch` precisa de tipo. `catch {` genérico reprova no pre-commit; use no mínimo `catch [System.Exception]`, e a exceção específica quando ela for previsível (`catch [System.IO.IOException]`).
- Para inspecionar linha de comando de processo, use `Get-CimInstance Win32_Process`, **nunca `Get-Process`** — ele não expõe `CommandLine` no PS 5.1 (contrato em `docs/governance-contracts.md § PowerShell 5.1 — inspeção de processos`). `Lib-OrchestratorRuntime.psm1` (`Stop-OrchestratorProcesses`) já faz assim; reutilize.
- Nada de caminho absoluto com letra de drive — `Tools/Test-PortablePaths.ps1` reprova; use `$PSScriptRoot` ou caminho relativo.
- Só verbos aprovados — `Tools/Test-PowerShellApprovedVerbs.ps1` valida a nomeação de função.
- `.ps1` e `.psm1` são a exceção do repo ao padrão sem-BOM: exigem BOM. O contrato por extensão está em `AGENTS.md § Regras de Encoding` e é aplicado por `Assert-FileEncoding.ps1` a cada Edit/Write — se seu editor grava sem BOM por padrão, ajuste antes de salvar `.ps1`.
- Os snippets exatos de catch tipado, formato de `param` e demais contratos PowerShell do hook estão em `docs/governance-contracts.md § Contrato PowerShell — catch tipado` e `docs/governance-contracts.md § Contrato PowerShell — paths portáveis` — consulte antes de escrever código novo.

## Repo-Specific Constraints
- Módulos compartilhados de `lib/` — cheque antes de duplicar função: `Lib-Config.psm1`, `Lib-Logging.psm1`, `Lib-LogEvent.psm1`, `Lib-Process.psm1`, `Lib-Retry.psm1`, `Lib-Email.psm1`, `Lib-Idempotency.psm1`, `Lib-Oracle.psm1`, `Lib-OrchestratorRuntime.psm1`.
- Todo script de `Infrastructure/` que precise de versão de runtime, leitura de `.env` ou encerramento de processo consome `Lib-OrchestratorRuntime.psm1` (`Get-OrchestratorRuntimeVersion`, `Get-OrchestratorEnvValue`, `Stop-OrchestratorProcesses`) — não reimplemente. `Install-OrchestratorTask.ps1` é a exceção legítima: só registra a tarefa agendada e não usa nenhuma dessas capacidades.
- O entrypoint de automação de domínio é `run.ps1`; configuração sensível vem do `.env` via `lib/Lib-Config.psm1`, sem segredo em código.
- Não execute os `run.ps1` de domínio para "testar" — eles disparam e-mail via Outlook e consultas Oracle de produção. Para exercitar o motor, enfileire pela API/dashboard.
- Falso verde conhecido: ler exit code de `.ps1` por `| Select-Object` mascara a falha — redirecione a saída para arquivo e cheque `$LASTEXITCODE`.

## Validation
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PowerShellGovernance.ps1 -RootPath .`
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PowerShellApprovedVerbs.ps1 -RootPath .`
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/Test-PortablePaths.ps1 -RootPath .`
- `pwsh -NoProfile -ExecutionPolicy Bypass -File Tools/ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance` quando a mudança afeta `Infrastructure/` ou scripts de governança.
- `pwsh -File Tools/Test-SkillsGovernance.ps1 -BasePath .` quando o PR edita esta `SKILL.md`.

## Troubleshooting
- Hook acusa `catch` genérico: adicione tipo — `catch [System.IO.IOException]` para IO previsível, `catch [System.Exception]` como piso.
- Script roda no seu box com pwsh 7 e falha calado no cron: sintaxe exclusiva do 7; teste sob `powershell.exe` 5.1 antes de commitar.
- Match de processo ou `Stop-OrchestratorProcesses` volta vazio no 5.1: há `Get-Process` no caminho; troque por `Get-CimInstance Win32_Process`.
- `Test-PortablePaths.ps1` reprova: caminho com letra de drive; troque por `$PSScriptRoot` ou relativo.
- Pipeline reporta verde mas a automação falhou: exit code engolido por `| Select-Object`; redirecione stdout para arquivo e valide `$LASTEXITCODE -eq 0`.
- Lógica repetida em mais de um script: extraia para `lib/*.psm1` em vez de copiar entre `.ps1`.

## Pre-Delivery Checklist
- Roda sob `powershell.exe` 5.1, não só sob `pwsh` 7.
- Todo `catch` tipado; nomes de função com verbo aprovado.
- Sem caminho com letra de drive; só `$PSScriptRoot` ou relativo.
- Lógica reutilizável em `lib/*.psm1`; script de `Infrastructure/` consome `Lib-OrchestratorRuntime.psm1` (exceto `Install-OrchestratorTask.ps1`).
- `.ps1`/`.psm1` salvos com BOM (a exceção do repo — ver `AGENTS.md § Regras de Encoding`).
- `Test-PowerShellGovernance.ps1` e, se esta skill mudou, `Test-SkillsGovernance.ps1` verdes.
