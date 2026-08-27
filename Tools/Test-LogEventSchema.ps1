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

# 1) Golden samples — SEMPRE validado, modo ESTRITO (sem --rollout). E a ancora
#    de conformidade do CI (Logs/*.jsonl e gitignored e nao existe em checkout limpo).
if (Test-Path -LiteralPath $samplesFile) {
    $out = & $pythonExe $validator $samplesFile 2>&1
    $rc = $LASTEXITCODE
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
    $out2 = & $pythonExe @pyArgs 2>&1
    $rc2 = $LASTEXITCODE
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
