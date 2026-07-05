param(
    [string]$RootPath = $null,
    [string[]]$Paths = @()
)

# ATENCAO: ao invocar este script para validar multiplos arquivos, use sempre o
# operador `&` in-process (ex.: `& $path -Paths $TargetPaths`), como faz
# Tools\ValidarAutomacoes.ps1. Invocacoes via `pwsh -File Test-PythonGovernance.ps1
# -Paths @(...)` a partir de OUTRO processo pwsh perdem elementos do array: o
# parser de CLI do pwsh.exe (modo -File) nao faz o binding rico de array do
# PowerShell e captura apenas o primeiro token, descartando os demais antes do
# script executar. O split abaixo recupera apenas o caso em que os caminhos
# chegam colapsados em uma unica string separada por virgula.
if ($Paths.Count -eq 1 -and $Paths[0] -match ',') {
    $Paths = $Paths[0] -split ',' | Where-Object { $_ }
}

if ([string]::IsNullOrEmpty($RootPath)) {
    $RootPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = 1
$env:PYLINTHOME = Join-Path $RootPath ".mypy_cache\pylint"
$env:MYPYPATH = "$(Join-Path $RootPath "Orchestrator");$RootPath;$(Join-Path $RootPath "lib\python")"
$env:PYTHONPATH = "$($env:PYTHONPATH);$(Join-Path $RootPath "Orchestrator");$(Join-Path $RootPath "lib\python");$(Join-Path $RootPath "Produção Beneficimento\src")"
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

# Debito tecnico controlado: arquivos historicos com "pylint: disable=all" estao
# congelados no baseline. Arquivos novos nao podem nascer com a diretiva.
$baselinePath = Join-Path $PSScriptRoot "pylint-disable-all-baseline.txt"
$baseline = @()
if (Test-Path $baselinePath) {
    $baseline = Get-Content $baselinePath -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith('#') }
}
foreach ($fullPath in $resolvedTargetFiles) {
    $normalizedRoot = ($RootPath -replace '/', '\').TrimEnd('\')
    $normalizedFull = $fullPath -replace '/', '\'
    $relative = $normalizedFull.Substring($normalizedRoot.Length).TrimStart('\') -replace '\\', '/'
    $head = Get-Content $fullPath -TotalCount 3 -ErrorAction SilentlyContinue
    if (($head -match 'pylint:\s*disable=all') -and ($baseline -notcontains $relative)) {
        Write-Host "[ERRO] '$relative' usa 'pylint: disable=all' e nao esta no baseline ($baselinePath). Arquivos novos devem passar no Pylint sem suprimir todos os checks." -ForegroundColor Red
        $hasErrors = $true
    }
}

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
    # C0411 (wrong-import-order) desabilitado: a deteccao de first-party do pylint
    # (baseada no PYTHONPATH/layout de pacotes) diverge da ordenacao real exigida
    # pelo isort (perfil "black", sem known-first-party configurado) que roda no
    # CI (job Lint Python). As duas ferramentas discordam sobre a mesma linha em
    # arquivos de Orchestrator/tests/ que importam de "app.*" e de bibliotecas
    # como fastapi/sqlalchemy/pytest — isort e o padrao real, pylint fica mudo.
    $pylintOutput = & $pylint --disable=C0114,C0115,C0116,R0801,C0413,C0301,C0302,C0411 @resolvedTargetFiles 2>&1
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
