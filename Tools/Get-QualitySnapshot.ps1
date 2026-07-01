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
$env:PYTHONUTF8 = 1
$env:PYLINTHOME = Join-Path $PSScriptRoot ".mypy_cache\pylint"
$env:MYPYPATH = "$(Join-Path $PSScriptRoot "..\Orchestrator");$(Join-Path $PSScriptRoot "..")"
New-Item -ItemType Directory -Force -Path $env:PYLINTHOME | Out-Null

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   COLETANDO METRICAS DE QUALIDADE - HUB DE AUTOMACOES" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verificar ambiente virtual .venv
$venvPath = Join-Path $PSScriptRoot "..\.venv"
if (-not (Test-Path $venvPath)) {
    Write-Error "Ambiente virtual (.venv) nao encontrado na raiz! Execute o bootstrap da Fase 2 primeiro."
}
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

function Get-PythonTool {
    param([string]$ToolName)

    $venvTool = Join-Path $PSScriptRoot "..\.venv\Scripts\$ToolName.exe"
    if (Test-Path $venvTool) { return $venvTool }
    if (Get-Command $ToolName -ErrorAction SilentlyContinue) { return $ToolName }
    return $null
}

function Get-OrchestratorApiKey {
    $envPath = Join-Path $PSScriptRoot "..\.env"
    if (-not (Test-Path $envPath)) { return $null }
    $keyLine = Get-Content $envPath | Where-Object { $_ -match '^ORCHESTRATOR_API_KEY=' } | Select-Object -First 1
    if (-not $keyLine) { return $null }
    return ($keyLine -split '=', 2)[1].Trim()
}

# 2. Medir tamanho do código fonte, payload versionado e pegada operacional local
Write-Host "[1/6] Medindo tamanho do repositorio..." -ForegroundColor Yellow

$excludeSourcePattern = '\\(\.git|\.venv|\.wwebjs_auth|\.mypy_cache|__pycache__|Logs|Backups|node_modules|playwright-report|test-results)\\'
$excludedOperationalNames = @(
    ".venv",
    ".wwebjs_auth",
    "node_modules",
    "playwright-report",
    "test-results",
    "Logs",
    "Backups"
)
$runtimeTransientFiles = @(
    "Orchestrator\automacoes.db",
    "Orchestrator\automacoes.db-wal",
    "Orchestrator\automacoes.db-shm",
    "Orchestrator\orchestrator.pid",
    "Orchestrator\worker.pid",
    "Receitas Bloqueadas\email_body.html",
    "Receitas Bloqueadas\email_state.json",
    "Receitas Bloqueadas\receitas_state.json",
    "Receitas Emitidas\delivery_state.json",
    "Receitas Emitidas\receitas_state.json"
)

$sourceFiles = Get-ChildItem -Path "$PSScriptRoot\.." -Recurse -File | 
    Where-Object { $_.FullName -notmatch $excludeSourcePattern }

$sourceSizeSum = ($sourceFiles | Measure-Object -Property Length -Sum).Sum
$sourceSizeMB = [math]::Round($sourceSizeSum / 1MB, 2)
$sourceFilesCount = $sourceFiles.Count

$trackedFiles = @(git -C (Join-Path $PSScriptRoot "..") ls-files)
$trackedPayloadSum = 0
foreach ($trackedFile in $trackedFiles) {
    $fullPath = Join-Path "$PSScriptRoot\.." $trackedFile
    if (Test-Path $fullPath) {
        $trackedPayloadSum += (Get-Item $fullPath).Length
    }
}
$trackedPayloadMB = [math]::Round($trackedPayloadSum / 1MB, 2)

$localOperationalFootprint = 0
foreach ($name in $excludedOperationalNames) {
    $matchingDirs = Get-ChildItem -Path "$PSScriptRoot\.." -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $name }
    foreach ($match in $matchingDirs) {
        $localOperationalFootprint += (Get-ChildItem $match.FullName -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    }
}
foreach ($relativePath in $runtimeTransientFiles) {
    $fullPath = Join-Path "$PSScriptRoot\.." $relativePath
    if (Test-Path $fullPath) {
        $item = Get-Item $fullPath
        if (-not $item.PSIsContainer) {
            $localOperationalFootprint += $item.Length
        }
    }
}
$localOperationalFootprintMB = [math]::Round($localOperationalFootprint / 1MB, 2)

