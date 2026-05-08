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
    Version: 3.7.2
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
$libRetry = Join-Path $ScriptPath "lib\Lib-Retry.psm1"
$libEmail = Join-Path $ScriptPath "lib\Lib-Email.psm1"
$ConfigFilePath = Join-Path $ScriptPath "config.json"
$EmergencyLog = Join-Path $ScriptPath "Startup_Error.txt"

# --- BOOTSTRAP / PRE-FLIGHT (Self-Diagnosing) ---
if (Test-Path $libLogging) {
    Import-Module $libLogging -Force
    if (Test-Path $libRetry) { Import-Module $libRetry  -Force }
    if (Test-Path $libEmail) { Import-Module $libEmail  -Force }
    # O Monitor realiza o seu proprio Pre-Flight para garantir que o Hub esta saudavel
    $preFlight = Test-AutomationPreFlight -ExecId "bootstrap" -LogPath $EmergencyLog -CheckPaths @($ConfigFilePath)
    if (-not $preFlight) {
        Write-Host "ERRO CRITICO: Pre-Flight do Monitor falhou. Verifique $EmergencyLog" -ForegroundColor Red
        Exit 9
    }
}
else {
    Write-Host "ERRO CRITICO: Biblioteca de log nao encontrada em $libLogging" -ForegroundColor Red
    Exit 1
}

