$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = "." }

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OrchestratorDir = Join-Path $ProjectRoot "Orchestrator"
$LogDir = Join-Path $OrchestratorDir "Logs"

# Garantir diretorio de logs
if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force }

# 1. HARD RESET (Pilar G) - Limpeza Atomica
Write-Host "[HARD RESET] Realizando limpeza profunda do ambiente..." -ForegroundColor Gray

# Taskkill forca o encerramento de todos os processos relacionados (ignoramos erros se ja estiver limpo)
try { taskkill /F /IM python.exe /T 2>$null } catch {}
try { taskkill /F /IM python3.12.exe /T 2>$null } catch {}
try { taskkill /F /IM py.exe /T 2>$null } catch {}

# Liberar porta 8000
$portInUse = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($portInUse) {
    $portInUse.OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}

# Limpar lock files
Remove-Item (Join-Path $OrchestratorDir "*.pid") -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 2. CARREGAR SEGREDOS
$envPath = Join-Path $ProjectRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $parts = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
    }
}

# 3. INICIAR WORKER (Background)
Set-Location $OrchestratorDir
Write-Host "Iniciando Worker v5.2..." -ForegroundColor Cyan
$workerProcess = Start-Process -FilePath $VenvPython -ArgumentList "worker.py" -WindowStyle Hidden -PassThru
$workerProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "worker.pid") -Encoding ascii -Force

# 4. INICIAR FASTAPI (Background)
Write-Host "Iniciando Central de Automa$([char]0xE7)$([char]0xF5)es (API)..." -ForegroundColor Green
$apiLog = Join-Path $LogDir "uvicorn_startup.log"
$apiProcess = Start-Process -FilePath $VenvPython -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WindowStyle Hidden -PassThru -RedirectStandardError $apiLog
$apiProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "orchestrator.pid") -Encoding ascii -Force

# 5. GARANTIR WATCHDOG (Monitor)
Write-Host "Ativando Watchdog de resiliencia (Monitor)..." -ForegroundColor Cyan
$monitorScript = Join-Path $InfrastructureDir "MonitorAutomacoes.ps1"
# Iniciamos o Monitor como processo independente
Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$monitorScript`""

Write-Host "[OK] Ambiente resetado e reiniciado com sucesso." -ForegroundColor Green
Start-Sleep -Seconds 2
exit
