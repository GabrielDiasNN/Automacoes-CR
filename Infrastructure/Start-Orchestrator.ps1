$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = "." }

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OrchestratorDir = Join-Path $ProjectRoot "Orchestrator"
$LogDir = Join-Path $OrchestratorDir "Logs"

Import-Module (Join-Path $ProjectRoot "lib\Lib-OrchestratorRuntime.psm1") -Force
$RuntimeVersion = Get-OrchestratorRuntimeVersion -ProjectRoot $ProjectRoot

# Garantir diretorio de logs
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force }

# 0. CARREGAR CONFIGURACOES (.env) - Necessario para saber a porta antes do reset
$envPath = Join-Path $ProjectRoot ".env"
$HubPort = "8000"
if (Test-Path $envPath) {
    # Semantica alinhada a ConvertFrom-EnvLine (Lib-Config.psm1) e a
    # Get-OrchestratorEnvValue em 31/07/2026. Este laco tinha DUAS divergencias:
    # nao removia comentario inline (exportando "5511999999999   # Nome" como
    # valor) e usava '^#', que nao reconhece comentario indentado.
    Get-Content $envPath | Where-Object { $_ -match '=' -and $_ -notmatch '^\s*#' } | ForEach-Object {
        $parts = $_.Split('=', 2)
        $key = $parts[0].Trim()
        $val = [regex]::Replace($parts[1].Trim(), '\s+#.*$', '').Trim()
        $val = $val.Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        if ($key -eq "HUB_API_PORT") { $HubPort = $val }
    }
}

# 1. SURGICAL RESET - Pilar G: Limpeza cirurgica
Write-Host "[RESET] Realizando limpeza segura do ambiente ($RuntimeVersion)..." -ForegroundColor Gray

# Matar apenas processos Python ligados ao projeto para nao afetar outros sistemas no servidor
# Pede a parada gracioso ANTES de forcar: Stop-Process -Force nao entrega
# sinal no Windows, e sem isso o worker nunca finalizava as execucoes em voo
# nem matava seus powershell.exe filhos (que ficavam orfaos).
Request-OrchestratorGracefulStop -ProjectRoot $ProjectRoot | Out-Null
Stop-OrchestratorProcesses -ProjectRoot $ProjectRoot | Out-Null

# Liberar porta dinamica configurada — SOMENTE se o dono pertencer a este projeto.
# Ate 31/07/2026 todo OwningProcess retornado era encerrado com -Force sem
# verificacao de identidade: se a porta de HUB_API_PORT estivesse ocupada por
# outro servico do servidor, o start derrubava esse servico e o
# -ErrorAction SilentlyContinue apagava qualquer rastro.
$rootPattern = [regex]::Escape($ProjectRoot)
$portInUse = Get-NetTCPConnection -LocalPort $HubPort -ErrorAction SilentlyContinue
foreach ($ownerPid in @($portInUse.OwningProcess | Sort-Object -Unique)) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
    if ($null -eq $owner) { continue }

    $doProjeto = ($owner.CommandLine -match $rootPattern) -or
                 ($null -ne $owner.ExecutablePath -and $owner.ExecutablePath -match $rootPattern)
    if ($doProjeto) {
        Write-Host "[RESET] Liberando porta $HubPort (PID $ownerPid, $($owner.Name))." -ForegroundColor Gray
        Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
    }
    else {
        Write-Host "[AVISO] Porta $HubPort ocupada pelo PID $ownerPid ($($owner.Name)), que NAO pertence a este projeto. Nao sera encerrado — ajuste HUB_API_PORT no .env ou libere a porta manualmente." -ForegroundColor Yellow
    }
}

# Limpar lock files
Remove-Item (Join-Path $OrchestratorDir "*.pid") -Force -ErrorAction SilentlyContinue
# Sentinela de parada: se sobrou de um encerramento anterior, o worker que esta
# prestes a subir se encerraria no primeiro ciclo do laco.
Remove-Item (Join-Path $OrchestratorDir "worker.shutdown") -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 2. APLICAR MIGRACOES DO BANCO (Alembic - Sincrono)
Set-Location $OrchestratorDir
Write-Host "Garantindo schema atualizado do banco de dados (Alembic)..." -ForegroundColor Cyan
& $VenvPython -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao aplicar migracoes do Alembic. Startup cancelado para evitar inconsistencias."
}

# 3. INICIAR FASTAPI (Background)
Write-Host "Iniciando Central de Automacoes (API) na porta $HubPort..." -ForegroundColor Green
$apiLog = Join-Path $LogDir "uvicorn_startup.log"
$apiProcess = Start-Process -FilePath $VenvPython -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port $HubPort" -WindowStyle Hidden -PassThru -RedirectStandardError $apiLog
$apiProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "orchestrator.pid") -Encoding ascii -Force

# 4. VALIDAR STARTUP REAL DA API
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

# 5. INICIAR WORKER (Background - Garantido com Schema Pronto)
Write-Host "Iniciando Worker $RuntimeVersion (Zero-Latency)..." -ForegroundColor Cyan
$workerProcess = Start-Process -FilePath $VenvPython -ArgumentList "worker.py" -WindowStyle Hidden -PassThru
$workerProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "worker.pid") -Encoding ascii -Force

# 6. GARANTIR WATCHDOG (Monitor)
Write-Host "Ativando Watchdog $RuntimeVersion (Resiliencia)..." -ForegroundColor Cyan
$monitorScript = Join-Path $InfrastructureDir "MonitorAutomacoes.ps1"
Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$monitorScript`""

Write-Host "[OK] Sistema $RuntimeVersion reiniciado com sucesso." -ForegroundColor Green
Start-Sleep -Seconds 2
exit
