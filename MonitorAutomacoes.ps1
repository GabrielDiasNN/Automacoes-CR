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
if (-not $ScriptPath) { $ScriptPath = "." }

# Bibliotecas e Dependencias Criticas
$libLogging = Join-Path $ScriptPath "lib\Lib-Logging.psm1"
$libRetry  = Join-Path $ScriptPath "lib\Lib-Retry.psm1"
$libEmail  = Join-Path $ScriptPath "lib\Lib-Email.psm1"
$ConfigFilePath = Join-Path $ScriptPath "config.json"
$EmergencyLog = Join-Path $ScriptPath "Startup_Error.txt"

# --- BOOTSTRAP / PRE-FLIGHT (Self-Diagnosing) ---
if (Test-Path $libLogging) {
    Import-Module $libLogging -Force
    if (Test-Path $libRetry)  { Import-Module $libRetry  -Force }
    if (Test-Path $libEmail)  { Import-Module $libEmail  -Force }
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
try { if ($host.Name -eq "ConsoleHost") { chcp 65001 | Out-Null } } catch [System.Exception] {}

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
catch [System.Exception] {
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

# --- RETRY QUEUE (VALEG: A-Arquitetura, Retry em Duas Camadas) ---
# Estrutura: taskName -> { Attempts; MaxAttempts; BackoffSeconds; RetryOnExitCodes; NextRetryAt; OriginalExecId; AlertOnDefinitive }
$script:RetryQueue = @{}

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
    } catch [System.Exception] { return $false }

    if ($Force -or $currentHash -ne $script:ConfigHash) {
        try {
            $raw = Get-Content $ConfigFilePath -Raw -Encoding UTF8
            $script:Config = $raw | ConvertFrom-Json
            $script:ConfigHash = $currentHash
            Write-Log "Configuracao carregada. Tarefas: $($script:Config.tasks.Count) | Hash=$($currentHash.Substring(0,8))"
            return $true
        } catch [System.Exception] {
            Write-Log "Falha ao carregar config.json: $_" -Type "ERRO"
            return $false
        }
    }
    return $true
}

