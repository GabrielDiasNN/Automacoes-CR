# Requires -Version 5.1
<#
.SYNOPSIS
    Coleta e apresenta o snapshot de qualidade do Hub de Automações.
.DESCRIPTION
    Script robusto que calcula tamanho do repo, arquivos grandes, cobertura pytest,
    pylint score, erros mypy e conformidade de governança local, exibindo um painel consolidado.
.VERSION
    1.0.0
#>
$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Garantir UTF-8 para saídas de console de ferramentas externas
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   COLETANDO METRICAS DE QUALIDADE - HUB DE AUTOMACOES" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verificar ambiente virtual .venv
$venvPath = Join-Path $PSScriptRoot "..\.venv"
if (-not (Test-Path $venvPath)) {
    Write-Error "Ambiente virtual (.venv) nao encontrado na raiz! Execute o bootstrap da Fase 2 primeiro."
}
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

# 2. Medir tamanho do código fonte e do repositório total
Write-Host "[1/6] Medindo tamanho do repositorio..." -ForegroundColor Yellow

$excludeSourcePattern = '\\(\.git|\.venv|\.wwebjs_auth|\.mypy_cache|__pycache__|Logs|Backups|node_modules|playwright-report|test-results)\\'
$excludeRepoPattern = '\\(\.venv|\.wwebjs_auth|node_modules|playwright-report|test-results)\\'

$sourceFiles = Get-ChildItem -Path "$PSScriptRoot\.." -Recurse -File | 
    Where-Object { $_.FullName -notmatch $excludeSourcePattern }

$sourceSizeSum = ($sourceFiles | Measure-Object -Property Length -Sum).Sum
$sourceSizeMB = [math]::Round($sourceSizeSum / 1MB, 2)
$sourceFilesCount = $sourceFiles.Count

$repoFiles = Get-ChildItem -Path "$PSScriptRoot\.." -Recurse -File | 
    Where-Object { $_.FullName -notmatch $excludeRepoPattern }

$repoSizeSum = ($repoFiles | Measure-Object -Property Length -Sum).Sum
$repoSizeMB = [math]::Round($repoSizeSum / 1MB, 2)

# 3. Detectar arquivos maiores que 5 MB
Write-Host "[2/6] Buscando arquivos maiores que 5 MB (excluindo .venv e .git)..." -ForegroundColor Yellow
$largeFiles = Get-ChildItem -Path "$PSScriptRoot\.." -Recurse -File | 
    Where-Object { $_.Length -gt 5MB -and $_.FullName -notmatch $excludeSourcePattern } |
    Select-Object Name, @{Name="SizeMB"; Expression={[math]::Round($_.Length / 1MB, 2)}}, FullName

# 4. Executar Pytest com cobertura
Write-Host "[3/6] Executando suite unitaria com pytest-cov (isso pode levar alguns segundos)..." -ForegroundColor Yellow
$env:PYTHONPATH = "Orchestrator"
$pytestProcess = Start-Process -FilePath $pythonExe -ArgumentList "-m pytest Orchestrator/tests --cov=Orchestrator/app --cov-report=term" -NoNewWindow -PassThru -RedirectStandardOutput "pytest_cov.tmp" -RedirectStandardError "pytest_err.tmp"
$pytestProcess.WaitForExit()

$pytestCoverage = 0
$pytestErrors = $false
if (Test-Path "pytest_cov.tmp") {
    $pytestOut = [System.IO.File]::ReadAllText("pytest_cov.tmp")
    $totalLine = $pytestOut -split "`r?`n" | Where-Object { $_ -match '^TOTAL\s+' }
    if ($totalLine -match '(\d+)%') {
        $pytestCoverage = [int]$Matches[1]
    }
    Remove-Item "pytest_cov.tmp" -Force
}
if (Test-Path "pytest_err.tmp") {
    $errOut = [System.IO.File]::ReadAllText("pytest_err.tmp")
    if ($errOut -match "FAILED") {
        $pytestErrors = $true
    }
    Remove-Item "pytest_err.tmp" -Force
}

if ($pytestProcess.ExitCode -ne 0) {
    $pytestErrors = $true
}

# 5. Executar Pylint score
Write-Host "[4/6] Analisando qualidade estetica com Pylint..." -ForegroundColor Yellow
$pylintProcess = Start-Process -FilePath $pythonExe -ArgumentList "-m pylint Orchestrator/app" -NoNewWindow -PassThru -RedirectStandardOutput "pylint.tmp" -RedirectStandardError "pylint_err.tmp"
$pylintProcess.WaitForExit()

