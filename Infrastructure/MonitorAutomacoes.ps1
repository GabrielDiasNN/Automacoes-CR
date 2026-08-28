<#
.SYNOPSIS
    Watchdog do Orquestrador FastAPI (versão lida de Orchestrator/app/constants.py).
.DESCRIPTION
    Script responsavel por garantir que a API e o Worker estejam sempre online.
    Utiliza a porta dinamica do .env para monitoramento.
#>
param([string]$MutexNameOverride = "")

$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = "." }

# Bibliotecas (apenas logging basico)
$libLogging = Join-Path $ProjectRoot "lib\Lib-Logging.psm1"
if (Test-Path $libLogging) { Import-Module $libLogging -Force }
Import-Module (Join-Path $ProjectRoot "lib\Lib-OrchestratorRuntime.psm1") -Force
$RuntimeVersion = Get-OrchestratorRuntimeVersion -ProjectRoot $ProjectRoot

function Write-Log {
    param([string]$Msg, [string]$Type = "INFO")
    $logPath = Join-Path $ProjectRoot "Logs\$(Get-Date -Format 'yyyy-MM')_Monitor.log"
    if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
        Write-AutomacaoLog -Message $Msg -Level $Type -ExecId "WATCHDOG" -LogPath $logPath
    } else {
        $ts = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
        "[$ts] [$Type] [WATCHDOG] $Msg" | Out-File -FilePath $logPath -Append -Encoding utf8
    }
}

# --- CARREGAR CONFIGURACOES (.env) ---
$HubPort = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "HUB_API_PORT" -Default "8000"
$ApiKey  = Get-OrchestratorEnvValue -ProjectRoot $ProjectRoot -Key "ORCHESTRATOR_API_KEY"

# Endpoint de Health completo (autenticado). Desde [1.3.57] a rota pública
# `/api/system/health` é só liveness (`status`); DB/scheduler/worker vivem em
# `/health/full`, que exige `X-API-Key` (já enviado abaixo).
$HealthUrl = "http://127.0.0.1:$HubPort/api/system/health/full"

# --- GERENCIAMENTO DE MUTEX (Instancia Unica) ---
$MutexName = if ([string]::IsNullOrWhiteSpace($MutexNameOverride)) { "Global\MonitorAutomacoesMutex" } else { $MutexNameOverride }
$script:MutexAcquired = $false
try {
    $script:MonitorMutex = New-Object System.Threading.Mutex($false, $MutexName)
    $script:MutexAcquired = $script:MonitorMutex.WaitOne([TimeSpan]::FromSeconds(5), $false)
} catch [System.Exception] { $script:MutexAcquired = $true }

if (-not $script:MutexAcquired) {
    Write-Host "AVISO: Watchdog $RuntimeVersion ja esta rodando." -ForegroundColor Yellow
    Exit 0
}

Write-Log "Watchdog $RuntimeVersion iniciado. Monitorando porta $HubPort"
Start-Sleep -Seconds 15 # Aguardar startup inicial
$script:LastOrchestratorRestart = $null
$script:LastWorkerRecover = $null

$script:ConsecutiveHealthFailures = 0

while ($true) {
    $healthSuccess = $false
    $errReason = ""
    $isAuthError = $false

    # Pilar E/V: Probe resiliente com 3 tentativas consecutivas para evitar falsos positivos
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $headers = @{ "X-API-Key" = $ApiKey }
            $health = Invoke-RestMethod -Uri $HealthUrl -Headers $headers -TimeoutSec 25 -ErrorAction Stop

            if ($health.database -ne "online" -or $health.scheduler -ne "executando") {
                throw "API respondeu, mas componentes internos em falha: DB=$($health.database), Sched=$($health.scheduler)"
            }

            $healthSuccess = $true
            $script:ConsecutiveHealthFailures = 0
            break
        }
        catch [System.Exception] {
            $errReason = $_.Exception.Message
            $statusCode = 0
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $statusCode = [int]$_.Exception.Response.StatusCode
            } elseif ($_.Exception.StatusCode) {
                $statusCode = [int]$_.Exception.StatusCode
            }

            if ($statusCode -eq 403 -or $statusCode -eq 401) {
                $isAuthError = $true
                break # Erro de credencial nao deve retentar nem reiniciar o servico
            }

            if ($attempt -lt 3) {
                Start-Sleep -Seconds 3
            }
        }
    }

    if ($isAuthError) {
        Write-Log "Watchdog: Falha de autenticacao (403) com a API na porta $HubPort. Verifique a ORCHESTRATOR_API_KEY no .env." -Type "WARN"
        Start-Sleep -Seconds 45
        continue
    }

    if ($healthSuccess) {
        # Verificar se o Worker esta respondendo ao ping (heartbeat).
        if ($health.worker.is_alive -eq $false) {
            $now = Get-Date
            if ($null -eq $script:LastWorkerRecover -or ($now - $script:LastWorkerRecover).TotalSeconds -gt 180) {
                Write-Log "Worker Engine sem heartbeat com API operacional. Acionando recuperacao do worker..." -Type "WARN"
                $script:LastWorkerRecover = $now
                try {
                    $recoverUrl = "http://127.0.0.1:$HubPort/api/system/worker/recover"
                    Invoke-RestMethod -Uri $recoverUrl -Method Post -Headers $headers -TimeoutSec 30 -ErrorAction Stop | Out-Null
                    Write-Log "Recuperacao do worker solicitada com sucesso." -Type "INFO"
                }
                catch [System.Exception] {
                    Write-Log "Falha ao acionar recuperacao do worker: $($_.Exception.Message)" -Type "ERRO"
                }
            }
            else {
                Write-Log "Worker ainda sem heartbeat; aguardando cooldown da recuperacao anterior." -Type "WARN"
            }
        }
        else {
            $script:LastWorkerRecover = $null
        }

        $script:LastOrchestratorRestart = $null
    }
    else {
        $script:ConsecutiveHealthFailures++
        $now = Get-Date
        # Cooldown de 180 segundos para evitar loops de reinicio infinito (Pilar E)
        if ($null -eq $script:LastOrchestratorRestart -or ($now - $script:LastOrchestratorRestart).TotalSeconds -gt 180) {
            Write-Log "Watchdog: Orquestrador inacessivel na porta $HubPort apos 3 tentativas ($errReason). Reiniciando..." -Type "WARN"
            $script:LastOrchestratorRestart = $now
            $startScript = Join-Path $InfrastructureDir "Start-Orchestrator.ps1"
            Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
            Start-Sleep -Seconds 30
        }
    }
    Start-Sleep -Seconds 45
}

