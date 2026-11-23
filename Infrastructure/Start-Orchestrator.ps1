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
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$StartupLog = Join-Path $LogDir "startup.log"
if ((Test-Path $StartupLog) -and ((Get-Item $StartupLog).Length -gt 1MB)) {
    Remove-Item $StartupLog -Force -ErrorAction SilentlyContinue
}

function Write-StartupLog {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    $ts = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
    $line = "[$ts] $Message"
    try {
        Add-Content -Path $StartupLog -Value $line -Encoding utf8 -ErrorAction SilentlyContinue
    } catch [System.Exception] {
        # Nao bloquear startup por falha de escrita em log auxiliar
    }
    Write-Host $Message -ForegroundColor $Color
}

function Start-WatchdogIfPresent {
    $monitorScript = Join-Path $InfrastructureDir "MonitorAutomacoes.ps1"
    if (Test-Path $monitorScript) {
        Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$monitorScript`""
    }
}

Write-StartupLog "=== Inicio do startup ($RuntimeVersion) ===" "Cyan"

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
        if ($key -eq "HUB_API_PORT" -and -not [string]::IsNullOrWhiteSpace($val)) { $HubPort = $val }
    }
}

# 1. SURGICAL RESET - Pilar G: Limpeza cirurgica
Write-StartupLog "[RESET] Realizando limpeza segura do ambiente ($RuntimeVersion)..." "Gray"

# Matar apenas processos Python ligados ao projeto para nao afetar outros sistemas no servidor
# Pede a parada gracioso ANTES de forcar: Stop-Process -Force nao entrega
# sinal no Windows, e sem isso o worker nunca finalizava as execucoes em voo
# nem matava seus powershell.exe filhos (que ficavam orfaos).
Request-OrchestratorGracefulStop -ProjectRoot $ProjectRoot | Out-Null
$killedCount = Stop-OrchestratorProcesses -ProjectRoot $ProjectRoot

# Liberar porta dinamica configurada — SOMENTE se o dono pertencer a este projeto.
# Ate 31/07/2026 todo OwningProcess retornado era encerrado com -Force sem
# verificacao de identidade: se a porta de HUB_API_PORT estivesse ocupada por
# outro servico do servidor, o start derrubava esse servico e o
# -ErrorAction SilentlyContinue apagava qualquer rastro.
$portCleared = $false
$rootPattern = [regex]::Escape($ProjectRoot)
$portInUse = Get-NetTCPConnection -LocalPort $HubPort -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 0 }
foreach ($ownerPid in @($portInUse.OwningProcess | Sort-Object -Unique)) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
    if ($null -eq $owner) { continue }

    $doProjeto = ($owner.CommandLine -match $rootPattern) -or
                 ($null -ne $owner.ExecutablePath -and $owner.ExecutablePath -match $rootPattern)
    if ($doProjeto) {
        Write-StartupLog "[RESET] Liberando porta $HubPort (PID $ownerPid, $($owner.Name))." "Gray"
        Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
        $portCleared = $true
    }
    else {
        Write-StartupLog "[AVISO] Porta $HubPort ocupada pelo PID $ownerPid ($($owner.Name)), que NAO pertence a este projeto. Nao sera encerrado — ajuste HUB_API_PORT no .env ou libere a porta manualmente." "Yellow"
    }
}

# Limpar lock files
Remove-Item (Join-Path $OrchestratorDir "*.pid") -Force -ErrorAction SilentlyContinue
# Sentinela de parada: se sobrou de um encerramento anterior, o worker que esta
# prestes a subir se encerraria no primeiro ciclo do laco.
Remove-Item (Join-Path $OrchestratorDir "worker.shutdown") -Force -ErrorAction SilentlyContinue
if ($killedCount -gt 0 -or $portCleared) {
    Start-Sleep -Seconds 2
}

try {
    # 2. INICIAR FASTAPI (Background)
    # O lifespan de app.main ja executa run_alembic_migrations() e
    # validate_database_schema() antes de responder /api/system/health,
    # evitando carregar Python/SQLAlchemy/Alembic duas vezes no boot frio.
    Set-Location $OrchestratorDir
    Write-StartupLog "Iniciando Central de Automacoes (API) na porta $HubPort..." "Green"
    $apiLog = Join-Path $LogDir "uvicorn_startup.log"
    $apiProcess = Start-Process -FilePath $VenvPython -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port $HubPort" -WindowStyle Hidden -PassThru -RedirectStandardError $apiLog
    $apiProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "orchestrator.pid") -Encoding ascii -Force

    # 4. VALIDAR STARTUP REAL DA API
    # `/api/system/health` publico virou liveness reduzido em [1.3.57]: `status`
    # vale `ok|degraded|unhealthy`, e `unhealthy` <=> DB ou scheduler fora (a mesma
    # condicao do antigo `database==online AND scheduler==executando`). Nao precisa
    # da chave aqui.
    # Deadline baseado em relogio (90s): em boot frio do Windows o import inicial
    # do FastAPI/SQLAlchemy pode passar de 35-40s.
    $healthUrl = "http://127.0.0.1:$HubPort/api/system/health"
    $apiReady = $false
    $apiDeadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $apiDeadline) {
        Start-Sleep -Seconds 1
        if (-not (Get-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue)) { break }
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 -ErrorAction Stop
            if ($health.status -and $health.status -ne "unhealthy") {
                $apiReady = $true
                break
            }
        } catch [System.Exception] {
            # A API ainda pode estar subindo; aguardar ate o deadline.
        }
    }
    if (-not $apiReady) {
        if ($null -ne $apiProcess -and -not $apiProcess.HasExited) {
            Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
        }
        $errTail = ""
        if (Test-Path $apiLog) {
            $errTail = (Get-Content $apiLog -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }
        throw "API nao ficou saudavel na porta $HubPort apos 90s. Ultimos logs: $errTail"
    }
    Write-StartupLog "API saudavel na porta $HubPort (PID $($apiProcess.Id))." "Green"

    # 5. INICIAR WORKER (Background - Garantido com Schema Pronto)
    Write-StartupLog "Iniciando Worker $RuntimeVersion (Zero-Latency)..." "Cyan"
    $workerProcess = Start-Process -FilePath $VenvPython -ArgumentList "worker.py" -WindowStyle Hidden -PassThru
    $workerProcess.Id | Out-File -FilePath (Join-Path $OrchestratorDir "worker.pid") -Encoding ascii -Force
}
catch [System.Exception] {
    Write-StartupLog "[ERRO] Falha no startup: $($_.Exception.Message)" "Red"
    # Garante que o Watchdog suba mesmo se o startup falhar no boot frio,
    # permitindo recuperacao automatica apos o cooldown.
    Start-WatchdogIfPresent
    throw
}

# 6. GARANTIR WATCHDOG (Monitor)
Write-StartupLog "Ativando Watchdog $RuntimeVersion (Resiliencia)..." "Cyan"
Start-WatchdogIfPresent

# 7. DAEMON WHATSAPP (opt-in via WHATSAPP_DAEMON_ENABLED=1). Nao fatal: falha vira aviso.
$daemonScript = Join-Path $InfrastructureDir "Start-WhatsAppDaemon.ps1"
try {
    & $daemonScript
    if ($LASTEXITCODE -ne 0) {
        Write-StartupLog "[AVISO] Daemon WhatsApp nao iniciado (exit $LASTEXITCODE). O Orchestrator segue sem ele." "Yellow"
    }
}
catch [System.Exception] {
    Write-StartupLog "[AVISO] Daemon WhatsApp: $($_.Exception.Message). O Orchestrator segue sem ele." "Yellow"
}

Write-StartupLog "[OK] Sistema $RuntimeVersion reiniciado com sucesso." "Green"
exit 0
