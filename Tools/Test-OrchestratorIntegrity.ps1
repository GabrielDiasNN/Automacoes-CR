<#
.SYNOPSIS
    Valida a integridade do Orquestrador e do Worker (Fase 3).
.DESCRIPTION
    Realiza tres checagens essenciais:
    1. Verifica se os processos Python (API e Worker) estao ativos.
    2. Valida a conectividade da API local e dos contratos operacionais principais.
    3. Executa a suite de testes unitarios (PyTest).
#>

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = (Get-Item $ScriptDir).Parent.FullName

Write-Host "=== Teste de Integridade: Control Tower ===" -ForegroundColor Cyan

$hasErrors = $false
$apiKey = $null
$envPath = Join-Path $ProjectRoot ".env"
if (Test-Path $envPath) {

    $keyLine = Get-Content $envPath | Where-Object { $_ -match '^ORCHESTRATOR_API_KEY=' } | Select-Object -First 1

    if ($keyLine) {

        $apiKey = ($keyLine -split '=', 2)[1].Trim()

    }

}
$headers = @{}
if ($apiKey) {

    $headers["X-API-Key"] = $apiKey

}

# 1. Checagem de Processos
Write-Host "1. Verificando processos ativos..." -NoNewline
$pythonProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue
if ($pythonProcs.Count -ge 2) {
    Write-Host " [OK] ($($pythonProcs.Count) instancias detectadas)" -ForegroundColor Green
} else {
    Write-Host " [FALHA] Orquestrador ou Worker nao encontrados." -ForegroundColor Red
    $hasErrors = $true
}

# 2. Checagem de API (Health Check)
Write-Host "2. Verificando conectividade da API..." -NoNewline
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -TimeoutSec 5
    if ($res.scheduler_running -eq $true) {
        Write-Host " [OK] (FastAPI Online & Scheduler Ativo)" -ForegroundColor Green
    } else {
        Write-Host " [AVISO] API Online, mas Scheduler esta desligado." -ForegroundColor Yellow
        $hasErrors = $true
    }
    } catch [System.Exception] {
    Write-Host " [FALHA] API Offline na porta 8000." -ForegroundColor Red
    $hasErrors = $true
    }

Write-Host "2.1 Verificando contratos operacionais..." -NoNewline

try {

    $diag = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/diagnostics" -Headers $headers -TimeoutSec 5

    $baseline = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/baseline" -Headers $headers -TimeoutSec 5

    $history = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/history?hours=1" -Headers $headers -TimeoutSec 5

    $portfolioHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/portfolio/health" -Headers $headers -TimeoutSec 5

    $portfolioDrift = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/portfolio/drift" -Headers $headers -TimeoutSec 5

    if ($diag.contract_version -and $baseline.status -and $history.trend_summary -and $portfolioHealth.summary -and $portfolioDrift.summary) {

        Write-Host " [OK] (diagnostics + baseline + history + portfolio disponiveis)" -ForegroundColor Green

    } else {

        Write-Host " [AVISO] Contratos de diagnostics/baseline/history/portfolio incompletos." -ForegroundColor Yellow

        $hasErrors = $true

    }

    } catch [System.Exception] {

    Write-Host " [FALHA] diagnostics/baseline/history/portfolio indisponiveis." -ForegroundColor Red

    $hasErrors = $true

    }



# 3. Execucao de Testes Unitarios (PyTest)
Write-Host "3. Executando suite PyTest..." -ForegroundColor Cyan
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyTest = Join-Path $ProjectRoot ".venv\Scripts\pytest.exe"

if (Test-Path $PyTest) {
    $env:PYTHONPATH = Join-Path $ProjectRoot "Orchestrator"
    $pytestOutput = & $PyTest (Join-Path $ProjectRoot "Orchestrator\tests") -q 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Todos os testes unitarios passaram." -ForegroundColor Green
    } else {
        Write-Host "[FALHA] Erros detectados na suite de testes." -ForegroundColor Red
        $pytestOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        $hasErrors = $true
    }
} else {
    Write-Host "[AVISO] PyTest nao encontrado no ambiente virtual." -ForegroundColor Yellow
}

if ($hasErrors) {
    Write-Host "`n[FALHA] A integridade do Orquestrador esta comprometida." -ForegroundColor Red
    exit 1
}

Write-Host "`n[SUCESSO] Sistema integro e validado." -ForegroundColor Green
exit 0