function Remove-FinishedTask {
    $toRemove = @()
    $agora = Get-Date
    foreach ($taskName in $script:RunningTasks.Keys) {
        $record = $script:RunningTasks[$taskName]
        $proc = if ($record -is [hashtable]) { $record.Proc } else { $record }
        if ($proc.HasExited) {
            $exitCode = $proc.ExitCode
            $startedAt = if ($record -is [hashtable]) { $record.StartedAt } else { $agora }
            $duration = [math]::Round(($agora - $startedAt).TotalSeconds, 1)
            
            Write-Log "Tarefa '$taskName' finalizada. ExitCode=$exitCode PID=$($proc.Id) Duracao=$($duration)s"
            
            # Atualiza Metricas
            $script:Metrics.TasksCompleted++
            $script:MetricsWindow.TasksCompleted++
            if ($exitCode -ne 0) {
                $script:Metrics.TasksFinishedNonZero++
                $script:MetricsWindow.TasksFinishedNonZero++

                # --- RETRY QUEUE: Enfileirar retry se configurado para este ExitCode ---
                $taskConfig = $script:Config.tasks | Where-Object { [string]$_.name -eq $taskName }
                if ($taskConfig -and $taskConfig.retryOnFailure -and $taskConfig.retryOnFailure.enabled) {
                    $retryConf = $taskConfig.retryOnFailure
                    $retryOnCodes = @($retryConf.retryOnExitCodes)
                    
                    if ($retryOnCodes -contains $exitCode) {
                        if (-not $script:RetryQueue.ContainsKey($taskName)) {
                            # Primeira falha: inicializa fila
                            $execIdOriginal = if ($record -is [hashtable] -and $record.ExecId) { $record.ExecId } else { "MONITOR" }
                            $script:RetryQueue[$taskName] = @{
                                Attempts          = 0
                                MaxAttempts       = [int]$retryConf.maxAttempts
                                BackoffSeconds    = @($retryConf.backoffSeconds)
                                RetryOnExitCodes  = $retryOnCodes
                                AlertOnDefinitive = [bool]$retryConf.alertOnDefinitiveFailure
                                OriginalExecId    = $execIdOriginal
                                LastExitCode      = $exitCode
                                NextRetryAt       = $null
                            }
                        }
                        
                        $q = $script:RetryQueue[$taskName]
                        $q.Attempts++
                        $q.LastExitCode = $exitCode
                        
                        if ($q.Attempts -ge $q.MaxAttempts) {
                            # Esgotou retries: alerta definitivo
                            Write-Log "[RETRY_ESGOTADO] '$taskName' falhou definitivamente apos $($q.MaxAttempts) tentativas. ExitCode=$exitCode" -Type "ERRO"
                            if ($q.AlertOnDefinitive) {
                                try {
                                    $alertLogPath = Join-Path (Get-LogDirectory) "$(Get-Date -Format 'yyyy-MM')_Monitor.log"
                                    Send-AlertaFalhaDefinitiva -TaskName $taskName -ExecId $q.OriginalExecId `
                                        -UltimoErro "ExitCode=$exitCode (apos $($q.MaxAttempts) tentativas)" `
                                        -Tentativas $q.MaxAttempts -LogPath $alertLogPath
                                } catch [System.Exception] {
                                    Write-Log "Falha ao enviar alerta definitivo: $_" -Type "WARN"
                                }
                            }
                            $script:RetryQueue.Remove($taskName)
                        } else {
                            # Agenda proximo retry com backoff
                            $backoffIdx = [Math]::Min($q.Attempts - 1, $q.BackoffSeconds.Count - 1)
                            $waitSec = $q.BackoffSeconds[$backoffIdx]
                            $q.NextRetryAt = $agora.AddSeconds($waitSec)
                            Write-Log "[RETRY] '$taskName' agendado para retry $($q.Attempts)/$($q.MaxAttempts) em ${waitSec}s (as $($q.NextRetryAt.ToString('HH:mm:ss'))). ExitCode anterior=$exitCode" -Type "WARN"
                        }
                    } else {
                        # ExitCode nao esta na lista de retry (ex: 0, 2, 23, 40) - limpa fila se existia
                        if ($script:RetryQueue.ContainsKey($taskName)) { $script:RetryQueue.Remove($taskName) }
                    }
                }
            } else {
                # Sucesso: limpa qualquer estado de retry pendente
                if ($script:RetryQueue.ContainsKey($taskName)) {
                    Write-Log "[RETRY] '$taskName' concluiu com sucesso. Fila de retry limpa."
                    $script:RetryQueue.Remove($taskName)
                }
            }
            
            # Atualiza Historico
            if (-not $script:TaskHistory.ContainsKey($taskName)) { $script:TaskHistory[$taskName] = New-Object System.Collections.Generic.List[PSObject] }
            $historyEntry = [PSCustomObject]@{
                exitCode = $exitCode
                finishedAt = $agora.ToString("yyyy-MM-dd HH:mm:ss")
                durationSeconds = $duration
            }
            $script:TaskHistory[$taskName].Insert(0, $historyEntry)
            if ($script:TaskHistory[$taskName].Count -gt $script:TaskHistoryLimit) { $script:TaskHistory[$taskName].RemoveAt($script:TaskHistoryLimit) }
            
            $script:TaskLastResult[$taskName] = $historyEntry
            $toRemove += $taskName
        }
    }
    foreach ($name in $toRemove) { $script:RunningTasks.Remove($name) | Out-Null }
}


function Invoke-ScheduledTask {
    param($Task, [datetime]$Now, [string]$RetryExecId = "")
    $taskName = [string]$Task.name
    if ($script:RunningTasks.ContainsKey($taskName)) { return }
    
    # Resolve caminho dinamico (Skill: ai-native-development-standard)
    $rawPath = [string]$Task.scriptPath
    $absPath = if ([System.IO.Path]::IsPathRooted($rawPath)) { $rawPath } else { Join-Path $ScriptPath $rawPath }

    $execId = if ([string]::IsNullOrWhiteSpace($RetryExecId)) { New-ExecId } else { $RetryExecId }
    Write-Log "DISPARANDO: $taskName ($absPath) [ExecId:$execId]"
    try {
        $proc = Start-Process "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$absPath`" `"$execId`"" -WindowStyle Hidden -PassThru
        $script:RunningTasks[$taskName] = @{ Proc = $proc; StartedAt = $Now; ExecId = $execId }
        $script:StateControl[$taskName] = $Now.ToString("yyyy-MM-dd HH:mm")
        $script:Metrics.TasksTriggered++
        $script:MetricsWindow.TasksTriggered++
    } catch [System.Exception] {
        Write-Log "Falha ao iniciar '$taskName': $_" -Type "ERRO"
    }
}

function Invoke-RetryQueue {
    <#
    .SYNOPSIS
        Processa a fila de retry: re-dispara tarefas que falharam quando o backoff expirou.
    #>
    param([datetime]$Now)
    
    foreach ($taskName in @($script:RetryQueue.Keys)) {
        $q = $script:RetryQueue[$taskName]
        if ($null -eq $q.NextRetryAt -or $Now -lt $q.NextRetryAt) { continue }
        if ($script:RunningTasks.ContainsKey($taskName)) { continue } # Ja rodando

        $retryExecId = "$($q.OriginalExecId)_RETRY_$($q.Attempts)"
        Write-Log "[RETRY] Re-disparando '$taskName'. Tentativa $($q.Attempts)/$($q.MaxAttempts). ExecId=$retryExecId" -Type "WARN"
        
        $taskConfig = $script:Config.tasks | Where-Object { [string]$_.name -eq $taskName }
        if ($taskConfig) {
            # Invalida o NextRetryAt para nao re-agendar ate a tarefa terminar
            $q.NextRetryAt = $null
            Invoke-ScheduledTask -Task $taskConfig -Now $Now -RetryExecId $retryExecId
        }
    }
}


