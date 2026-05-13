$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "--- [CHECKUP ORQUESTRADOR v5.2.0] ---" -ForegroundColor Cyan

# 1. Verificar .env
if (Test-Path (Join-Path $ProjectRoot ".env")) {
    Write-Host "[OK] Arquivo .env encontrado." -ForegroundColor Green
} else {
    Write-Host "[ERRO] Arquivo .env AUSENTE!" -ForegroundColor Red
}

# 2. Verificar Porta 8000
$port = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($port) {
    Write-Host "[AVISO] Porta 8000 ocupada pelo PID $($port.OwningProcess[0])." -ForegroundColor Yellow
} else {
    Write-Host "[OK] Porta 8000 livre." -ForegroundColor Green
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
        if ($walSize -gt 1024) {
            Write-Host "[AVISO] WAL muito grande ($($walSize.ToString('F1')) KB). Checkpoint necessario." -ForegroundColor Yellow
        }
    }
}

Write-Host "`nCheckup concluido." -ForegroundColor Cyan