# 2.1 Catálogo governado de automações
$candidateAutomationDirs = Get-ChildItem -Path "$PSScriptRoot\.." -Directory |
    Where-Object {
        $_.Name -notin @("_Template", "Orchestrator", "Dashboard", "docs", "Tools", "Infrastructure", "lib", "Backups", "Logs") -and
        (Test-Path (Join-Path $_.FullName "run.ps1")) -and
        (Test-Path (Join-Path $_.FullName "README.md")) -and
        (Test-Path (Join-Path $_.FullName "CONTEXT.md"))
    }

$manifestFiles = Get-ChildItem -Path "$PSScriptRoot\.." -Directory |
    Where-Object { $_.Name -notlike ".*" } |
    ForEach-Object {
        $candidate = Join-Path $_.FullName "automation.manifest.json"
        if (Test-Path $candidate) { Get-Item $candidate }
    }

$activeManifestFiles = $manifestFiles | Where-Object { $_.Directory.Name -ne "_Template" }
$runbooksPresent = 0
$catalogIssues = 0
$smokeReady = 0
$pythonTargets = @(git -C (Join-Path $PSScriptRoot "..") ls-files "*.py")
$resolvedPythonTargets = @()

foreach ($file in $pythonTargets) {
    $fullPath = Join-Path "$PSScriptRoot\.." $file.Trim('"')
    if (Test-Path $fullPath) {
        $resolvedPythonTargets += $fullPath
    }
}

foreach ($manifestFile in $activeManifestFiles) {
    try {
        $manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw | ConvertFrom-Json
        $runbookPath = Join-Path "$PSScriptRoot\.." $manifest.runbook_path
        if (Test-Path $runbookPath) { $runbooksPresent++ } else { $catalogIssues++ }

        $hasSmoke = $false
        foreach ($smokeTest in @($manifest.smoke_tests)) {
            $smokePath = Join-Path "$PSScriptRoot\.." $smokeTest
            if (Test-Path $smokePath) {
                $hasSmoke = $true
            } else {
                $catalogIssues++
            }
        }
        if ($hasSmoke) { $smokeReady++ }
    } catch [System.Exception] {
        $catalogIssues++
    }
}

$automationDirCount = $candidateAutomationDirs.Count
$catalogCoverage = if ($automationDirCount -gt 0) {
    [math]::Round(($activeManifestFiles.Count / $automationDirCount) * 100, 1)
} else {
    100.0
}

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
$pylintScore = 0.0
$pylint = Get-PythonTool "pylint"
if ($pylint -and $resolvedPythonTargets.Count -gt 0) {
    $pylintOutput = & $pylint --disable=C0114,C0115,C0116,R0801 @resolvedPythonTargets 2>&1
    $pylintText = ($pylintOutput | Out-String)
    $scoreLine = $pylintText -split "`r?`n" | Where-Object { $_ -match 'rated at (-?\d+\.\d+)/10' }
    if ($scoreLine -match 'rated at (-?\d+\.\d+)/10') {
        $pylintScore = [double]$Matches[1]
    }
}

# 6. Executar Mypy type-checking
Write-Host "[5/6] Analisando tipagem estatica com Mypy..." -ForegroundColor Yellow
$mypyErrors = 0
$mypy = Get-PythonTool "mypy"
if ($mypy -and $resolvedPythonTargets.Count -gt 0) {
    foreach ($file in $resolvedPythonTargets) {
        $mypyOutput = & $mypy --strict --explicit-package-bases --namespace-packages $file 2>&1
        if ($LASTEXITCODE -ne 0) {
            $mypyErrors += [regex]::Matches(($mypyOutput | Out-String), ': error:').Count
        }
    }
}

# 7. Executar Governança agregada e Zero Trust
Write-Host "[6/6] Executando validacao de governanca agregada local..." -ForegroundColor Yellow
$null = powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\ValidarAutomacoes.ps1" -BasePath "$PSScriptRoot\.." -OnlyGovernance
$govExitCode = $LASTEXITCODE
$govStatus = if ($govExitCode -eq 0) { "APROVADO" } else { "REJEITADO" }

