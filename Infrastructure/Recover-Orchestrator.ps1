$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
$OrchestratorDir = Join-Path $ProjectRoot "Orchestrator"

Write-Host "--- [RESCUE MODE: ORQUESTRADOR v5.2] ---" -ForegroundColor Red
Write-Host "Iniciando limpeza profunda de processos e locks..." -ForegroundColor Yellow

# 1. Matar todos os processos Python e PowerShell relacionados as automacoes
$procToKill = Get-Process | Where-Object { 
    ($_.ProcessName -match "python" -and ($_.Path -match "Automacoes" -or $_.CommandLine -match "uvicorn" -or $_.CommandLine -match "worker.py")) -or
    ($_.ProcessName -match "powershell" -and ($_.CommandLine -match "Start-Orchestrator.ps1" -or $_.CommandLine -match "MonitorAutomacoes.ps1"))
}

foreach ($p in $procToKill) {
    Write-Host "  > Encerrando PID $($p.Id) ($($p.ProcessName))..." -ForegroundColor Gray
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

# 2. Limpar arquivos de controle stale
$pidFiles = Get-ChildItem -Path $OrchestratorDir -Filter "*.pid" -Recurse
foreach ($f in $pidFiles) {
    Write-Host "  > Removendo PID file: $($f.Name)" -ForegroundColor Gray
    Remove-Item $f.FullName -Force
}

# 3. Forcar Checkpoint do WAL via script minimalista
Write-Host "  > Consolidando banco de dados (WAL Checkpoint)..." -ForegroundColor Cyan
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
& $VenvPython -c "import sqlite3; conn=sqlite3.connect(r'$OrchestratorDir\automacoes.db'); conn.execute('PRAGMA wal_checkpoint(TRUNCATE)'); conn.close()"

# 4. Relancar Start-Orchestrator
Write-Host "Redistribuindo processos..." -ForegroundColor Green
$startScript = Join-Path $InfrastructureDir "Start-Orchestrator.ps1"
Start-Process "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$startScript`""

Write-Host "`nSistema reiniciado com sucesso via Rescue Mode." -ForegroundColor Green
Write-Host "Aguarde 15s para a API ficar online." -ForegroundColor White
