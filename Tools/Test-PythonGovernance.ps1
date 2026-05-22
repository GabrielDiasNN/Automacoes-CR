param(
    [string]$RootPath = $PSScriptRoot,
    [string[]]$Paths = @()
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = 1
$env:PYLINTHOME = Join-Path $RootPath ".mypy_cache\pylint"
$env:MYPYPATH = "$(Join-Path $RootPath "Orchestrator");$RootPath"
New-Item -ItemType Directory -Force -Path $env:PYLINTHOME | Out-Null
Write-Host "=== Governanca Python (Type Hints & Pylint) ==="

$targetFiles = @()
if ($Paths.Count -gt 0) {
    $targetFiles = $Paths | Where-Object { $_ -match '\.py$' }
} else {
    $targetFiles = (git ls-files "*.py")
}

if ($targetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo Python (.py) para validar."
    exit 0
}

function Get-PythonTool {
    param([string]$ToolName)
    $venvTool = Join-Path $RootPath ".venv\Scripts\$ToolName.exe"
    if (Test-Path $venvTool) { return $venvTool }
    if (Get-Command $ToolName -ErrorAction SilentlyContinue) { return $ToolName }
    return $null
}

$resolvedTargetFiles = @()
foreach ($file in $targetFiles) {
    $file = $file.Trim('"')
    $fullPath = Join-Path $RootPath $file
    if (-not (Test-Path $fullPath)) { continue }
    Write-Host "Verificando: $file"
    $resolvedTargetFiles += $fullPath
}

if ($resolvedTargetFiles.Count -eq 0) {
    Write-Host "Nenhum arquivo Python (.py) existente para validar."
    exit 0
}

$hasErrors = $false
$mypy = Get-PythonTool "mypy"
$pylint = Get-PythonTool "pylint"

$oldPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
if ($mypy) {
    foreach ($file in $resolvedTargetFiles) {
        $mypyOutput = & $mypy --strict --explicit-package-bases --namespace-packages $file 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERRO] Falha de Tipagem Estrita (Mypy) em $file" -ForegroundColor Red
            $mypyOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
            $hasErrors = $true
        }
    }
} else {
    Write-Host "[AVISO] Mypy nao instalado. Validacao de tipagem Python pulada." -ForegroundColor Yellow
}
$ErrorActionPreference = $oldPreference

if ($pylint) {
    $pylintOutput = & $pylint --disable=C0114,C0116,R0801 @resolvedTargetFiles 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] Falha de Qualidade de Codigo (Pylint)" -ForegroundColor Red
        $pylintOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        $hasErrors = $true
    }
} else {
    Write-Host "[AVISO] Pylint nao instalado. Validacao de qualidade Python pulada." -ForegroundColor Yellow
}

if ($hasErrors) {
    Write-Host "`n[FALHA] Foram encontrados erros de governanca Python. Corrija-os antes de commitar." -ForegroundColor Red
    exit 1
}

Write-Host "Validacao Python concluida com sucesso." -ForegroundColor Green
exit 0
