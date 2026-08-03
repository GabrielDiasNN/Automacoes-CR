#Requires -Version 5.1
<#
.SYNOPSIS
    Hook PostToolUse (Bash|PowerShell): registra que um gate de qualidade rodou.

.DESCRIPTION
    Inspeciona o comando executado e grava um marcador com carimbo de tempo em
    .claude/.state/. O hook de Stop (Assert-StopQualityGate.ps1) compara esses
    marcadores com o mtime dos arquivos alterados para decidir se o encerramento
    da tarefa esta coberto por verificacao.

    O marcador registra APENAS que o comando foi disparado; nao afirma que ele
    passou. O sinal de aprovacao continua sendo a leitura da saida pelo agente.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'HookCommon.psm1') -Force -DisableNameChecking

$payload = Get-HookPayload
if ($null -eq $payload) {
    exit 0
}

$command = Get-HookProperty -Payload $payload -Name 'command'
if ([string]::IsNullOrWhiteSpace($command)) {
    exit 0
}

$markers = @()
if ($command -match 'pytest') { $markers += 'last-pytest' }
if ($command -match 'ValidarAutomacoes|Test-PythonGovernance|Test-SourceEncoding') { $markers += 'last-governance' }
if ($command -match 'npm run (build|lint)') { $markers += 'last-dashboard' }

if ($markers.Count -eq 0) {
    exit 0
}

$stateDir = Join-Path (Get-RepositoryRoot) '.claude\.state'
if (-not (Test-Path -LiteralPath $stateDir -PathType Container)) {
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
}

$stamp = (Get-Date).ToString('o')
foreach ($marker in ($markers | Select-Object -Unique)) {
    Set-Content -LiteralPath (Join-Path $stateDir $marker) -Value $stamp -Encoding ascii -NoNewline
}

exit 0
