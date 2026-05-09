<#
.SYNOPSIS
    Valida a integridade do Orquestrador e do Worker (Fase 3).
.DESCRIPTION
    Realiza tres checagens essenciais:
    1. Verifica se os processos Python (API e Worker) estao ativos.
    2. Valida a conectividade da API local.
    3. Executa a suite de testes unitarios (PyTest).
#>

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectRoot = (Get-Item $ScriptDir).Parent.FullName

Write-Host "=== Teste de Integridade: Control Tower ===" -ForegroundColor Cyan

$hasErrors = $false

# 1. Checagem de Processos
Write-Host "1. Verificando processos ativos..." -NoNewline
$pythonProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue
if ($pythonProcs.Count -ge 2) {
    Write-Host " [OK] ($($pythonProcs.Count) instâncias detectadas)" -ForegroundColor Green
} else {
    Write-Host " [FALHA] Orquestrador ou Worker nao encontrados." -ForegroundColor Red
    $hasErrors = $true
}

# 2. Checagem de API (Health Check)
Write-Host "2. Verificando conectividade da API..." -NoNewline
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:8766/" -TimeoutSec 5
    if ($res.scheduler_running -eq $true) {
        Write-Host " [OK] (FastAPI Online & Scheduler Ativo)" -ForegroundColor Green
    } else {
        Write-Host " [AVISO] API Online, mas Scheduler esta desligado." -ForegroundColor Yellow
        $hasErrors = $true
    }
} catch {
    Write-Host " [FALHA] API Offline na porta 8766." -ForegroundColor Red
    $hasErrors = $true
}

# 3. Execucao de Testes Unitarios (PyTest)
Write-Host "3. Executando suíte PyTest..." -ForegroundColor Cyan
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyTest = Join-Path $ProjectRoot ".venv\Scripts\pytest.exe"

if (Test-Path $PyTest) {
    $env:PYTHONPATH = Join-Path $ProjectRoot "Orchestrator"
    $pytestOutput = & $PyTest (Join-Path $ProjectRoot "Orchestrator\tests") 2>&1
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
