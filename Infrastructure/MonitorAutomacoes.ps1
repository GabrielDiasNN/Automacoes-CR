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

# --- CONFIGURACAO CENTRALIZADA ---
$HubPort = if (Get-Command Get-HubConfig -ErrorAction SilentlyContinue) { Get-HubConfig -Key "HUB_API_PORT" -Default "8000" } else { "8000" }
$HealthUrl = "http://127.0.0.1:$HubPort/"

# --- GERENCIAMENTO DE MUTEX (Instancia Unica) ---
$MutexName = if ([string]::IsNullOrWhiteSpace($MutexNameOverride)) { "Global\MonitorAutomacoesMutex" } else { $MutexNameOverride }
$script:MutexAcquired = $false
try {
    $script:MonitorMutex = New-Object System.Threading.Mutex($false, $MutexName)
    $script:MutexAcquired = $script:MonitorMutex.WaitOne([TimeSpan]::FromSeconds(5), $false)
} catch [System.Exception] {
    $script:MutexAcquired = $true
}

if (-not $script:MutexAcquired) {
    Write-Host "AVISO: Watchdog ja esta rodando." -ForegroundColor Yellow
    Exit 0
}

Write-Log "Watchdog iniciado v5.2.0. Vigiando Orquestrador em $HealthUrl"
$script:LastOrchestratorRestart = $null

while ($true) {
    try {
        $orchestratorStatus = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 5 -ErrorAction Stop
        if ($null -eq $orchestratorStatus -or $orchestratorStatus.scheduler_running -ne $true) {
            throw "Orquestrador respondeu mas o Scheduler esta inativo."
        }
        $script:LastOrchestratorRestart = $null
    }
    catch {
        $errReason = $_.Exception.Message
        $now = Get-Date
        if ($null -eq $script:LastOrchestratorRestart -or ($now - $script:LastOrchestratorRestart).TotalSeconds -gt 60) {
            Write-Log "Watchdog: Orquestrador inacessivel ou instavel ($errReason). Reiniciando..." -Type "WARN"
            $script:LastOrchestratorRestart = $now
            $startScript = Join-Path $InfrastructureDir "Start-Orchestrator.ps1"
            Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
            Start-Sleep -Seconds 15
        }
    }
    Start-Sleep -Seconds 20
}
