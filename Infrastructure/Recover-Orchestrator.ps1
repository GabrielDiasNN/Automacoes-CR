$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
$OrchestratorDir = Join-Path $ProjectRoot "Orchestrator"

Import-Module (Join-Path $ProjectRoot "lib\Lib-OrchestratorRuntime.psm1") -Force
$RuntimeVersion = Get-OrchestratorRuntimeVersion -ProjectRoot $ProjectRoot

Write-Host "--- [RESCUE MODE: ORQUESTRADOR $RuntimeVersion] ---" -ForegroundColor Red
Write-Host "Iniciando limpeza profunda de processos e locks..." -ForegroundColor Yellow

# 1. Matar todos os processos Python e PowerShell relacionados as automacoes
$killed = Stop-OrchestratorProcesses -ProjectRoot $ProjectRoot -IncludeStarter
Write-Host "  > $killed processo(s) encerrado(s)." -ForegroundColor Gray

# 2. Limpar arquivos de controle stale
$pidFiles = Get-ChildItem -Path $OrchestratorDir -Filter "*.pid" -Recurse
foreach ($f in $pidFiles) {
    Write-Host "  > Removendo PID file: $($f.Name)" -ForegroundColor Gray
    Remove-Item $f.FullName -Force
}

# 3. Forcar Checkpoint do WAL via script minimalista
Write-Host "  > Consolidando banco de dados (WAL Checkpoint)..." -ForegroundColor Cyan
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DbPath = Join-Path $OrchestratorDir "automacoes.db"
if (Test-Path $DbPath) {
    & $VenvPython -c "import sqlite3, sys; conn=sqlite3.connect(sys.argv[1]); conn.execute('PRAGMA wal_checkpoint(TRUNCATE)'); conn.close()" $DbPath
} else {
    Write-Host "  > Banco nao encontrado em $DbPath; checkpoint ignorado." -ForegroundColor Yellow
}

# 4. Relancar Start-Orchestrator
Write-Host "Redistribuindo processos..." -ForegroundColor Green
$startScript = Join-Path $InfrastructureDir "Start-Orchestrator.ps1"
Start-Process "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$startScript`""

Write-Host "`nSistema reiniciado com sucesso via Rescue Mode." -ForegroundColor Green
Write-Host "Aguarde 15s para a API ficar online." -ForegroundColor White
