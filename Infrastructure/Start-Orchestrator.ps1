$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = "." }

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OrchestratorDir = Join-Path $ProjectRoot "Orchestrator"

# 1. Liberar porta 8000 se estiver ocupada (Force Upgrade)
$portInUse = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($portInUse) {
    foreach ($conn in $portInUse) {
        $procId = $conn.OwningProcess
        if ($procId -gt 0) {
            Write-Host "[UPGRADE] Liberando porta 8000 (Encerrando PID $procId)..." -ForegroundColor Yellow
            try { 
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue 
                taskkill /F /PID $procId /T 2>$null
            } catch {}
        }
    }
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

# 3. Encerrar Worker anterior se existir (Pilar G)
$workerPidFile = Join-Path $OrchestratorDir "worker.pid"
if (Test-Path $workerPidFile) {
    $oldPid = (Get-Content $workerPidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "[RESET] Encerrando Worker anterior (PID $oldPid)..." -ForegroundColor Yellow
        try {
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            taskkill /F /PID $oldPid /T 2>$null
        } catch {}
    }
}

# 4. Iniciar Worker em Background
Set-Location $OrchestratorDir
Write-Host "Iniciando Worker v5.2 (Hardenized)..." -ForegroundColor Cyan
$workerProcess = Start-Process -FilePath $VenvPython -ArgumentList "worker.py" -WindowStyle Hidden -PassThru
$workerProcess.Id | Out-File -FilePath $workerPidFile -Encoding ascii -Force

# 4. Iniciar FastAPI
Write-Host "Iniciando Central de Automa$([char]0xE7)$([char]0xF5)es v5.0.0 na porta 8000 (Localhost)..." -ForegroundColor Green
Write-Host "Dashboard disponiv$([char]0xED)l em: http://localhost:8000/dashboard" -ForegroundColor White

& $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