$liveBaselineStatus = "N/D"
$liveBaselineRecommendedAction = $null
try {
    $apiKey = Get-OrchestratorApiKey
    $headers = @{}
    if ($apiKey) { $headers["X-API-Key"] = $apiKey }
    $baseline = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/baseline" -Headers $headers -TimeoutSec 3
    if ($baseline.status) {
        $liveBaselineStatus = [string]$baseline.status
        $liveBaselineRecommendedAction = [string]$baseline.recommended_action
    }
} catch [System.Exception] {
    $liveBaselineStatus = "INDISPONIVEL"
}

Write-Host "`n=== RESULTADO CONSOLIDADO DO SNAPSHOT DE QUALIDADE ===" -ForegroundColor Cyan

# Formatar status visual para as métricas
$statusCoverage = if ($pytestCoverage -ge 60) { "✅" } else { "⚠️" }
$statusMypy = if ($mypyErrors -eq 0) { "✅" } else { "❌" }
$statusPylint = if ($pylintScore -ge 8.5) { "✅" } else { "⚠️" }
$statusRepoSize = if ($trackedPayloadMB -le 150) { "✅" } else { "⚠️" }
$statusGov = if ($govStatus -eq "APROVADO") { "✅" } else { "❌" }
$statusBaseline = switch ($liveBaselineStatus.ToLowerInvariant()) {
    "healthy" { "✅" }
    "attention" { "⚠️" }
    "incident" { "❌" }
    default { "ℹ️" }
}

Write-Host "--------------------------------------------------------" -ForegroundColor Gray
Write-Host " Metrica                          | Meta     | Atual    | Status" -ForegroundColor Gray
Write-Host "--------------------------------------------------------" -ForegroundColor Gray
Write-Host (" Cobertura de Testes (Pytest)     | >= 60%   | {0,-8} | {1}" -f "$pytestCoverage%", $statusCoverage)
Write-Host (" Erros de Tipagem (Mypy)          | 0        | {0,-8} | {1}" -f $mypyErrors, $statusMypy)
Write-Host (" Score de Estilo (Pylint)         | >= 8.5   | {0,-8} | {1}" -f "$pylintScore/10", $statusPylint)
Write-Host (" Tamanho Versionado (Git)        | <= 150MB | {0,-8} | {1}" -f "$trackedPayloadMB MB", $statusRepoSize)
Write-Host (" Governanca Agregada e ZeroTrust  | APROVADO | {0,-8} | {1}" -f $govStatus, $statusGov)
Write-Host (" Baseline Operacional (Live)      | healthy  | {0,-12} | {1}" -f $liveBaselineStatus, $statusBaseline)
Write-Host "--------------------------------------------------------" -ForegroundColor Gray

Write-Host ("`nTamanho do Codigo Fonte (Limpo): {0} MB ({1} arquivos)" -f $sourceSizeMB, $sourceFilesCount) -ForegroundColor Green
Write-Host ("Pegada Operacional Local Excluida: {0} MB" -f $localOperationalFootprintMB) -ForegroundColor DarkCyan
Write-Host ("Cobertura do Catálogo Governado: {0}% ({1}/{2})" -f $catalogCoverage, $activeManifestFiles.Count, $automationDirCount) -ForegroundColor Cyan
Write-Host ("Runbooks Presentes no Catálogo: {0}" -f $runbooksPresent) -ForegroundColor Cyan
Write-Host ("Automações com Smoke Declarado: {0}" -f $smokeReady) -ForegroundColor Cyan
Write-Host ("Issues do Catálogo: {0}" -f $catalogIssues) -ForegroundColor Cyan
if ($liveBaselineRecommendedAction) {
    Write-Host ("Ação Recomendada do Baseline: {0}" -f $liveBaselineRecommendedAction) -ForegroundColor Cyan
}

if ($largeFiles.Count -gt 0) {
    Write-Host "`n⚠️  ALERTA: Detectados arquivos maiores que 5 MB:" -ForegroundColor Yellow
    foreach ($file in $largeFiles) {
        Write-Host (" - {0} ({1} MB) -> {2}" -f $file.Name, $file.SizeMB, $file.FullName) -ForegroundColor DarkYellow
    }
} else {
    Write-Host "`n✅ Nenhum arquivo maior que 5 MB detectado (excluindo .venv e .git)." -ForegroundColor Green
}

Write-Host "`nSnapshot finalizado com sucesso." -ForegroundColor Green
