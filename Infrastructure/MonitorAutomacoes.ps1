<#
.SYNOPSIS
    Watchdog do Orquestrador FastAPI v6.2.0.
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

function Write-Log {
    param([string]$Msg, [string]$Type = "INFO")
    $logPath = Join-Path $ProjectRoot "Logs\$(Get-Date -Format 'yyyy-MM')_Monitor.log"
    if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
        Write-AutomacaoLog -Message $Msg -Level $Type -ExecId "WATCHDOG" -LogPath $logPath
    } else {
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        "[$ts] [$Type] [WATCHDOG] $Msg" | Out-File -FilePath $logPath -Append -Encoding utf8
    }
}

# --- CARREGAR CONFIGURACOES (.env) ---
$envPath = Join-Path $ProjectRoot ".env"
$HubPort = "8000"
$ApiKey  = ""

if (Test-Path $envPath) {
    Get-Content $envPath | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $parts = $_.Split('=', 2)
        $k = $parts[0].Trim()
        $v = $parts[1].Trim().Trim('"').Trim("'")
        if ($k -eq "HUB_API_PORT") { $HubPort = $v }
        if ($k -eq "ORCHESTRATOR_API_KEY") { $ApiKey = $v }
    }
}

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
    Write-Host "AVISO: Watchdog v6.2.0 ja esta rodando." -ForegroundColor Yellow
    Exit 0
}

Write-Log "Watchdog v6.2.0 iniciado. Monitorando porta $HubPort"
Start-Sleep -Seconds 15 # Aguardar startup inicial
$script:LastOrchestratorRestart = $null

while ($true) {
    try {
        # Validacao autenticada (Pilar V)
        $headers = @{ "X-API-Key" = $ApiKey }
        $health = Invoke-RestMethod -Uri $HealthUrl -Headers $headers -TimeoutSec 10 -ErrorAction Stop

        # Verificacao de integridade dos componentes vitais
        if ($health.database -ne "online" -or $health.scheduler -ne "executando") {
            throw "API respondeu, mas componentes internos em falha: DB=$($health.database), Sched=$($health.scheduler)"
        }
        
        # Verificar se o Worker esta respondendo ao ping (heartbeat)
        if ($health.worker.is_alive -eq $false) {
             Write-Log "Alerta: Worker Engine parou de enviar Heartbeat. API operacional." -Type "WARN"
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
