# {
#   "version": "1.0.0",
#   "skill": "ai-native-development-standard",
#   "description": "Valida os arquivos Logs/*.jsonl contra docs/log-event.schema.json (ver docs/logging-standard.md)"
# }
[CmdletBinding()]
param(
    [string]$RootPath = ".",
    [string[]]$Paths = @(),
    [ValidateSet("warn", "blocking")]
    [string]$Mode = "warn"
)

$ErrorActionPreference = "Stop"

$rootFull = (Resolve-Path -LiteralPath $RootPath).Path
$validator = Join-Path $rootFull "Tools\log_event_validator.py"

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

if (-not $files -or @($files).Count -eq 0) {
    Write-Host "[OK] Nenhum arquivo Logs/*.jsonl no escopo." -ForegroundColor Green
    exit 0
}

$pyArgs = @($validator, "--rollout") + ($files | ForEach-Object { $_.FullName })
$output = & $pythonExe @pyArgs 2>&1
$exitCode = $LASTEXITCODE

$output | ForEach-Object { Write-Host $_ }

if ($exitCode -eq 0) {
    Write-Host "[OK] $(@($files).Count) arquivo(s) de log em conformidade com o schema.`n" -ForegroundColor Green
    exit 0
}

if ($Mode -eq "blocking") {
    Write-Host "[ERRO] Violacoes de contrato de log-event (modo blocking)." -ForegroundColor Red
    exit 1
}

Write-Host "[WARN] Violacoes de contrato de log-event (modo warn: nao bloqueia o gate)." -ForegroundColor Yellow
Write-Host "       Durante o rollout do padrao de logging. Ver docs/logging-standard.md.`n" -ForegroundColor Yellow
exit 0
