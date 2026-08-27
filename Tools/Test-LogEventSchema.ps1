# {
#   "version": "2.0.0",
#   "skill": "ai-native-development-standard",
#   "description": "Valida docs/log-event.samples.jsonl (estrito) e Logs/*.jsonl (rollout) contra docs/log-event.schema.json"
# }
[CmdletBinding()]
param(
    [string]$RootPath = ".",
    [string[]]$Paths = @(),
    [ValidateSet("warn", "blocking")]
    [string]$Mode = "blocking"
)

$ErrorActionPreference = "Stop"

$rootFull = (Resolve-Path -LiteralPath $RootPath).Path
$validator = Join-Path $rootFull "Tools\log_event_validator.py"
$samplesFile = Join-Path $rootFull "docs\log-event.samples.jsonl"

Write-Host "=== Contrato de Evento de Log (log-event.schema.json) ===" -ForegroundColor Cyan

# Prefere o venv do projeto; cai para o `python` do PATH (ambiente do CI, que
# instala as dependencias no Python global via setup-python).
$venvPython = Join-Path $rootFull ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    (Get-Command python).Source
} else {
    $null
}

if (-not $pythonExe) {
    Write-Host "[WARN] Python nao encontrado (.venv nem PATH); validacao de log-event pulada." -ForegroundColor Yellow
    exit 0
}
if (-not (Test-Path -LiteralPath $validator)) {
    Write-Host "[ERRO] Validador ausente: $validator" -ForegroundColor Red
    exit 1
}

$hardFail = $false

function Invoke-LogEventValidator {
    <#
    .SYNOPSIS
        Executa o validador Python e devolve saida combinada + exit code.
    .DESCRIPTION
        O `2>&1` sobre um executavel NATIVO converte cada linha de stderr em
        ErrorRecord; com $ErrorActionPreference = "Stop" isso vira um
        NativeCommandError TERMINANTE no Windows PowerShell 5.1. Como o
        validador SEMPRE escreve a linha de resumo em stderr (mesmo com zero
        violacoes), o gate abortava com exit 1 em toda execucao sob 5.1 --
        passando so em pwsh 7. Rebaixar a preferencia ao redor da chamada
        nativa mantem o stderr como texto e preserva $LASTEXITCODE como a
        unica fonte de veredito.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $saida = & $Exe @Arguments 2>&1
        return [PSCustomObject]@{ Output = $saida; ExitCode = $LASTEXITCODE }
    }
    finally {
        $ErrorActionPreference = $anterior
    }
}

# 1) Golden samples — SEMPRE validado, modo ESTRITO (sem --rollout). E a ancora
#    de conformidade do CI (Logs/*.jsonl e gitignored e nao existe em checkout limpo).
if (Test-Path -LiteralPath $samplesFile) {
    $res = Invoke-LogEventValidator -Exe $pythonExe -Arguments @($validator, $samplesFile)
    $out = $res.Output
    $rc = $res.ExitCode
    $out | ForEach-Object { Write-Host $_ }
    if ($rc -eq 0) {
        Write-Host "[OK] docs/log-event.samples.jsonl em conformidade com o schema." -ForegroundColor Green
    } else {
        Write-Host "[ERRO] docs/log-event.samples.jsonl viola o schema (modo estrito)." -ForegroundColor Red
        $hardFail = $true
    }
} else {
    Write-Host "[WARN] docs/log-event.samples.jsonl ausente." -ForegroundColor Yellow
}

# 2) Logs/*.jsonl locais (quando existirem) — modo --rollout (ignora linha legada
#    sem trace_id, ex.: envelope antigo do Orchestrator).
$excludedPathRegex = "\\(\.venv|node_modules|\.git|\.wwebjs_auth|\.playwright-mcp|\.pytest_cache|\.mypy_cache)\\"

if ($Paths.Count -gt 0) {
    $files = @()
    foreach ($p in $Paths) {
        $p = $p.Trim('"')
        $full = Join-Path $rootFull $p
        if ((Test-Path -LiteralPath $full -PathType Leaf) -and $full -match '\.jsonl$' -and $full -match '\\Logs\\') {
            $files += (Get-Item -LiteralPath $full)
        }
    }
} else {
    $files = Get-ChildItem -Path $rootFull -Filter "*.jsonl" -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch $excludedPathRegex -and $_.DirectoryName -match '\\Logs$' }
}

if ($files -and @($files).Count -gt 0) {
    $pyArgs = @($validator, "--rollout") + ($files | ForEach-Object { $_.FullName })
    $res2 = Invoke-LogEventValidator -Exe $pythonExe -Arguments $pyArgs
    $out2 = $res2.Output
    $rc2 = $res2.ExitCode
    $out2 | ForEach-Object { Write-Host $_ }
    if ($rc2 -eq 0) {
        Write-Host "[OK] $(@($files).Count) arquivo(s) Logs/*.jsonl em conformidade.`n" -ForegroundColor Green
    } elseif ($Mode -eq "blocking") {
        Write-Host "[ERRO] Violacoes em Logs/*.jsonl (modo blocking)." -ForegroundColor Red
        $hardFail = $true
    } else {
        Write-Host "[WARN] Violacoes em Logs/*.jsonl (modo warn: nao bloqueia).`n" -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] Nenhum arquivo Logs/*.jsonl no escopo." -ForegroundColor Green
}

if ($hardFail) { exit 1 }
exit 0
