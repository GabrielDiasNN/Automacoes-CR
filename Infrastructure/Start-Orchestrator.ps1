$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = "." }

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OrchestratorDir = Join-Path $ProjectRoot "Orchestrator"
$LogDir = Join-Path $OrchestratorDir "Logs"
$RuntimeVersion = "v6.5.4"

# Garantir diretorio de logs
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force }

# 0. CARREGAR CONFIGURACOES (.env) - Necessario para saber a porta antes do reset
$envPath = Join-Path $ProjectRoot ".env"
$HubPort = "8000"
if (Test-Path $envPath) {
    Get-Content $envPath | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $parts = $_.Split('=', 2)
        $key = $parts[0].Trim()
        $val = $parts[1].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        if ($key -eq "HUB_API_PORT") { $HubPort = $val }
    }
}

# 1. SURGICAL RESET - Pilar G: Limpeza cirurgica
Write-Host "[RESET] Realizando limpeza segura do ambiente ($RuntimeVersion)..." -ForegroundColor Gray

# Matar apenas processos Python ligados ao projeto para nao afetar outros sistemas no servidor
$CurrentPid = $PID
$procToKill = Get-Process | Where-Object {
    $_.Id -ne $CurrentPid -and (
        ($_.ProcessName -match "python" -and ($_.Path -match "Automacoes" -or $_.CommandLine -match "uvicorn" -or $_.CommandLine -match "worker.py")) -or
        ($_.ProcessName -match "powershell" -and ($_.CommandLine -match "MonitorAutomacoes.ps1"))
    )
}

foreach ($p in $procToKill) {
    try {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    } catch [System.InvalidOperationException] {
        Write-Verbose ("Processo {0} ja finalizado durante a limpeza." -f $p.Id)
    }
}

# Liberar porta dinamica configurada
$portInUse = Get-NetTCPConnection -LocalPort $HubPort -ErrorAction SilentlyContinue
if ($portInUse) {
    $portInUse.OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}

# Limpar lock files
Remove-Item (Join-Path $OrchestratorDir "*.pid") -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 3. INICIAR WORKER (Background)
Set-Location $OrchestratorDir
Write-Host "Iniciando Worker $RuntimeVersion (Zero-Latency)..." -ForegroundColor Cyan
$workerProcess = Start-Process -FilePath $VenvPython -ArgumentList "worker.py" -WindowStyle Hidden -PassThru
$workerProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "worker.pid") -Encoding ascii -Force

# 4. INICIAR FASTAPI (Background)
Write-Host "Iniciando Central de Automacoes (API) na porta $HubPort..." -ForegroundColor Green
$apiLog = Join-Path $LogDir "uvicorn_startup.log"
$apiProcess = Start-Process -FilePath $VenvPython -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port $HubPort" -WindowStyle Hidden -PassThru -RedirectStandardError $apiLog
$apiProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "orchestrator.pid") -Encoding ascii -Force

# 5. VALIDAR STARTUP REAL DA API
$healthUrl = "http://127.0.0.1:$HubPort/api/system/health"
$apiReady = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    if (-not (Get-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue)) { break }
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 -ErrorAction Stop
        if ($health.database -eq "online" -and $health.scheduler -eq "executando") {
            $apiReady = $true
            break
        }
    } catch [System.Exception] {
        # A API ainda pode estar subindo; aguardar ate o limite do loop.
    }
}
if (-not $apiReady) {
    $errTail = ""
    if (Test-Path $apiLog) {
        $errTail = (Get-Content $apiLog -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
    }
    throw "API nao ficou saudavel na porta $HubPort apos restart. Ultimos logs: $errTail"
}

# 6. GARANTIR WATCHDOG (Monitor)
Write-Host "Ativando Watchdog $RuntimeVersion (Resiliencia)..." -ForegroundColor Cyan
$monitorScript = Join-Path $InfrastructureDir "MonitorAutomacoes.ps1"
Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$monitorScript`""

Write-Host "[OK] Sistema $RuntimeVersion reiniciado com sucesso." -ForegroundColor Green
Start-Sleep -Seconds 2
exit
