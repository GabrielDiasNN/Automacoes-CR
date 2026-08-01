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

# Endpoint de Health real
$HealthUrl = "http://127.0.0.1:$HubPort/api/system/health"

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

while ($true) {
    try {
        # Validacao autenticada (Pilar V)
        $headers = @{ "X-API-Key" = $ApiKey }
        $health = Invoke-RestMethod -Uri $HealthUrl -Headers $headers -TimeoutSec 10 -ErrorAction Stop

        # Verificacao de integridade dos componentes vitais
        if ($health.database -ne "online" -or $health.scheduler -ne "executando") {
            throw "API respondeu, mas componentes internos em falha: DB=$($health.database), Sched=$($health.scheduler)"
        }
        
        # Verificar se o Worker esta respondendo ao ping (heartbeat).
        # Ate 31/07/2026 este ramo APENAS logava um WARN: com a API saudavel e o
        # worker morto, o unico caminho de reinicio (o catch abaixo) nunca
        # disparava e a fila ficava parada indefinidamente — exatamente o
        # cenario para o qual /api/system/worker/recover existe, mas que ninguem
        # acionava sem um humano olhando o dashboard.
        if ($health.worker.is_alive -eq $false) {
            $now = Get-Date
            # Cooldown proprio, separado do reinicio total do Orquestrador.
            if ($null -eq $script:LastWorkerRecover -or ($now - $script:LastWorkerRecover).TotalSeconds -gt 180) {
                Write-Log "Worker Engine sem heartbeat com API operacional. Acionando recuperacao do worker..." -Type "WARN"
                $script:LastWorkerRecover = $now
                try {
                    # Recupera SOMENTE o worker. Reiniciar o Orquestrador inteiro
                    # derrubaria tambem a API e as execucoes em voo.
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
    catch [System.Exception] {
        $errReason = $_.Exception.Message
        $now = Get-Date
        # Cooldown de 180 segundos para evitar loops de reinicio infinito (Pilar E)
        if ($null -eq $script:LastOrchestratorRestart -or ($now - $script:LastOrchestratorRestart).TotalSeconds -gt 180) {
            Write-Log "Watchdog: Orquestrador inacessivel na porta $HubPort ($errReason). Reiniciando..." -Type "WARN"
            $script:LastOrchestratorRestart = $now
            $startScript = Join-Path $InfrastructureDir "Start-Orchestrator.ps1"
            # Disparar reinicio seguro
            Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
            Start-Sleep -Seconds 30
        }
    }
    Start-Sleep -Seconds 45
}