# Configuracao Global de Encoding (Skill log-standardization)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# Forca o console host para UTF-8 (Blindagem visual no console/log)
try { if ($host.Name -eq "ConsoleHost") { chcp 65001 | Out-Null } } catch [System.Exception] {}

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:ApiListener = $null
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
    }
    else {
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
$script:ApiToken = [guid]::NewGuid().ToString("N")
$script:DashboardOutputPath = Join-Path $ScriptPath "Dashboard\dashboard.html"

# --- RETRY QUEUE (VALEG: A-Arquitetura, Retry em Duas Camadas) ---
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
    }
    catch [System.Exception] { return $false }

    if ($Force -or $currentHash -ne $script:ConfigHash) {
        try {
            $raw = Get-Content $ConfigFilePath -Raw -Encoding UTF8
            $script:Config = $raw | ConvertFrom-Json
            $script:ConfigHash = $currentHash
            Write-Log "Configuracao carregada. Tarefas: $($script:Config.tasks.Count) | Hash=$($currentHash.Substring(0,8))"
            $script:LastConfigReloadAt = Get-Date
            $script:LastConfigReloadStatus = "Sucesso"
            return $true
        }
        catch [System.Exception] {
            Write-Log "Falha ao carregar config.json: $_" -Type "ERRO"
            $script:LastConfigReloadStatus = "Erro: $_"
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
        $proc = $record.Proc
        if ($proc.HasExited) {
            $exitCode = $proc.ExitCode
            $startedAt = $record.StartedAt
            $duration = [math]::Round(($agora - $startedAt).TotalSeconds, 1)
            
            Write-Log "Tarefa '$taskName' finalizada. ExitCode=$exitCode PID=$($proc.Id) Duracao=$($duration)s"
            
            $script:Metrics.TasksCompleted++
            $script:MetricsWindow.TasksCompleted++
            if ($exitCode -ne 0) {
                $script:Metrics.TasksFinishedNonZero++
                $script:MetricsWindow.TasksFinishedNonZero++

                $taskConfig = $script:Config.tasks | Where-Object { [string]$_.name -eq $taskName }
                if ($taskConfig -and $taskConfig.retryOnFailure -and $taskConfig.retryOnFailure.enabled) {
                    $retryConf = $taskConfig.retryOnFailure
                    $retryOnCodes = @($retryConf.retryOnExitCodes)
                    
                    if ($retryOnCodes -contains $exitCode) {
                        if (-not $script:RetryQueue.ContainsKey($taskName)) {
                            $execIdOriginal = if ($record.ExecId) { $record.ExecId } else { "MONITOR" }
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
                            Write-Log "[RETRY_ESGOTADO] '$taskName' falhou definitivamente apos $($q.MaxAttempts) tentativas. ExitCode=$exitCode" -Type "ERRO"
                            if ($q.AlertOnDefinitive) {
                                try {
                                    $alertLogPath = Join-Path (Get-LogDirectory) "$(Get-Date -Format 'yyyy-MM')_Monitor.log"
                                    Send-AlertaFalhaDefinitiva -TaskName $taskName -ExecId $q.OriginalExecId `
                                        -UltimoErro "ExitCode=$exitCode (apos $($q.MaxAttempts) tentativas)" `
                                        -Tentativas $q.MaxAttempts -LogPath $alertLogPath
                                }
                                catch [System.Exception] {
                                    Write-Log "Falha ao enviar alerta definitivo: $_" -Type "WARN"
                                }
                            }
                            $script:RetryQueue.Remove($taskName)
                        }
                        else {
                            $backoffIdx = [Math]::Min($q.Attempts - 1, $q.BackoffSeconds.Count - 1)
                            $waitSec = $q.BackoffSeconds[$backoffIdx]
                            $q.NextRetryAt = $agora.AddSeconds($waitSec)
                            Write-Log "[RETRY] '$taskName' agendado para retry $($q.Attempts)/$($q.MaxAttempts) em ${waitSec}s (as $($q.NextRetryAt.ToString('dd/MM HH:mm:ss'))). ExitCode anterior=$exitCode" -Type "WARN"
                        }
                    }
                    else {
                        if ($script:RetryQueue.ContainsKey($taskName)) { $script:RetryQueue.Remove($taskName) }
                    }
                }
            }
            else {
                if ($script:RetryQueue.ContainsKey($taskName)) {
                    Write-Log "[RETRY] '$taskName' concluiu com sucesso. Fila de retry limpa."
                    $script:RetryQueue.Remove($taskName)
                }
            }
            
            if (-not $script:TaskHistory.ContainsKey($taskName)) { $script:TaskHistory[$taskName] = New-Object System.Collections.Generic.List[PSObject] }
            $historyEntry = [PSCustomObject]@{
                exitCode        = $exitCode
                finishedAt      = $agora.ToString("dd/MM/yyyy HH:mm:ss")
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
    
    $rawPath = [string]$Task.scriptPath
    $absPath = if ([System.IO.Path]::IsPathRooted($rawPath)) { $rawPath } else { Join-Path $ScriptPath $rawPath }

    $execId = if ([string]::IsNullOrWhiteSpace($RetryExecId)) { New-ExecId } else { $RetryExecId }
    Write-Log "DISPARANDO: $taskName ($absPath) [ExecId:$execId]"
    try {
        $proc = Start-Process "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$absPath`" `"$execId`"" -WindowStyle Hidden -PassThru
        $script:RunningTasks[$taskName] = @{ Proc = $proc; StartedAt = $Now; ExecId = $execId }
        $script:StateControl[$taskName] = $Now.ToString("dd/MM HH:mm")
        $script:Metrics.TasksTriggered++
        $script:MetricsWindow.TasksTriggered++
    }
    catch [System.Exception] {
        Write-Log "Falha ao iniciar '$taskName': $_" -Type "ERRO"
    }
}

function Invoke-RetryQueue {
    param([datetime]$Now)
    foreach ($taskName in @($script:RetryQueue.Keys)) {
        $q = $script:RetryQueue[$taskName]
        if ($null -eq $q.NextRetryAt -or $Now -lt $q.NextRetryAt) { continue }
        if ($script:RunningTasks.ContainsKey($taskName)) { continue }

        $retryExecId = "$($q.OriginalExecId)_RETRY_$($q.Attempts)"
        Write-Log "[RETRY] Re-disparando '$taskName'. Tentativa $($q.Attempts)/$($q.MaxAttempts). ExecId=$retryExecId" -Type "WARN"
        
        $taskConfig = $script:Config.tasks | Where-Object { [string]$_.name -eq $taskName }
        if ($taskConfig) {
            $q.NextRetryAt = $null
            Invoke-ScheduledTask -Task $taskConfig -Now $Now -RetryExecId $retryExecId
        }
    }
}

function Test-TaskExecution {
    param($Task, [datetime]$Now, [string]$TimeKey)
    if (-not $Task.enabled) { return $false }
    
    $currentDay = [int]$Now.DayOfWeek
    if ($null -ne $Task.schedule.daysOfWeek -and $Task.schedule.daysOfWeek.Count -gt 0) {
        if ($Task.schedule.daysOfWeek -notcontains $currentDay) { return $false }
    }

    if ($null -ne $Task.schedule.hours -and $Task.schedule.hours.Count -gt 0) {
        if ($Task.schedule.hours -notcontains $Now.Hour) { return $false }
    }

    if ($null -ne $Task.schedule.minutes -and $Task.schedule.minutes.Count -gt 0) {
        if ($Task.schedule.minutes -notcontains $Now.Minute) { return $false }
    }

    if ($script:StateControl[[string]$Task.name] -eq $TimeKey) { return $false }
    
    return $true
}

function Start-ApiServer {
    try {
        $script:ApiListener = New-Object System.Net.HttpListener
        $script:ApiListener.Prefixes.Add("http://localhost:8765/")
        $script:ApiListener.Start()
        Write-Log "API Server iniciado em http://localhost:8765/"
    }
    catch {
        Write-Log "Falha ao iniciar API Server: $_" -Type "WARN"
    }
}

function Invoke-ApiRequests {
    if ($null -eq $script:ApiListener -or -not $script:ApiListener.IsListening) { return }
    try {
        if (-not $script:ApiListener.BeginGetContext($null, $null).AsyncWaitHandle.WaitOne(1)) { return }
        $ctx = $script:ApiListener.EndGetContext($script:ApiListener.BeginGetContext($null, $null))
        $req = $ctx.Request
        $res = $ctx.Response
        
        $res.AddHeader("Access-Control-Allow-Origin", "*")
        $res.AddHeader("Access-Control-Allow-Methods", "POST, OPTIONS")
        $res.AddHeader("Access-Control-Allow-Headers", "Content-Type, X-Monitor-Token")
        
        if ($req.HttpMethod -eq "OPTIONS") { $res.StatusCode = 200; $res.Close(); return }

        if ($req.Headers["X-Monitor-Token"] -ne $script:ApiToken) { $res.StatusCode = 403; $res.Close(); return }

        $reader = New-Object System.IO.StreamReader($req.InputStream)
        $body = $reader.ReadToEnd()
        $data = $body | ConvertFrom-Json
        
        $status = "Comando recebido"
        if ($data.action -eq "run-now") {
            $taskName = $data.payload.taskName
            $task = $script:Config.tasks | Where-Object { $_.name -eq $taskName }
            if ($task) {
                Invoke-ScheduledTask -Task $task -Now (Get-Date)
                $status = "Tarefa '$taskName' disparada"
            }
        }

        $responseJson = @{ status = $status } | ConvertTo-Json
        $buffer = [System.Text.Encoding]::UTF8.GetBytes($responseJson)
        $res.ContentLength64 = $buffer.Length
        $res.OutputStream.Write($buffer, 0, $buffer.Length)
        $res.Close()
    }
    catch { }
}

function Update-Dashboard {
    $agora = Get-Date
    $script:LastHeartbeatAt = $agora
    
    $tasksState = @()
    foreach ($task in $script:Config.tasks) {
        $taskName = [string]$task.name
        $isRunning = $script:RunningTasks.ContainsKey($taskName)
        $runningSince = if ($isRunning) { $script:RunningTasks[$taskName].StartedAt.ToString("dd/MM/yyyy HH:mm:ss") } else { $null }
        
        $tasksState += [ordered]@{
            name         = $taskName
            enabled      = $task.enabled
            isRunning    = $isRunning
            runningSince = $runningSince
            lastResult   = $script:TaskLastResult[$taskName]
            history      = $script:TaskHistory[$taskName]
            config       = $task
        }
    }

    $state = [ordered]@{
        monitorVersion = "3.7.2"
        generatedAt    = $agora.ToString("dd/MM/yyyy HH:mm:ss")
        startedAt      = $script:MonitorStartedAt.ToString("dd/MM/yyyy HH:mm:ss")
        taskCount      = $script:Config.tasks.Count
        runningTasks   = $script:RunningTasks.Count
        health         = @{
            lastHeartbeatAt        = $script:LastHeartbeatAt.ToString("dd/MM/yyyy HH:mm:ss")
            lastConfigReloadAt     = $(if ($script:LastConfigReloadAt) { $script:LastConfigReloadAt.ToString("dd/MM/yyyy HH:mm:ss") } else { "N/A" })
            lastConfigReloadStatus = $script:LastConfigReloadStatus
            mainLoopConsecutiveErr = $script:MainLoopConsecutiveErrors
        }
        metrics        = @{ cumulative = $script:Metrics; window = $script:MetricsWindow }
        tasks          = $tasksState
        operations     = @{ apiBaseUrl = "http://localhost:8765"; endpoint = "/api/operations"; token = $script:ApiToken; apiMode = "LocalHttpListener"; statusMessage = "Servidor Ativo" }
    }

    $json = $state | ConvertTo-Json -Depth 10 -Compress
    $statePath = Join-Path (Get-LogDirectory) "dashboard-state.json"
    $json | Out-File $statePath -Encoding utf8
}

# --- MAIN LOOP ---
Update-Configuration -Force
Start-ApiServer
Update-Dashboard

while ($true) {
    try {
        Remove-FinishedTask
        Update-Configuration | Out-Null
        $agora = Get-Date
        $timeKey = $agora.ToString("dd/MM HH:mm")

        Invoke-RetryQueue -Now $agora

        foreach ($task in $script:Config.tasks) {
            if (Test-TaskExecution -Task $task -Now $agora -TimeKey $timeKey) {
                Invoke-ScheduledTask -Task $task -Now $agora
            }
        }
        
        Invoke-ApiRequests
        Update-Dashboard

        if ($RunOnce) { break }
        Start-Sleep -Seconds 20
        $script:MainLoopConsecutiveErrors = 0
    }
    catch {
        $script:MainLoopConsecutiveErrors++
        Write-Log "ERRO NO LOOP: $_" -Type "ERRO"
        if ($script:MainLoopConsecutiveErrors -ge $script:MainLoopMaxConsecutiveErrors) {
            Write-Log "Muitos erros consecutivos no loop. Encerrando monitor." -Type "ERRO"
            $script:MonitorExitCode = 1
            break
        }
        Start-Sleep -Seconds 10
    }
}

if ($script:MonitorMutex) { $script:MonitorMutex.ReleaseMutex(); $script:MonitorMutex.Dispose() }
Exit $script:MonitorExitCode

