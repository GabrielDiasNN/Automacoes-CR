<#
.SYNOPSIS
    Nucleo de Monitoramento e Orquestracao (Automacoes Hub).
.DESCRIPTION
    Este e o servico central que gerencia o ciclo de vida de todas as automacoes:
    1. Hot-Reload: Recarrega configuracoes sem reiniciar.
    2. Scheduler: Dispara tarefas baseadas em janelas de tempo.
    3. Health & Metrics: Gera dashboards e snapshots de performance.
    4. Mutex: Garante instancia unica de monitoramento.
.NOTES
    Version: 3.7.0
    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-execution-contract
    Contract: monitor-trigger-action, base64-bridge-logs, preflight-v1
#>
param(
    [switch]$RunOnce,
    [switch]$SkipTaskExecution,
    [switch]$DryRun,
    [string]$MutexNameOverride = ""
)

$ErrorActionPreference = "Stop"

$ScriptPath = $PSScriptRoot
if (-not $ScriptPath) { $ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $ScriptPath) { $ScriptPath = "C:\Automacoes" }

# Bibliotecas e Dependencias Criticas
$libLogging = Join-Path $ScriptPath "lib\Lib-Logging.psm1"
$ConfigFilePath = Join-Path $ScriptPath "config.json"
$EmergencyLog = Join-Path $ScriptPath "Startup_Error.txt"

# --- BOOTSTRAP / PRE-FLIGHT (Self-Diagnosing) ---
if (Test-Path $libLogging) {
    Import-Module $libLogging -Force
    # O Monitor realiza o seu proprio Pre-Flight para garantir que o Hub esta saudavel
    $preFlight = Test-AutomationPreFlight -ExecId "bootstrap" -LogPath $EmergencyLog -CheckPaths @($ConfigFilePath)
    if (-not $preFlight) {
        Write-Host "ERRO CRITICO: Pre-Flight do Monitor falhou. Verifique $EmergencyLog" -ForegroundColor Red
        Exit 9
    }
} else {
    Write-Host "ERRO CRITICO: Biblioteca de log nao encontrada em $libLogging" -ForegroundColor Red
    Exit 1
}

# Configuracao Global de Encoding (Skill log-standardization)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# Forca o console host para UTF-8 (Blindagem visual no console/log)
try { if ($host.Name -eq "ConsoleHost") { chcp 65001 | Out-Null } } catch {}

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$script:MonitorExitCode = 0

# Helper para Log com suporte a Base64 e Auto-Masking (Skill log-standardization)
function Write-Log {
    param([string]$Msg, [string]$Type = "INFO", [string]$LogDir)
    
    if (-not $LogDir) { $LogDir = Get-LogDirectory }
    $fileName = "$(Get-Date -Format 'yyyy-MM')_Monitor.log"
    $logPath = Join-Path -Path $LogDir -ChildPath $fileName

    # Se a mensagem tiver acentos, transporta via Base64 Bridge
    if ($Msg -match '[\u00C0-\u00FF]') {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Msg)
        $b64 = [System.Convert]::ToBase64String($bytes)
        Write-AutomacaoLog -Message "B64:$b64" -Level $Type -ExecId "MONITOR" -LogPath $logPath
    } else {
        Write-AutomacaoLog -Message $Msg -Level $Type -ExecId "MONITOR" -LogPath $logPath
    }
}

# --- GERENCIAMENTO DE MUTEX (Instancia Unica) ---
$MutexName = if ([string]::IsNullOrWhiteSpace($MutexNameOverride)) { "Global\MonitorAutomacoesMutex" } else { $MutexNameOverride }
$MutexWaitSeconds = 5
$script:MutexAcquired = $false

try {
    $script:MonitorMutex = New-Object System.Threading.Mutex($false, $MutexName)
    $script:MutexAcquired = $script:MonitorMutex.WaitOne([TimeSpan]::FromSeconds($MutexWaitSeconds), $false)
}
catch [System.Threading.AbandonedMutexException] {
    $script:MutexAcquired = $true
    Write-Log "Mutex abandonado detectado. Assumindo controle desta instancia." -Type "WARN"
}
catch {
    Write-Log "Falha ao adquirir Mutex: $_" -Type "ERRO"
    Exit 1
}

if (-not $script:MutexAcquired) {
    Write-Host "AVISO: Outra instancia do Monitor ja esta ativa ($MutexName)." -ForegroundColor Yellow
    Exit 0
}

# --- ESTADO INICIAL ---
if (Test-Path $EmergencyLog) { Remove-Item $EmergencyLog -ErrorAction SilentlyContinue }