function Test-TaskExecution {
    param($Task, [datetime]$Now, [string]$TimeKey)
    if (-not $Task.enabled) { return $false }
    
    # Valida Dia da Semana (0=Domingo, 6=Sabado)
    $currentDay = [int]$Now.DayOfWeek
    if ($Task.schedule.daysOfWeek -ne $null -and $Task.schedule.daysOfWeek.Count -gt 0) {
        if ($Task.schedule.daysOfWeek -notcontains $currentDay) { return $false }
    }

    # Valida Hora (Se vazio, assume todas as horas - "cada hora")
    if ($Task.schedule.hours -ne $null -and $Task.schedule.hours.Count -gt 0) {
        if ($Task.schedule.hours -notcontains $Now.Hour) { return $false }
    }

    # Valida Minutos
    if ($Task.schedule.minutes -ne $null -and $Task.schedule.minutes.Count -gt 0) {
        if ($Task.schedule.minutes -notcontains $Now.Minute) { return $false }
    }

    # Previne duplicidade no mesmo minuto
    if ($script:StateControl[[string]$Task.name] -eq $TimeKey) { return $false }
    
    return $true
}

function Update-Dashboard {
    $agora = Get-Date
    $script:LastHeartbeatAt = $agora
    
    $tasksState = @()
    foreach ($task in $script:Config.tasks) {
        $taskName = [string]$task.name
        $isRunning = $script:RunningTasks.ContainsKey($taskName)
        $runningSince = if ($isRunning) { $script:RunningTasks[$taskName].StartedAt.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
        
        $tasksState += [ordered]@{
            name = $taskName
            enabled = $task.enabled
            isRunning = $isRunning
            runningSince = $runningSince
            lastResult = $script:TaskLastResult[$taskName]
            history = $script:TaskHistory[$taskName]
            config = $task
        }
    }

    $state = [ordered]@{
        monitorVersion = "3.7.0"
        generatedAt = $agora.ToString("yyyy-MM-dd HH:mm:ss")
        startedAt = $script:MonitorStartedAt.ToString("yyyy-MM-dd HH:mm:ss")
        taskCount = $script:Config.tasks.Count
        runningTasks = $script:RunningTasks.Count
        health = @{
            lastHeartbeatAt = $script:LastHeartbeatAt.ToString("yyyy-MM-dd HH:mm:ss")
            lastConfigReloadAt = if ($script:LastConfigReloadAt) { $script:LastConfigReloadAt.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }
            lastConfigReloadStatus = $script:LastConfigReloadStatus
            mainLoopConsecutiveErr = $script:MainLoopConsecutiveErrors
        }
        metrics = @{
            cumulative = $script:Metrics
            window = $script:MetricsWindow
        }
        tasks = $tasksState
    }

    $json = $state | ConvertTo-Json -Depth 10 -Compress
    $logDir = Get-LogDirectory
    $statePath = Join-Path $logDir "dashboard-state.json"
    $json | Out-File $statePath -Encoding utf8

    # Gera o HTML se o template existir
    $templatePath = Join-Path $ScriptPath ".github\templates\dashboard-modern.html"
    if (Test-Path $templatePath) {
        try {
            $template = Get-Content $templatePath -Raw
            $html = $template.Replace("__DASHBOARD_JSON__", $json).Replace("__REFRESH_SECONDS__", $script:DashboardSettings.refreshSeconds.ToString())
            $html | Out-File $script:DashboardOutputPath -Encoding utf8
        } catch [System.Exception] {
            Write-Log "Falha ao gerar HTML do Dashboard: $_" -Type "WARN"
        }
    }
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

        # Processa retries antes dos agendamentos normais (prioridade)
        Invoke-RetryQueue -Now $agora

        foreach ($task in $script:Config.tasks) {
            if (Test-TaskExecution -Task $task -Now $agora -TimeKey $timeKey) {
                Invoke-ScheduledTask -Task $task -Now $agora
            }
        }
        
        Update-Dashboard

        if ($RunOnce) { break }
        Start-Sleep -Seconds 20
    }
    catch [System.Exception] {
        Write-Log "ERRO NO LOOP: $_" -Type "ERRO"
        Start-Sleep -Seconds 30
    }
}


if ($script:MonitorMutex) { $script:MonitorMutex.ReleaseMutex(); $script:MonitorMutex.Dispose() }
Exit $script:MonitorExitCode
