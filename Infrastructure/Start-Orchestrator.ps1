$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = "." }

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OrchestratorDir = Join-Path $ProjectRoot "Orchestrator"

# 1. Liberar porta 8766 se estiver ocupada (Force Upgrade)
$portInUse = Get-NetTCPConnection -LocalPort 8766 -ErrorAction SilentlyContinue
if ($portInUse) {
    $procId = $portInUse[0].OwningProcess
    Write-Host "[UPGRADE] Liberando porta 8766 (Encerrando PID $procId)..." -ForegroundColor Yellow
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# 2. Carregar segredos
$envPath = Join-Path $ProjectRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $parts = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
    }
}

# 3. Iniciar Worker em Background
Set-Location $OrchestratorDir
Write-Host "Iniciando Worker v4.0..." -ForegroundColor Cyan
$workerProcess = Start-Process -FilePath $VenvPython -ArgumentList "worker.py" -WindowStyle Hidden -PassThru
$workerProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "worker.pid") -Encoding ascii -Force

# 4. Iniciar FastAPI
Write-Host "Iniciando Hub Soberano v4.0.1 na porta 8766..." -ForegroundColor Green
Write-Host "Dashboard disponivel em: http://localhost:8766/dashboard" -ForegroundColor White
& $VenvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8766
