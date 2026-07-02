$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Import-Module (Join-Path $ProjectRoot "lib\Lib-OrchestratorRuntime.psm1") -Force
$RuntimeVersion = Get-OrchestratorRuntimeVersion -ProjectRoot $ProjectRoot

# Carregar porta do .env para diagnostico dinamico
$envPath = Join-Path $ProjectRoot ".env"
$HubPort = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "HUB_API_PORT" -Default "8000"

Write-Host "--- [CHECKUP ORQUESTRADOR $RuntimeVersion] ---" -ForegroundColor Cyan
Write-Host "Target Port: $HubPort" -ForegroundColor Gray

# 1. Verificar .env
if (Test-Path $envPath) {
    Write-Host "[OK] Arquivo .env encontrado." -ForegroundColor Green
} else {
    Write-Host "[ERRO] Arquivo .env AUSENTE!" -ForegroundColor Red
}

# 2. Verificar Porta
$port = Get-NetTCPConnection -LocalPort $HubPort -ErrorAction SilentlyContinue
if ($port) {
    Write-Host "[OK] Porta $HubPort ativa (PID $($port.OwningProcess[0]))." -ForegroundColor Green
} else {
    Write-Host "[ERRO] Porta $HubPort NAO esta ouvindo. Orquestrador offline." -ForegroundColor Red
}

# 3. Verificar Python e Dependencias
if (Test-Path $VenvPython) {
    Write-Host "[OK] Ambiente Virtual (.venv) encontrado." -ForegroundColor Green
    $modules = "fastapi", "uvicorn", "apscheduler", "sqlalchemy", "pytz"
    foreach ($m in $modules) {
        & $VenvPython -c "import $m" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  > Modulo '$m': OK" -ForegroundColor Gray
        } else {
            Write-Host "  > Modulo '$m': FALHA!" -ForegroundColor Red
        }
    }
} else {
    Write-Host "[ERRO] Python nao encontrado em $VenvPython" -ForegroundColor Red
}

# 4. Verificar Banco de Dados
$dbPath = Join-Path $ProjectRoot "Orchestrator\automacoes.db"
if (Test-Path $dbPath) {
    $size = (Get-Item $dbPath).Length / 1KB
    Write-Host "[OK] Banco de dados encontrado ($($size.ToString('F1')) KB)." -ForegroundColor Green
    $walPath = "$dbPath-wal"
    if (Test-Path $walPath) {
        $walSize = (Get-Item $walPath).Length / 1KB
        if ($walSize -gt 5120) { # Aumentado threshold para 5MB
            Write-Host "[AVISO] WAL grande ($($walSize.ToString('F1')) KB). Checkpoint em breve." -ForegroundColor Yellow
        }
    }
}

Write-Host "`nCheckup $RuntimeVersion concluido." -ForegroundColor Cyan