$script:Config = $null
$script:ConfigLastWrite = $null
$script:ConfigHash = $null
$script:RunningTasks = @{}
$script:StateControl = @{}
$script:MainLoopConsecutiveErrors = 0
$script:MainLoopMaxConsecutiveErrors = 5
$script:Metrics = @{ TasksTriggered = 0; TasksDryRunEligible = 0; TasksSkippedOverlap = 0; TasksCompleted = 0; TasksFinishedNonZero = 0; TasksFinishedWarn = 0; ExitCode7ReadOnly = 0; ExitCode23Cooldown = 0; ExitCode40Concurrent = 0; ConfigReloadSuccess = 0; ConfigReloadFailure = 0 }
$script:MetricsWindow = @{ TasksTriggered = 0; TasksDryRunEligible = 0; TasksSkippedOverlap = 0; TasksCompleted = 0; TasksFinishedNonZero = 0; TasksFinishedWarn = 0; ExitCode7ReadOnly = 0; ExitCode23Cooldown = 0; ExitCode40Concurrent = 0; ConfigReloadSuccess = 0; ConfigReloadFailure = 0 }
$script:MetricsWindowStartedAt = Get-Date
$script:TaskLastResult = @{}
$script:TaskHistory = @{}
$script:TaskHistoryLimit = 50
$script:MonitorStartedAt = Get-Date
$script:LastConfigReloadAt = $null
$script:LastConfigReloadStatus = "N/A"
$script:LastHeartbeatAt = $script:MonitorStartedAt
$script:OperationsApiToken = [guid]::NewGuid().ToString("N")
$script:DashboardOutputPath = Join-Path $ScriptPath "Dashboard\dashboard.html"
$script:DashboardSettings = [ordered]@{ enabled = $true; mode = "modern"; refreshSeconds = 60; historyLimitPerTask = 50; scheduleDelayToleranceMinutes = 5 }

function Get-LogDirectory {
    if ($script:Config -and $script:Config.settings -and $script:Config.settings.logDirectory) { return [string]$script:Config.settings.logDirectory }
    return (Join-Path $ScriptPath "Logs")
}

function Update-Configuration {
    param([switch]$Force)
    if (-not (Test-Path $ConfigFilePath)) { Write-Log "Arquivo config.json nao encontrado." -Type "ERRO"; return $false }
    $currentHash = ""
    try {
        $stream = [System.IO.File]::OpenRead($ConfigFilePath)
        $sha = New-Object System.Security.Cryptography.SHA256Managed
        $currentHash = [System.BitConverter]::ToString($sha.ComputeHash($stream)).Replace("-", "")
        $stream.Close(); $stream.Dispose()
    } catch { return $false }

    if ($Force -or $currentHash -ne $script:ConfigHash) {
        try {
            $raw = Get-Content $ConfigFilePath -Raw -Encoding UTF8
            $script:Config = $raw | ConvertFrom-Json
            $script:ConfigHash = $currentHash
            Write-Log "Configuracao carregada. Tarefas: $($script:Config.tasks.Count) | Hash=$($currentHash.Substring(0,8))"
            return $true
        } catch {
            Write-Log "Falha ao carregar config.json: $_" -Type "ERRO"
            return $false
        }
    }
    return $true
}

function Remove-FinishedTask {
    $toRemove = @()
    foreach ($taskName in $script:RunningTasks.Keys) {
        $record = $script:RunningTasks[$taskName]
        $proc = if ($record -is [hashtable]) { $record.Proc } else { $record }
        if ($proc.HasExited) {
            $exitCode = $proc.ExitCode
            Write-Log "Tarefa '$taskName' finalizada. ExitCode=$exitCode PID=$($proc.Id)"
            $toRemove += $taskName
        }
    }
    foreach ($name in $toRemove) { $script:RunningTasks.Remove($name) | Out-Null }
}

function Invoke-ScheduledTask {
    param($Task, [datetime]$Now)
    $taskName = [string]$Task.name
    if ($script:RunningTasks.ContainsKey($taskName)) { return }
    
    # Resolve caminho dinamico (Skill: ai-native-development-standard)
    $rawPath = [string]$Task.scriptPath
    $absPath = if ([System.IO.Path]::IsPathRooted($rawPath)) { $rawPath } else { Join-Path $ScriptPath $rawPath }

    Write-Log "DISPARANDO: $taskName ($absPath)"
    $execId = New-ExecId
    try {
        $proc = Start-Process "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$absPath`" `"$execId`"" -WindowStyle Hidden -PassThru
        $script:RunningTasks[$taskName] = @{ Proc = $proc; StartedAt = $Now }
        $script:StateControl[$taskName] = $Now.ToString("yyyy-MM-dd HH:mm")
    } catch {
        Write-Log "Falha ao iniciar '$taskName': $_" -Type "ERRO"
    }
}

function Test-TaskExecution {
    param($Task, [datetime]$Now, [string]$TimeKey)
    if (-not $Task.enabled) { return $false }
    if ($Task.schedule.minutes -notcontains $Now.Minute) { return $false }
    if ($script:StateControl[[string]$Task.name] -eq $TimeKey) { return $false }
    return $true
}

# --- LOOP PRINCIPAL ---
Update-Configuration -Force | Out-Null
Write-Log "Monitor iniciado v3.7.0. Modo=$(if ($RunOnce){'RunOnce'}else{'Continuo'})"

while ($true) {
    try {
        Remove-FinishedTask
        Update-Configuration | Out-Null
        $agora = Get-Date
        $timeKey = $agora.ToString("yyyy-MM-dd HH:mm")

        foreach ($task in $script:Config.tasks) {
            if (Test-TaskExecution -Task $task -Now $agora -TimeKey $timeKey) {
                Invoke-ScheduledTask -Task $task -Now $agora
            }
        }

        if ($RunOnce) { break }
        Start-Sleep -Seconds 20
    }
    catch {
        Write-Log "ERRO NO LOOP: $_" -Type "ERRO"
        Start-Sleep -Seconds 30
    }
}

if ($script:MonitorMutex) { $script:MonitorMutex.ReleaseMutex(); $script:MonitorMutex.Dispose() }
Exit $script:MonitorExitCode
