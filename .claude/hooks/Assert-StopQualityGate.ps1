#Requires -Version 5.1
<#
.SYNOPSIS
    Hook Stop: barra o encerramento da tarefa quando o trabalho pendente ainda
    nao passou pelas verificacoes correspondentes.

.DESCRIPTION
    Duas verificacoes:

      1. Governanca: Tools/ValidarAutomacoes.ps1 -OnlyGovernance -Paths sobre os
         arquivos alterados — os 15 checks (zero-trust, SQL, mypy/pylint,
         PSScriptAnalyzer, encoding, JSON, Playwright, manifesto, arquitetura,
         datas, semantica, Node, schema de evento de log). O modo direcionado e o que torna isso viavel:
         SEM -Paths o script cai em full_scan (~171 s, medido); COM -Paths custa
         ~6 s sem Python e ~18 s com dois .py, onde o mypy domina.

      2. Marcadores: o gate de governanca NAO roda pytest nem build do Dashboard.
         Entao segue valendo a conferencia de que eles foram disparados DEPOIS da
         ultima alteracao nos arquivos que os exigem, pelos carimbos gravados por
         Register-GateRun.ps1.

    Respeita stop_hook_active: se o proprio hook ja bloqueou uma vez neste
    ciclo, aprova, para nao entrar em laco infinito.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'HookCommon.psm1') -Force -DisableNameChecking

function ConvertFrom-PorcelainLine {
    param([string]$Line)

    if ($Line.Length -le 3) { return $null }

    $path = $Line.Substring(3).Trim()

    # Renomeacao: "origem -> destino"; interessa o destino.
    $arrow = $path.IndexOf(' -> ', [System.StringComparison]::Ordinal)
    if ($arrow -ge 0) {
        $path = $path.Substring($arrow + 4)
    }

    return $path.Trim('"')
}

function Test-MarkerIsFresh {
    param(
        [string]$MarkerPath,
        [datetime]$NewestChange
    )

    if (-not (Test-Path -LiteralPath $MarkerPath -PathType Leaf)) {
        return $false
    }

    return (Get-Item -LiteralPath $MarkerPath).LastWriteTimeUtc -ge $NewestChange
}

$payload = Get-HookPayload
if ($null -ne $payload -and ($payload.PSObject.Properties.Name -contains 'stop_hook_active')) {
    if ($payload.stop_hook_active -eq $true) {
        exit 0
    }
}

$repoRoot = Get-RepositoryRoot

Push-Location -LiteralPath $repoRoot
try {
    $porcelain = @(& git status --porcelain 2>$null)
}
catch [System.Exception] {
    $porcelain = @()
}
finally {
    Pop-Location
}

if ($porcelain.Count -eq 0) {
    exit 0
}

$existing = @()
$newestChange = [datetime]::MinValue
foreach ($line in $porcelain) {
    $relative = ConvertFrom-PorcelainLine -Line $line
    if (-not $relative) { continue }

    $full = Join-Path $repoRoot $relative
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }

    $existing += $relative
    $mtime = (Get-Item -LiteralPath $full).LastWriteTimeUtc
    if ($mtime -gt $newestChange) { $newestChange = $mtime }
}

if ($existing.Count -eq 0) {
    exit 0
}

$problems = @()

# --- 1. Governanca direcionada (15 checks) --------------------------------
$gate = Invoke-GovernanceGate -RepositoryRoot $repoRoot -RelativePaths $existing
if ($gate.ExitCode -gt 0) {
    $problems += 'GOVERNANCA: os arquivos alterados reprovam em Tools/ValidarAutomacoes.ps1 -OnlyGovernance.'
    $problems += (Select-FailureLines -Output $gate.Output)
    $problems += '  (saida integral: pwsh -File Tools\ValidarAutomacoes.ps1 -BasePath . -OnlyGovernance -StagedOnly)'
    $problems += ''
}

# --- 2. Marcadores de verificacao ----------------------------------------
$stateDir = Join-Path $repoRoot '.claude\.state'

$pythonChanged = @($existing | Where-Object {
        $_ -match '\.py$' -and $_ -match '^(Orchestrator/|lib/python/|Produ..o Beneficimento/src/)'
    })

if ($pythonChanged.Count -gt 0) {
    if (-not (Test-MarkerIsFresh -MarkerPath (Join-Path $stateDir 'last-pytest') -NewestChange $newestChange)) {
        $problems += 'PYTEST: ha codigo Python governado alterado sem execucao de pytest posterior a ultima edicao.'
        $problems += ('  Arquivos: ' + (($pythonChanged | Select-Object -First 10) -join ', '))
        $problems += '  Rode: cd Orchestrator; ..\.venv\Scripts\pytest'
        $problems += ''
    }
}

$dashboardChanged = @($existing | Where-Object { $_ -match '^Dashboard/src/' })

if ($dashboardChanged.Count -gt 0) {
    if (-not (Test-MarkerIsFresh -MarkerPath (Join-Path $stateDir 'last-dashboard') -NewestChange $newestChange)) {
        $problems += 'DASHBOARD: ha fontes em Dashboard/src alteradas sem lint/build posterior a ultima edicao.'
        $problems += ('  Arquivos: ' + (($dashboardChanged | Select-Object -First 10) -join ', '))
        $problems += '  Rode: cd Dashboard; npm run lint; npm run build'
        $problems += ''
    }
}

if ($problems.Count -eq 0) {
    exit 0
}

$header = @(
    'STOP BLOQUEADO: o trabalho pendente ainda nao passou pelas verificacoes exigidas.',
    ''
)

[Console]::Error.WriteLine((($header + $problems) -join [Environment]::NewLine))
exit 2