$pylintScore = 0.0
if (Test-Path "pylint.tmp") {
    $pylintOut = [System.IO.File]::ReadAllText("pylint.tmp")
    $scoreLine = $pylintOut -split "`r?`n" | Where-Object { $_ -match 'rated at (-?\d+\.\d+)/10' }
    if ($scoreLine -match 'rated at (-?\d+\.\d+)/10') {
        $pylintScore = [double]$Matches[1]
    }
    Remove-Item "pylint.tmp" -Force
}
if (Test-Path "pylint_err.tmp") {
    Remove-Item "pylint_err.tmp" -Force
}

# 6. Executar Mypy type-checking
Write-Host "[5/6] Analisando tipagem estatica com Mypy..." -ForegroundColor Yellow
$mypyProcess = Start-Process -FilePath $pythonExe -ArgumentList "-m mypy --explicit-package-bases Orchestrator" -NoNewWindow -PassThru -RedirectStandardOutput "mypy.tmp" -RedirectStandardError "mypy_err.tmp"
$mypyProcess.WaitForExit()

$mypyErrors = 0
if (Test-Path "mypy.tmp") {
    $mypyOut = [System.IO.File]::ReadAllText("mypy.tmp")
    if ($mypyOut -match 'Found (\d+) error') {
        $mypyErrors = [int]$Matches[1]
    }
    Remove-Item "mypy.tmp" -Force
}
if (Test-Path "mypy_err.tmp") {
    Remove-Item "mypy_err.tmp" -Force
}

# 7. Executar Governança agregada e Zero Trust
Write-Host "[6/6] Executando validacao de governanca agregada local..." -ForegroundColor Yellow
$null = powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\ValidarAutomacoes.ps1" -BasePath "$PSScriptRoot\.." -OnlyGovernance
$govExitCode = $LASTEXITCODE
$govStatus = if ($govExitCode -eq 0) { "APROVADO" } else { "REJEITADO" }

Write-Host "`n=== RESULTADO CONSOLIDADO DO SNAPSHOT DE QUALIDADE ===" -ForegroundColor Cyan

# Formatar status visual para as métricas
$statusCoverage = if ($pytestCoverage -ge 60) { "✅" } else { "⚠️" }
$statusMypy = if ($mypyErrors -eq 0) { "✅" } else { "❌" }
$statusPylint = if ($pylintScore -ge 8.5) { "✅" } else { "⚠️" }
$statusRepoSize = if ($repoSizeMB -le 150) { "✅" } else { "⚠️" }
$statusGov = if ($govStatus -eq "APROVADO") { "✅" } else { "❌" }

Write-Host "--------------------------------------------------------" -ForegroundColor Gray
Write-Host " Metrica                          | Meta     | Atual    | Status" -ForegroundColor Gray
Write-Host "--------------------------------------------------------" -ForegroundColor Gray
Write-Host (" Cobertura de Testes (Pytest)     | >= 60%   | {0,-8} | {1}" -f "$pytestCoverage%", $statusCoverage)
Write-Host (" Erros de Tipagem (Mypy)          | 0        | {0,-8} | {1}" -f $mypyErrors, $statusMypy)
Write-Host (" Score de Estilo (Pylint)         | >= 8.5   | {0,-8} | {1}" -f "$pylintScore/10", $statusPylint)
Write-Host (" Tamanho do Repositorio (Total)  | <= 150MB | {0,-8} | {1}" -f "$repoSizeMB MB", $statusRepoSize)
Write-Host (" Governanca Agregada e ZeroTrust  | APROVADO | {0,-8} | {1}" -f $govStatus, $statusGov)
Write-Host "--------------------------------------------------------" -ForegroundColor Gray

Write-Host ("`nTamanho do Codigo Fonte (Limpo): {0} MB ({1} arquivos)" -f $sourceSizeMB, $sourceFilesCount) -ForegroundColor Green

if ($largeFiles.Count -gt 0) {
    Write-Host "`n⚠️  ALERTA: Detectados arquivos maiores que 5 MB:" -ForegroundColor Yellow
    foreach ($file in $largeFiles) {
        Write-Host (" - {0} ({1} MB) -> {2}" -f $file.Name, $file.SizeMB, $file.FullName) -ForegroundColor DarkYellow
    }
} else {
    Write-Host "`n✅ Nenhum arquivo maior que 5 MB detectado (excluindo .venv e .git)." -ForegroundColor Green
}

Write-Host "`nSnapshot finalizado com sucesso." -ForegroundColor Green
