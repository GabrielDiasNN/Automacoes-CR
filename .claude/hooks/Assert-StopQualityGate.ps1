#Requires -Version 5.1
<#
.SYNOPSIS
    Hook Stop: barra o encerramento da tarefa quando o trabalho pendente ainda
    nao passou pelas verificacoes correspondentes.

.DESCRIPTION
    O gate completo (ValidarAutomacoes.ps1 -OnlyGovernance) leva ~171 s — acima
    do timeout padrao de hook e inviavel a cada encerramento. Por isso este hook
    faz apenas duas coisas baratas:

      1. Encoding: Tools/Test-SourceEncoding.ps1 em modo direcionado sobre os
         arquivos alterados. Deterministico e rapido; bloqueia se falhar.

      2. Marcadores: confere se pytest / lint do Dashboard foram disparados
         DEPOIS da ultima alteracao nos arquivos que os exigem, usando os
         carimbos gravados por Register-GateRun.ps1.

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

# --- 1. Encoding direcionado ---------------------------------------------
$encoding = Invoke-EncodingCheck -RepositoryRoot $repoRoot -RelativePaths $existing
if ($encoding.ExitCode -gt 0) {
    $problems += 'ENCODING: arquivos alterados violam a regra de BOM do repositorio.'
    $problems += $encoding.Output
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
