<#
.SYNOPSIS
    Watchdog do Orquestrador FastAPI.
.DESCRIPTION
    Script minimalista responsavel apenas por garantir que o Python (Orquestrador)
    esteja sempre rodando. Toda a logica de agendamento e geracao de estado foi
    migrada para o FastAPI (Fase 1 do Plano de Evolucao).
#>
param([string]$MutexNameOverride = "")

$ErrorActionPreference = "Stop"
$InfrastructureDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InfrastructureDir
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = "." }

# Bibliotecas (apenas logging basico)
$libLogging = Join-Path $ProjectRoot "lib\Lib-Logging.psm1"
$libConfig  = Join-Path $ProjectRoot "lib\Lib-Config.psm1"
if (Test-Path $libLogging) { Import-Module $libLogging -Force }
if (Test-Path $libConfig)  { Import-Module $libConfig  -Force }

function Write-Log {
    param([string]$Msg, [string]$Type = "INFO")
    $logPath = Join-Path $ProjectRoot "Logs\$(Get-Date -Format 'yyyy-MM')_Monitor.log"
    Write-AutomacaoLog -Message $Msg -Level $Type -ExecId "WATCHDOG" -LogPath $logPath
}

# --- CARREGAR CONFIGURACOES (.env) ---
$envPath = Join-Path $ProjectRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $parts = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
    }
}

$HubPort = $env:HUB_API_PORT
if (-not $HubPort) { $HubPort = "8000" }
$ApiKey  = $env:ORCHESTRATOR_API_KEY

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
    Write-Host "AVISO: Watchdog ja esta rodando." -ForegroundColor Yellow
    Exit 0
}

Write-Log "Watchdog iniciado v5.2.3. Vigiando Orquestrador em $HealthUrl"
Start-Sleep -Seconds 10 # Tempo rapido de estabilizacao
$script:LastOrchestratorRestart = $null

while ($true) {
    try {
        # Validacao autenticada (Pilar V)
        $headers = @{ "X-API-Key" = $ApiKey }
        $health = Invoke-RestMethod -Uri $HealthUrl -Headers $headers -TimeoutSec 5 -ErrorAction Stop

        if ($health.database -ne "online" -or $health.scheduler -ne "executando") {
            throw "Sinal de vida OK, mas componentes internos falharam: DB=$($health.database), Sched=$($health.scheduler)"
        }
        $script:LastOrchestratorRestart = $null
    }
    catch [System.Exception] {
        $errReason = $_.Exception.Message
        $now = Get-Date
        # Cooldown de 120 segundos para evitar loops de reinicio infinito (Pilar E)
        if ($null -eq $script:LastOrchestratorRestart -or ($now - $script:LastOrchestratorRestart).TotalSeconds -gt 120) {
            Write-Log "Watchdog: Orquestrador instavel ou inacessivel ($errReason). Reiniciando..." -Type "WARN"
            $script:LastOrchestratorRestart = $now
            $startScript = Join-Path $InfrastructureDir "Start-Orchestrator.ps1"
            Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
            Start-Sleep -Seconds 20
        }
    }
    Start-Sleep -Seconds 30
}

