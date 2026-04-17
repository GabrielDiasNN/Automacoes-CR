# ==============================================================================
# ARQUIVO: MonitorAutomacoes.ps1
# VERSÃO: 3.6
# ==============================================================================

param(
    [switch]$RunOnce,
    [switch]$SkipTaskExecution,
    [switch]$DryRun,
    [string]$MutexNameOverride = ""
)

$ErrorActionPreference = "Stop"

$ScriptPath = $PSScriptRoot
if (-not $ScriptPath) { $ScriptPath = "C:\Automacoes" }

$EmergencyLog = Join-Path $ScriptPath "Startup_Error.txt"

$script:MonitorExitCode = 0

function Write-StartupDiagnostic {
    param(
        [string]$Message,
        [string]$Type = "ERRO"
    )

    try {
        $timestamp = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
        $line = "[$timestamp] [PS] [$Type] $Message"
        $encoding = if ($Utf8Encoding) { $Utf8Encoding } else { New-Object System.Text.UTF8Encoding($false) }

        $sw = New-Object System.IO.StreamWriter($EmergencyLog, $true, $encoding)
        try {
            $sw.WriteLine($line)
            $sw.Flush()
        }
        finally {
            $sw.Close()
            $sw.Dispose()
        }
    }
    catch {}
}

$Utf8Encoding = New-Object System.Text.UTF8Encoding($false)
try {
    [Console]::InputEncoding = $Utf8Encoding
    [Console]::OutputEncoding = $Utf8Encoding
    $OutputEncoding = $Utf8Encoding
}
catch {}

$MutexName = if ([string]::IsNullOrWhiteSpace($MutexNameOverride)) {
    "Global\MonitorAutomacoesMutex"
}
else {
    $MutexNameOverride
}
$MutexWaitSeconds = 5
$script:MutexAcquired = $false

try {
    # Mantemos o objeto Mutex no escopo do script para garantir que ele não seja coletado
    # pelo Garbage Collector enquanto o monitor estiver rodando.
    $script:MonitorMutex = New-Object System.Threading.Mutex($false, $MutexName)
}
catch {
    $msg = "Falha crítica ao inicializar Mutex: $_"
    Write-Host "ERRO: $msg" -ForegroundColor Red
    Write-StartupDiagnostic -Message $msg -Type "ERRO"
    Exit 1
}

try {
    $script:MutexAcquired = $script:MonitorMutex.WaitOne([TimeSpan]::FromSeconds($MutexWaitSeconds), $false)
}
catch [System.Threading.AbandonedMutexException] {
    $script:MutexAcquired = $true
    $msg = "Mutex abandonado detectado. Assumindo controle desta instância."
    Write-Host "AVISO: $msg" -ForegroundColor Yellow
    Write-StartupDiagnostic -Message $msg -Type "WARN"
}
catch {
    $msg = "Falha ao adquirir Mutex: $_"
    Write-Host "ERRO: $msg" -ForegroundColor Red
    Write-StartupDiagnostic -Message $msg -Type "ERRO"
    Exit 1
}

if (-not $script:MutexAcquired) {
    $msg = "Não foi possível adquirir o mutex '$MutexName' em $MutexWaitSeconds s. Outra instância provavelmente está ativa."
    Write-Host "AVISO: $msg" -ForegroundColor Yellow
    Write-StartupDiagnostic -Message $msg -Type "WARN"
    Exit 0
}

if (Test-Path $EmergencyLog) {
    Remove-Item $EmergencyLog -ErrorAction SilentlyContinue
}

$ConfigFilePath = Join-Path $ScriptPath "config.json"

$script:Config = $null
$script:ConfigLastWrite = $null
$script:ConfigHash = $null
$script:RunningTasks = @{}
$script:StateControl = @{}
$script:MainLoopConsecutiveErrors = 0
$script:MainLoopMaxConsecutiveErrors = 5
$script:PreviousMetricsSnapshot = $null
$script:SkipTaskExecutionLogged = $false
$script:Metrics = @{
    TasksTriggered       = 0
    TasksDryRunEligible  = 0
    TasksSkippedOverlap  = 0
    TasksCompleted       = 0
    TasksFinishedNonZero = 0
    TasksFinishedWarn    = 0
    ExitCode7ReadOnly    = 0
    ExitCode23Cooldown   = 0
    ExitCode40Concurrent = 0
    ConfigReloadSuccess  = 0
    ConfigReloadFailure  = 0
}
$script:MetricsWindow = @{
    TasksTriggered       = 0
    TasksDryRunEligible  = 0
    TasksSkippedOverlap  = 0
    TasksCompleted       = 0
    TasksFinishedNonZero = 0
    TasksFinishedWarn    = 0
    ExitCode7ReadOnly    = 0
    ExitCode23Cooldown   = 0
    ExitCode40Concurrent = 0
    ConfigReloadSuccess  = 0
    ConfigReloadFailure  = 0
}
$script:MetricsWindowStartedAt = Get-Date
$script:TaskLastResult = @{}
$script:TaskHistory = @{}
$script:TaskHistoryLimit = 50
$script:MonitorStartedAt = Get-Date
$script:LastConfigReloadAt = $null
$script:LastConfigReloadStatus = "N/A"
$script:LastHeartbeatAt = $script:MonitorStartedAt
$script:OperationsApiEnabled = $true
$script:OperationsApiPort = 8765
$script:OperationsApiPrefix = "http://localhost:8765/"
$script:OperationsApiStatus = "Nao iniciado"
$script:OperationsApiLastError = ""
$script:OperationsApiToken = [guid]::NewGuid().ToString("N")
$script:HttpListener = $null
$script:OperationsApiAsyncResult = $null
$script:DashboardTemplatePath = Join-Path $ScriptPath ".github\templates\dashboard-modern.html"
$script:DashboardOutputPath = Join-Path $ScriptPath "Dashboard\dashboard.html"
$script:DashboardTemplateHash = ""
$script:DashboardTemplateContent = $null
$script:DashboardTemplateSource = "fallback"
$script:DashboardTemplateStatus = "Template fallback embutido em uso."
$script:DashboardSettings = [ordered]@{
    enabled                       = $true
    mode                          = "modern"
    refreshSeconds                = 60
    historyLimitPerTask           = 50
    scheduleDelayToleranceMinutes = 5
}

function Add-MetricCounter {
    param(
        [string]$MetricName,
        [int]$Delta = 1
    )

    if ($script:Metrics.ContainsKey($MetricName)) {
        $script:Metrics[$MetricName] += $Delta
    }

    if ($script:MetricsWindow.ContainsKey($MetricName)) {
        $script:MetricsWindow[$MetricName] += $Delta
    }
}

function Get-MetricsCountersSnapshot {
    param([hashtable]$Source)

    return [ordered]@{
        TasksTriggered       = [int]$Source.TasksTriggered
        TasksDryRunEligible  = [int]$Source.TasksDryRunEligible
        TasksSkippedOverlap  = [int]$Source.TasksSkippedOverlap
        TasksCompleted       = [int]$Source.TasksCompleted
        TasksFinishedNonZero = [int]$Source.TasksFinishedNonZero
        TasksFinishedWarn    = [int]$Source.TasksFinishedWarn
        ExitCode7ReadOnly    = [int]$Source.ExitCode7ReadOnly
        ExitCode23Cooldown   = [int]$Source.ExitCode23Cooldown
        ExitCode40Concurrent = [int]$Source.ExitCode40Concurrent
        ConfigReloadSuccess  = [int]$Source.ConfigReloadSuccess
        ConfigReloadFailure  = [int]$Source.ConfigReloadFailure
    }
}

function Reset-WindowMetrics {
    param([datetime]$WindowStart = (Get-Date))

    foreach ($metricKey in @($script:MetricsWindow.Keys)) {
        $script:MetricsWindow[$metricKey] = 0
    }

    $script:MetricsWindowStartedAt = $WindowStart
}

function Save-MetricsSnapshot {
    param(
        [datetime]$WindowEnd = (Get-Date),
        [switch]$ResetWindow
    )

    try {
        $logDir = Get-LogDirectory
        $snapshotPath = Join-Path $logDir "Monitor_Metrics.json"
        $windowStart = $script:MetricsWindowStartedAt
        if (-not $windowStart) { $windowStart = $WindowEnd }

        $snapshot = [ordered]@{
            generatedAt                 = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
            monitorVersion              = "3.6"
            runningTasks                = [int]$script:RunningTasks.Count
            previousSnapshotGeneratedAt = if ($script:PreviousMetricsSnapshot) { [string]$script:PreviousMetricsSnapshot.generatedAt } else { $null }
            cumulative                  = Get-MetricsCountersSnapshot -Source $script:Metrics
            window                      = [ordered]@{
                startedAt = $windowStart.ToString("yyyy-MM-ddTHH:mm:ssK")
                endedAt   = $WindowEnd.ToString("yyyy-MM-ddTHH:mm:ssK")
                counters  = Get-MetricsCountersSnapshot -Source $script:MetricsWindow
            }
        }

        Set-Utf8Content -FilePath $snapshotPath -Content ($snapshot | ConvertTo-Json -Depth 6)
    }
    catch {
        Write-Log "Falha ao persistir snapshot de metricas: $_" -Type "WARN"
    }
    finally {
        if ($ResetWindow) {
            Reset-WindowMetrics -WindowStart $WindowEnd
        }
    }
}

function Add-TaskHistoryEntry {
    param(
        [string]$TaskName,
        [int]$ExitCode,
        [datetime]$FinishedAt,
        [Nullable[datetime]]$StartedAt = $null,
        [int]$DurationSeconds = 0,
        [int]$ProcessId = 0
    )

    if ([string]::IsNullOrWhiteSpace($TaskName)) { return }

    if (-not $script:TaskHistory.ContainsKey($TaskName)) {
        $script:TaskHistory[$TaskName] = @()
    }

    $status = if ($ExitCode -eq 0) {
        "OK"
    }
    elseif ($ExitCode -in @(7, 23, 40)) {
        "WARN"
    }
    else {
        "ERRO"
    }

    $entry = [ordered]@{
        finishedAt      = $FinishedAt.ToString("yyyy-MM-ddTHH:mm:ssK")
        startedAt       = if ($StartedAt) { $StartedAt.Value.ToString("yyyy-MM-ddTHH:mm:ssK") } else { $null }
        exitCode        = [int]$ExitCode
        status          = $status
        durationSeconds = [int]$DurationSeconds
        processId       = [int]$ProcessId
    }

    $existing = @($script:TaskHistory[$TaskName])
    $updated = @($entry) + $existing
    if ($updated.Count -gt $script:TaskHistoryLimit) {
        $updated = $updated[0..($script:TaskHistoryLimit - 1)]
    }

    $script:TaskHistory[$TaskName] = $updated
}

function Get-TaskDurationSummary {
    param([array]$Entries)

    $samples = @($Entries | ForEach-Object { [int]$_.durationSeconds } | Where-Object { $_ -gt 0 })
    if ($samples.Count -eq 0) {
        return [ordered]@{ avgSeconds = 0; p95Seconds = 0 }
    }

    $avg = [math]::Round((($samples | Measure-Object -Sum).Sum / $samples.Count), 0)
    $sorted = @($samples | Sort-Object)
    $idx = [math]::Ceiling($sorted.Count * 0.95) - 1
    if ($idx -lt 0) { $idx = 0 }
    if ($idx -ge $sorted.Count) { $idx = $sorted.Count - 1 }

    return [ordered]@{
        avgSeconds = [int]$avg
        p95Seconds = [int]$sorted[$idx]
    }
}

function Get-DashboardSettings {
    $defaults = [ordered]@{
        enabled                       = $true
        mode                          = "modern"
        refreshSeconds                = 60
        historyLimitPerTask           = 50
        scheduleDelayToleranceMinutes = 5
    }

    if (-not ($script:Config -and $script:Config.settings -and $script:Config.settings.dashboard)) {
        return $defaults
    }

    $dashboard = $script:Config.settings.dashboard

    if ($null -ne $dashboard.enabled) {
        $defaults.enabled = [bool]$dashboard.enabled
    }

    if (-not [string]::IsNullOrWhiteSpace([string]$dashboard.mode)) {
        $defaults.mode = [string]$dashboard.mode
    }

    if ($dashboard.refreshSeconds) {
        $defaults.refreshSeconds = [int]$dashboard.refreshSeconds
    }

    if ($dashboard.historyLimitPerTask) {
        $defaults.historyLimitPerTask = [int]$dashboard.historyLimitPerTask
    }

    if ($dashboard.scheduleDelayToleranceMinutes) {
        $defaults.scheduleDelayToleranceMinutes = [int]$dashboard.scheduleDelayToleranceMinutes
    }

    return $defaults
}

function Get-PreviousScheduledRun {
    param(
        $Schedule,
        [datetime]$ReferenceTime = (Get-Date)
    )

    if (-not $Schedule) { return $null }

    $candidate = $ReferenceTime.AddMinutes(-1)
    $candidate = [datetime]::new($candidate.Year, $candidate.Month, $candidate.Day, $candidate.Hour, $candidate.Minute, 0)

    for ($i = 0; $i -lt 10080; $i++) {
        $dow = [int]$candidate.DayOfWeek
        $h = $candidate.Hour
        $m = $candidate.Minute

        $dowOk = $Schedule.daysOfWeek -contains $dow
        $hourOk = ($Schedule.hours.Count -eq 0) -or ($Schedule.hours -contains $h)
        $minOk = $Schedule.minutes -contains $m

        if ($dowOk -and $hourOk -and $minOk) { return $candidate }

        $candidate = $candidate.AddMinutes(-1)
    }

    return $null
}

function Get-ConsecutiveErrorCount {
    param([array]$Entries)

    $count = 0
    foreach ($entry in @($Entries)) {
        if ([string]$entry.status -eq "ERRO") {
            $count++
            continue
        }
        break
    }

    return $count
}

function Get-DashboardStateSnapshot {
    param([datetime]$Now = (Get-Date))

    $dayNames = @("Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab")
    $tasks = @()

    foreach ($task in $script:Config.tasks) {
        $taskName = [string]$task.name
        $enabled = [bool]$task.enabled
        $isRunning = $script:RunningTasks.ContainsKey($taskName)
        $nextRun = $null
        $previousRun = $null
        if ($enabled -and $task.schedule) {
            $nextRunCandidate = Get-NextScheduledRun -Schedule $task.schedule
            if ($nextRunCandidate) {
                $nextRun = $nextRunCandidate.ToString("yyyy-MM-ddTHH:mm:ssK")
            }

            $previousRunCandidate = Get-PreviousScheduledRun -Schedule $task.schedule -ReferenceTime $Now
            if ($previousRunCandidate) {
                $previousRun = $previousRunCandidate.ToString("yyyy-MM-ddTHH:mm:ssK")
            }
        }

        $scheduleText = ""
        if ($task.schedule) {
            $dowStr = ($task.schedule.daysOfWeek | ForEach-Object { $dayNames[[int]$_] }) -join ","
            $hhStr = if ($task.schedule.hours.Count -gt 0) {
                ($task.schedule.hours | ForEach-Object { $_.ToString("00") }) -join "/"
            }
            else { "cada" }
            $mmStr = ($task.schedule.minutes | ForEach-Object { $_.ToString("00") }) -join ","
            $scheduleText = "$dowStr $hhStr`:$mmStr"
        }

        $runningSince = $null
        $runningSeconds = 0
        if ($isRunning) {
            $record = $script:RunningTasks[$taskName]
            if ($record -is [hashtable] -and $record.StartedAt) {
                $runningSince = $record.StartedAt.ToString("yyyy-MM-ddTHH:mm:ssK")
                $runningSeconds = [int][math]::Round((New-TimeSpan -Start $record.StartedAt -End $Now).TotalSeconds, 0)
            }
        }

        $lastResult = $null
        if ($script:TaskLastResult.ContainsKey($taskName)) {
            $last = $script:TaskLastResult[$taskName]
            $lastResult = [ordered]@{
                exitCode        = [int]$last.ExitCode
                finishedAt      = $last.FinishedAt.ToString("yyyy-MM-ddTHH:mm:ssK")
                durationSeconds = if ($last.DurationSeconds) { [int]$last.DurationSeconds } else { 0 }
            }
        }

        $entries = if ($script:TaskHistory.ContainsKey($taskName)) { @($script:TaskHistory[$taskName]) } else { @() }
        $durationSummary = Get-TaskDurationSummary -Entries $entries

        $tasks += [ordered]@{
            name           = $taskName
            enabled        = $enabled
            scheduleText   = $scheduleText
            nextRun        = $nextRun
            previousRun    = $previousRun
            isRunning      = $isRunning
            runningSince   = $runningSince
            runningSeconds = $runningSeconds
            lastResult     = $lastResult
            avgDurationSec = [int]$durationSummary.avgSeconds
            p95DurationSec = [int]$durationSummary.p95Seconds
            historyCount   = $entries.Count
            config         = [ordered]@{
                scriptPath     = [string]$task.scriptPath
                preventOverlap = [bool]$task.preventOverlap
                waitForExit    = [bool]$task.waitForExit
                schedule       = [ordered]@{
                    daysOfWeek = if ($task.schedule) { @($task.schedule.daysOfWeek | ForEach-Object { [int]$_ }) } else { @() }
                    hours      = if ($task.schedule) { @($task.schedule.hours | ForEach-Object { [int]$_ }) } else { @() }
                    minutes    = if ($task.schedule) { @($task.schedule.minutes | ForEach-Object { [int]$_ }) } else { @() }
                }
            }
        }
    }

    $alerts = @()
    if ([int]$script:MetricsWindow.TasksFinishedNonZero -gt 0) {
        $alerts += [ordered]@{ severity = "WARN"; message = "Ha execucoes com Exit nao-zero na janela atual." }
    }

    if ([int]$script:Metrics.ConfigReloadFailure -gt [int]$script:Metrics.ConfigReloadSuccess) {
        $alerts += [ordered]@{ severity = "WARN"; message = "Falhas de reload de config superaram sucessos no acumulado." }
    }

    foreach ($taskName in $script:RunningTasks.Keys) {
        $record = $script:RunningTasks[$taskName]
        if ($record -is [hashtable] -and $record.StartedAt -and $record.MaxRuntimeMinutes -gt 0) {
            $elapsedMinutes = (New-TimeSpan -Start $record.StartedAt -End $Now).TotalMinutes
            if ($elapsedMinutes -ge ($record.MaxRuntimeMinutes * 0.9)) {
                $alerts += [ordered]@{ severity = "WARN"; message = "Tarefa '$taskName' proxima do timeout. Decorrido=$([math]::Round($elapsedMinutes,1)) min" }
            }
        }
    }

    $delayTolerance = [int]$script:DashboardSettings.scheduleDelayToleranceMinutes
    foreach ($taskState in $tasks) {
        if (-not $taskState.enabled -or $taskState.isRunning -or -not $taskState.previousRun) { continue }

        $prevRunAt = [datetime]::Parse([string]$taskState.previousRun)
        $delayMinutes = (New-TimeSpan -Start $prevRunAt -End $Now).TotalMinutes
        if ($delayMinutes -lt $delayTolerance) { continue }

        $lastFinishedAt = $null
        if ($taskState.lastResult -and $taskState.lastResult.finishedAt) {
            $lastFinishedAt = [datetime]::Parse([string]$taskState.lastResult.finishedAt)
        }

        if (-not $lastFinishedAt -or $lastFinishedAt -lt $prevRunAt) {
            $alerts += [ordered]@{ severity = "WARN"; message = "Tarefa '$($taskState.name)' aparenta atraso de disparo. Previsto em $($prevRunAt.ToString("dd/MM HH:mm"))" }
        }

        $entries = if ($script:TaskHistory.ContainsKey($taskState.name)) { @($script:TaskHistory[$taskState.name]) } else { @() }
        $consecutiveErrors = Get-ConsecutiveErrorCount -Entries $entries
        if ($consecutiveErrors -ge 2) {
            $alerts += [ordered]@{ severity = "WARN"; message = "Tarefa '$($taskState.name)' com $consecutiveErrors falhas consecutivas." }
        }
    }

    $windowMinutes = 0
    if ($script:MetricsWindowStartedAt) {
        $windowMinutes = [math]::Round((New-TimeSpan -Start $script:MetricsWindowStartedAt -End $Now).TotalMinutes, 0)
    }

    return [ordered]@{
        dashboardSchemaVersion = "1.0.0"
        generatedAt            = $Now.ToString("yyyy-MM-ddTHH:mm:ssK")
        monitorVersion         = "3.6"
        startedAt              = $script:MonitorStartedAt.ToString("yyyy-MM-ddTHH:mm:ssK")
        runningTasks           = [int]$script:RunningTasks.Count
        taskCount              = [int]$script:Config.tasks.Count
        windowMinutes          = [int]$windowMinutes
        health                 = [ordered]@{
            lastHeartbeatAt        = $script:LastHeartbeatAt.ToString("yyyy-MM-ddTHH:mm:ssK")
            lastConfigReloadAt     = if ($script:LastConfigReloadAt) { $script:LastConfigReloadAt.ToString("yyyy-MM-ddTHH:mm:ssK") } else { $null }
            lastConfigReloadStatus = [string]$script:LastConfigReloadStatus
            mainLoopConsecutiveErr = [int]$script:MainLoopConsecutiveErrors
            mutexName              = [string]$MutexName
            checkIntervalSeconds   = if ($script:Config.settings.checkIntervalSeconds) { [int]$script:Config.settings.checkIntervalSeconds } else { 20 }
        }
        dashboard              = [ordered]@{
            enabled                       = [bool]$script:DashboardSettings.enabled
            mode                          = [string]$script:DashboardSettings.mode
            refreshSeconds                = [int]$script:DashboardSettings.refreshSeconds
            historyLimitPerTask           = [int]$script:DashboardSettings.historyLimitPerTask
            scheduleDelayToleranceMinutes = [int]$script:DashboardSettings.scheduleDelayToleranceMinutes
        }
        operations             = [ordered]@{
            apiMode        = "http-local"
            apiBaseUrl     = "http://localhost:$($script:OperationsApiPort)"
            endpoint       = "/api/operations"
            supported      = @("run-now", "dry-run", "toggle-enabled", "open-logs", "set-refresh", "set-schedule")
            implemented    = [bool]($script:HttpListener -and $script:HttpListener.IsListening)
            statusMessage  = [string]$script:OperationsApiStatus
            token          = [string]$script:OperationsApiToken
            tokenHint      = "Envie header X-Monitor-Token para operacoes autenticadas."
            templateSource = [string]$script:DashboardTemplateSource
            templateStatus = [string]$script:DashboardTemplateStatus
            templatePath   = [string]$script:DashboardTemplatePath
        }
        metrics                = [ordered]@{
            cumulative = Get-MetricsCountersSnapshot -Source $script:Metrics
            window     = Get-MetricsCountersSnapshot -Source $script:MetricsWindow
        }
        alerts                 = $alerts
        tasks                  = $tasks
        taskHistory            = $script:TaskHistory
    }
}

function Save-DashboardState {
    param([datetime]$Now = (Get-Date))

    try {
        if (-not $script:DashboardSettings.enabled) { return }
        $state = Get-DashboardStateSnapshot -Now $Now
        $statePath = Join-Path (Get-LogDirectory) "dashboard-state.json"
        Set-Utf8Content -FilePath $statePath -Content ($state | ConvertTo-Json -Depth 8)
    }
    catch {
        Write-Log "Falha ao persistir dashboard-state.json: $_" -Type "WARN"
    }
}

function Import-PreviousDashboardState {
    try {
        $statePath = Join-Path (Get-LogDirectory) "dashboard-state.json"
        if (-not (Test-Path -Path $statePath)) { return }

        $raw = Get-Content -Path $statePath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) { return }

        $state = $raw | ConvertFrom-Json
        if ($state -and $state.taskHistory) {
            $historyTable = @{}
            foreach ($property in $state.taskHistory.PSObject.Properties) {
                $historyTable[[string]$property.Name] = @($property.Value)
            }
            $script:TaskHistory = $historyTable
        }

        if ($state -and $state.tasks) {
            foreach ($taskState in @($state.tasks)) {
                if ($taskState.lastResult) {
                    $finishedAt = $null
                    try {
                        $finishedAt = [datetime]::Parse([string]$taskState.lastResult.finishedAt)
                    } catch { }

                    if ($finishedAt) {
                        $script:TaskLastResult[[string]$taskState.name] = @{
                            ExitCode        = [int]$taskState.lastResult.exitCode
                            FinishedAt      = $finishedAt
                            DurationSeconds = if ($taskState.lastResult.durationSeconds) { [int]$taskState.lastResult.durationSeconds } else { 0 }
                        }
                    }
                }
            }
        }
    }
    catch {
        Write-Log "Falha ao carregar dashboard-state anterior: $_" -Type "WARN"
    }
}

function Import-PreviousMetricsSnapshot {
    try {
        $snapshotPath = Join-Path (Get-LogDirectory) "Monitor_Metrics.json"
        if (-not (Test-Path -Path $snapshotPath)) { return $null }

        $raw = Get-Content -Path $snapshotPath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }

        $snapshot = $raw | ConvertFrom-Json
        if ($snapshot -and $snapshot.cumulative) {
            return $snapshot
        }
    }
    catch {
        Write-Log "Falha ao carregar snapshot anterior de metricas: $_" -Type "WARN"
    }

    return $null
}

function Get-NextScheduledRun {
    param($Schedule)

    if (-not $Schedule) { return $null }

    $candidate = (Get-Date).AddMinutes(1)
    $candidate = $candidate.AddSeconds(-$candidate.Second)
    $candidate = [datetime]::new($candidate.Year, $candidate.Month, $candidate.Day, $candidate.Hour, $candidate.Minute, 0)

    for ($i = 0; $i -lt 10080; $i++) {
        $dow = [int]$candidate.DayOfWeek
        $h = $candidate.Hour
        $m = $candidate.Minute

        $dowOk = $Schedule.daysOfWeek -contains $dow
        $hourOk = ($Schedule.hours.Count -eq 0) -or ($Schedule.hours -contains $h)
        $minOk = $Schedule.minutes -contains $m

        if ($dowOk -and $hourOk -and $minOk) { return $candidate }

        $candidate = $candidate.AddMinutes(1)
    }
    return $null
}

function Get-DashboardHtmlFallbackDocument {
    # Alias de compatibilidade para evitar referencias legadas.
    return Get-DashboardHtmlEmergencyFallbackDocument
}

function Get-DashboardTemplateContent {
    if ([string]::IsNullOrWhiteSpace($script:DashboardTemplatePath)) {
        return $null
    }

    if (-not (Test-Path -Path $script:DashboardTemplatePath)) {
        return $null
    }

    try {
        $hash = Get-ConfigHash -Path $script:DashboardTemplatePath
        if (-not $hash) {
            return $null
        }

        if ($script:DashboardTemplateContent -and $script:DashboardTemplateHash -eq $hash) {
            return $script:DashboardTemplateContent
        }

        $template = Get-Content -Path $script:DashboardTemplatePath -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($template)) {
            return $null
        }

        $script:DashboardTemplateHash = $hash
        $script:DashboardTemplateContent = $template
        $script:DashboardTemplateSource = "external"
        $script:DashboardTemplateStatus = "Template externo carregado com sucesso."
        return $template
    }
    catch {
        Write-Log "Falha ao carregar template externo de dashboard: $_" -Type "WARN"
        return $null
    }
}

function Get-DashboardHtmlEmergencyFallbackDocument {
    # Fallback minimo para contingencia. Evita drift com o template canonico.
    return @'
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="__REFRESH_SECONDS__">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Monitor Automacoes - Fallback</title>
    <style>
        :root { color-scheme: light; }
        body {
            margin: 0;
            padding: 18px;
            background: #f4f7fb;
            color: #0f172a;
            font-family: "Segoe UI", Tahoma, sans-serif;
        }
        .panel {
            max-width: 1080px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid #dbe3ee;
            border-radius: 12px;
            padding: 16px;
        }
        h1 {
            margin: 0 0 10px;
            font-size: 1.2rem;
            color: #0b385f;
        }
        p {
            margin: 0 0 12px;
            line-height: 1.4;
            font-size: 0.92rem;
        }
        pre {
            margin: 0;
            max-height: 70vh;
            overflow: auto;
            padding: 12px;
            border-radius: 10px;
            border: 1px solid #dbe3ee;
            background: #f8fafc;
            color: #1e293b;
            font-size: 0.78rem;
            font-family: Consolas, "Courier New", monospace;
            white-space: pre-wrap;
            word-break: break-word;
        }
    </style>
</head>
<body>
    <main class="panel">
        <h1>Monitor de Automacoes - modo contingencia</h1>
        <p>O template canonico do dashboard nao foi carregado. Exibindo estado bruto para manter observabilidade operacional.</p>
        <pre id="raw-state">Carregando estado...</pre>
    </main>
    <script id="dashboard-data" type="application/json">__DASHBOARD_JSON__</script>
    <script>
        (function () {
            var pre = document.getElementById('raw-state');
            var dataNode = document.getElementById('dashboard-data');
            if (!pre || !dataNode) {
                return;
            }

            try {
                var payload = JSON.parse((dataNode.textContent || '').trim());
                pre.textContent = JSON.stringify(payload, null, 2);
            }
            catch (err) {
                pre.textContent = 'Falha ao interpretar estado do dashboard: ' + err.message;
            }
        })();
    </script>
</body>
</html>
'@
}

function Get-DashboardHtmlDocument {
    $template = Get-DashboardTemplateContent
    if ($template) {
        return $template
    }

    $script:DashboardTemplateSource = "fallback"
    $script:DashboardTemplateStatus = "Template canonico indisponivel; usando fallback de emergencia minimizado."
    return Get-DashboardHtmlEmergencyFallbackDocument
}

function Save-DashboardHtml {
    param([datetime]$Now = (Get-Date))

    try {
        if (-not $script:DashboardSettings.enabled) { return }

        $state = Get-DashboardStateSnapshot -Now $Now
        $htmlPath = $script:DashboardOutputPath
        $legacyHtmlPath = Join-Path (Get-LogDirectory) "dashboard.html"
        $refreshSeconds = [int]$script:DashboardSettings.refreshSeconds

        $historyExport = @()
        foreach ($taskName in @($script:TaskHistory.Keys | Sort-Object)) {
            $entries = @($script:TaskHistory[$taskName] | Select-Object -First 3)
            foreach ($entry in $entries) {
                $historyExport += [ordered]@{
                    taskName        = $taskName
                    status          = $entry.status
                    exitCode        = [int]$entry.exitCode
                    finishedAt      = $entry.finishedAt
                    durationSeconds = [int]$entry.durationSeconds
                }
            }
        }

        $state.Add("history", $historyExport)
        $jsonPayload = $state | ConvertTo-Json -Depth 6 -Compress

        $html = Get-DashboardHtmlDocument
        $html = $html.Replace("__REFRESH_SECONDS__", $refreshSeconds.ToString())
        $html = $html.Replace("__DASHBOARD_JSON__", $jsonPayload)

        Set-Utf8Content -FilePath $htmlPath -Content $html

        if ((Test-Path -Path $legacyHtmlPath) -and ($legacyHtmlPath -ne $htmlPath)) {
            try {
                Remove-Item -Path $legacyHtmlPath -Force -ErrorAction Stop
            }
            catch {
                Write-Log "Falha ao remover dashboard legado em Logs: $_" -Type "WARN"
            }
        }
    }
    catch {
        Write-Log "Falha ao gerar dashboard HTML: $_" -Type "WARN"
    }
}

function Get-ExitCodeLogType {
    param([int]$ExitCode)

    switch ($ExitCode) {
        0 { return "INFO" }
        7 { return "WARN" }
        23 { return "WARN" }
        40 { return "WARN" }
        default { return "ERRO" }
    }
}

function Register-TaskCompletionMetrics {
    param([int]$ExitCode)

    Add-MetricCounter -MetricName "TasksCompleted"

    if ($ExitCode -ne 0) {
        Add-MetricCounter -MetricName "TasksFinishedNonZero"
    }

    switch ($ExitCode) {
        7 {
            Add-MetricCounter -MetricName "ExitCode7ReadOnly"
            Add-MetricCounter -MetricName "TasksFinishedWarn"
            break
        }
        23 {
            Add-MetricCounter -MetricName "ExitCode23Cooldown"
            Add-MetricCounter -MetricName "TasksFinishedWarn"
            break
        }
        40 {
            Add-MetricCounter -MetricName "ExitCode40Concurrent"
            Add-MetricCounter -MetricName "TasksFinishedWarn"
            break
        }
    }
}

function Write-TaskCompletionLog {
    param(
        [string]$TaskName,
        [int]$ExitCode,
        [int]$ProcessId,
        [string]$LogDir,
        [Nullable[datetime]]$StartedAt = $null,
        [datetime]$FinishedAt = (Get-Date),
        [int]$DurationSeconds = 0
    )

    $desc = ""
    if ($script:Config.settings.exitCodeMap -and $script:Config.settings.exitCodeMap."$ExitCode") {
        $desc = " - $($script:Config.settings.exitCodeMap."$ExitCode")"
    }

    Register-TaskCompletionMetrics -ExitCode $ExitCode
    $logType = Get-ExitCodeLogType -ExitCode $ExitCode
    $script:TaskLastResult[$TaskName] = @{ ExitCode = $ExitCode; FinishedAt = $FinishedAt; DurationSeconds = $DurationSeconds }
    Add-TaskHistoryEntry -TaskName $TaskName -ExitCode $ExitCode -FinishedAt $FinishedAt -StartedAt $StartedAt -DurationSeconds $DurationSeconds -ProcessId $ProcessId

    if ($ExitCode -eq 0) {
        Write-Log "Tarefa '$TaskName' finalizada. ExitCode=$ExitCode$desc PID=$ProcessId" -LogDir $LogDir
        return
    }

    $status = if ($logType -eq "ERRO") { "ERRO" } else { "AVISO" }
    Write-Log "Tarefa '$TaskName' finalizada com $status. ExitCode=$ExitCode$desc PID=$ProcessId" -Type $logType -LogDir $LogDir
}

function Initialize-Directory {
    param([string]$Path)
    if ($Path -and -not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function Add-Utf8Line {
    param(
        [string]$FilePath,
        [string]$Line
    )

    $dir = Split-Path -Parent $FilePath
    if ($dir) { Initialize-Directory $dir }

    $sw = New-Object System.IO.StreamWriter($FilePath, $true, $Utf8Encoding)
    try {
        $sw.WriteLine($Line)
        $sw.Flush()
    }
    finally {
        $sw.Close()
        $sw.Dispose()
    }
}

function Set-Utf8Content {
    param(
        [string]$FilePath,
        [string]$Content
    )

    $dir = Split-Path -Parent $FilePath
    if ($dir) { Initialize-Directory $dir }

    $sw = New-Object System.IO.StreamWriter($FilePath, $false, $Utf8Encoding)
    try {
        $sw.Write($Content)
        $sw.Flush()
    }
    finally {
        $sw.Close()
        $sw.Dispose()
    }
}

function Get-LogDirectory {
    if ($script:Config -and $script:Config.settings -and $script:Config.settings.logDirectory) {
        return [string]$script:Config.settings.logDirectory
    }
    return (Join-Path $ScriptPath "Logs")
}

function Write-Log {
    param(
        [string]$msg,
        [string]$type = "INFO",
        [string]$LogDir
    )

    if (-not $LogDir) { $LogDir = Get-LogDirectory }
    Initialize-Directory $LogDir

    $fileName = "$(Get-Date -Format 'yyyy-MM')_Monitor.log"
    $logPath = Join-Path -Path $LogDir -ChildPath $fileName
    $timestamp = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    $line = "[$timestamp] [PS] [$type] $msg"

    try { Add-Utf8Line -FilePath $logPath -Line $line } catch {}

    $color = "Cyan"
    if ($type -eq "ERRO") { $color = "Red" }
    elseif ($type -eq "WARN") { $color = "Yellow" }

    Write-Host $line -ForegroundColor $color
}

function Test-TaskStructure {
    param($Task)

    if (-not $Task) { return "Tarefa nula." }
    if (-not $Task.name) { return "Campo 'name' ausente." }
    if (-not $Task.scriptPath) { return "Campo 'scriptPath' ausente em '$($Task.name)'." }
    if ($null -eq $Task.enabled) { return "Campo 'enabled' ausente em '$($Task.name)'." }
    if (-not $Task.schedule) { return "Campo 'schedule' ausente em '$($Task.name)'." }
    if ($null -eq $Task.schedule.minutes) { return "Campo 'schedule.minutes' ausente em '$($Task.name)'." }

    return $null
}

function Test-AbsolutePathValue {
    param(
        [string]$PathValue,
        [string]$FieldName,
        [string]$TaskName,
        [switch]$Required
    )

    $taskContext = if ($TaskName) { " na tarefa '$TaskName'" } else { "" }

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        if ($Required) {
            throw "Campo '$FieldName' vazio$taskContext."
        }
        return
    }

    if (-not [System.IO.Path]::IsPathRooted($PathValue)) {
        throw ("Campo '{0}' deve ser caminho absoluto{1}. Valor informado: {2}" -f $FieldName, $taskContext, $PathValue)
    }
}

function Test-BooleanFieldValue {
    param(
        $Value,
        [string]$FieldName,
        [string]$TaskName
    )

    if ($null -eq $Value) { return }

    if ($Value -isnot [bool]) {
        throw "Campo '$FieldName' em '$TaskName' deve ser booleano. Valor atual: $Value"
    }
}

function Test-IntegerArrayRange {
    param(
        $Values,
        [string]$FieldName,
        [string]$TaskName,
        [int]$Min,
        [int]$Max,
        [switch]$Required,
        [switch]$AllowEmpty
    )

    if ($null -eq $Values) {
        if ($Required) {
            throw "Campo '$FieldName' ausente em '$TaskName'."
        }
        return
    }

    if (($Values -is [string]) -or ($Values -isnot [System.Collections.IEnumerable])) {
        throw "Campo '$FieldName' em '$TaskName' deve ser array numérico."
    }

    $arrayValues = @($Values)
    if ($arrayValues.Count -eq 0 -and -not $AllowEmpty) {
        throw "Campo '$FieldName' em '$TaskName' não pode ser vazio."
    }

    foreach ($value in $arrayValues) {
        $parsedValue = 0
        if (-not [int]::TryParse([string]$value, [ref]$parsedValue)) {
            throw "Campo '$FieldName' em '$TaskName' contém valor não numérico: $value"
        }

        if ($parsedValue -lt $Min -or $parsedValue -gt $Max) {
            throw "Campo '$FieldName' em '$TaskName' fora do intervalo [$Min,$Max]: $parsedValue"
        }
    }
}

function Get-ConfigHash {
    param([string]$Path)

    try {
        if (-not (Test-Path $Path)) { return $null }
        $stream = [System.IO.File]::OpenRead($Path)
        $sha256 = New-Object System.Security.Cryptography.SHA256Managed
        $hash = [System.BitConverter]::ToString($sha256.ComputeHash($stream)).Replace("-", "")
        $stream.Close()
        $stream.Dispose()
        return $hash
    }
    catch {
        if ($stream) { $stream.Close(); $stream.Dispose() }
        return $null
    }
}

function Test-Configuration {
    param($Config)

    if (-not $Config) { throw "Configuração vazia." }
    if (-not $Config.settings) { throw "Bloco 'settings' ausente." }
    if (-not $Config.tasks) { throw "Bloco 'tasks' ausente." }

    Test-AbsolutePathValue -PathValue ([string]$Config.settings.logDirectory) -FieldName "settings.logDirectory" -Required
    Test-AbsolutePathValue -PathValue ([string]$Config.settings.basePath) -FieldName "settings.basePath" -Required

    if ($null -ne $Config.settings.checkIntervalSeconds) {
        $checkInterval = 0
        if (-not [int]::TryParse([string]$Config.settings.checkIntervalSeconds, [ref]$checkInterval) -or $checkInterval -lt 1) {
            throw "Campo 'settings.checkIntervalSeconds' deve ser inteiro >= 1."
        }
    }

    if ($Config.settings.dashboard) {
        $dashboard = $Config.settings.dashboard

        if ($null -ne $dashboard.enabled -and $dashboard.enabled -isnot [bool]) {
            throw "Campo 'settings.dashboard.enabled' deve ser booleano."
        }

        if ($dashboard.mode) {
            $mode = ([string]$dashboard.mode).ToLower()
            if ($mode -notin @("legacy", "modern")) {
                throw "Campo 'settings.dashboard.mode' deve ser 'legacy' ou 'modern'."
            }
        }

        if ($null -ne $dashboard.refreshSeconds) {
            $refreshSeconds = 0
            if (-not [int]::TryParse([string]$dashboard.refreshSeconds, [ref]$refreshSeconds) -or $refreshSeconds -lt 10 -or $refreshSeconds -gt 3600) {
                throw "Campo 'settings.dashboard.refreshSeconds' deve ser inteiro entre 10 e 3600."
            }
        }

        if ($null -ne $dashboard.historyLimitPerTask) {
            $historyLimit = 0
            if (-not [int]::TryParse([string]$dashboard.historyLimitPerTask, [ref]$historyLimit) -or $historyLimit -lt 1 -or $historyLimit -gt 500) {
                throw "Campo 'settings.dashboard.historyLimitPerTask' deve ser inteiro entre 1 e 500."
            }
        }

        if ($null -ne $dashboard.scheduleDelayToleranceMinutes) {
            $delayTolerance = 0
            if (-not [int]::TryParse([string]$dashboard.scheduleDelayToleranceMinutes, [ref]$delayTolerance) -or $delayTolerance -lt 1 -or $delayTolerance -gt 120) {
                throw "Campo 'settings.dashboard.scheduleDelayToleranceMinutes' deve ser inteiro entre 1 e 120."
            }
        }
    }

    $taskList = @($Config.tasks)
    if ($taskList.Count -eq 0) {
        throw "Bloco 'tasks' não pode ser vazio."
    }

    $names = @{}
    foreach ($task in $taskList) {
        $structureError = Test-TaskStructure -Task $task
        if ($structureError) { throw $structureError }

        $taskName = [string]$task.name

        Test-AbsolutePathValue -PathValue ([string]$task.scriptPath) -FieldName "scriptPath" -TaskName $taskName -Required
        Test-BooleanFieldValue -Value $task.enabled -FieldName "enabled" -TaskName $taskName
        Test-BooleanFieldValue -Value $task.preventOverlap -FieldName "preventOverlap" -TaskName $taskName
        Test-BooleanFieldValue -Value $task.waitForExit -FieldName "waitForExit" -TaskName $taskName

        Test-IntegerArrayRange -Values $task.schedule.daysOfWeek -FieldName "schedule.daysOfWeek" -TaskName $taskName -Min 0 -Max 6 -AllowEmpty
        Test-IntegerArrayRange -Values $task.schedule.hours -FieldName "schedule.hours" -TaskName $taskName -Min 0 -Max 23 -AllowEmpty
        Test-IntegerArrayRange -Values $task.schedule.minutes -FieldName "schedule.minutes" -TaskName $taskName -Min 0 -Max 59 -Required

        if ($names.ContainsKey($taskName)) {
            throw "Nome de tarefa duplicado: '$taskName'."
        }
        $names[$taskName] = $true

        # Validação de caminho para tarefas habilitadas
        if ($task.enabled -and -not (Test-Path $task.scriptPath)) {
            Write-Log "AVISO: scriptPath não encontrado para '$taskName': $($task.scriptPath)" -Type "WARN"
        }
    }
}

function Import-Configuration {
    if (-not (Test-Path $ConfigFilePath)) {
        $err = "ERRO CRÍTICO: Arquivo config.json não encontrado."
        Set-Utf8Content -FilePath $EmergencyLog -Content $err
        return $null
    }

    try {
        $rawJson = Get-Content $ConfigFilePath -Raw -Encoding UTF8
        $config = $rawJson | ConvertFrom-Json
        Test-Configuration -Config $config
        return $config
    }
    catch {
        $err = "ERRO CRÍTICO: Falha ao carregar config.json. Detalhes: $_"
        Set-Utf8Content -FilePath $EmergencyLog -Content $err
        return $null
    }
}

function Update-Configuration {
    param([switch]$Force)

    if (-not (Test-Path $ConfigFilePath)) {
        Write-Log "Arquivo config.json não encontrado em $ConfigFilePath" -Type "ERRO"
        $script:LastConfigReloadStatus = "ERRO"
        Add-MetricCounter -MetricName "ConfigReloadFailure"
        return $false
    }

    $currentWrite = (Get-Item $ConfigFilePath).LastWriteTime
    $currentHash = Get-ConfigHash -Path $ConfigFilePath

    if (-not $currentHash) {
        Write-Log "Falha ao calcular hash de config.json em $ConfigFilePath" -Type "ERRO"
        $script:LastConfigReloadStatus = "ERRO"
        Add-MetricCounter -MetricName "ConfigReloadFailure"
        return $false
    }

    if ($Force -or $null -eq $script:ConfigHash -or $currentHash -ne $script:ConfigHash) {
        $maxAttempts = 3
        $newConfig = $null

        for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
            $newConfig = Import-Configuration
            if ($newConfig) { break }

            if ($attempt -lt $maxAttempts) {
                $jitter = Get-Random -Minimum 0 -Maximum 2000
                $delayMs = 2000 + $jitter
                Write-Log "Falha ao carregar config.json (tentativa $attempt/$maxAttempts). Nova tentativa em $([math]::Round($delayMs/1000,1))s." -Type "WARN"
                Start-Sleep -Milliseconds $delayMs
            }
        }

        if (-not $newConfig) {
            Write-Log "Falha ao carregar config.json após $maxAttempts tentativas. Mantendo configuração atual." -Type "ERRO"
            $script:LastConfigReloadStatus = "ERRO"
            Add-MetricCounter -MetricName "ConfigReloadFailure"
            return $false
        }

        $previousCount = 0
        if ($script:Config -and $script:Config.tasks) {
            $previousCount = $script:Config.tasks.Count
        }

        $script:Config = $newConfig
        $script:ConfigLastWrite = $currentWrite
        $script:ConfigHash = $currentHash
        $script:DashboardSettings = Get-DashboardSettings
        $script:TaskHistoryLimit = [int]$script:DashboardSettings.historyLimitPerTask

        # Purgar entradas obsoletas do StateControl após hot-reload
        $validTaskNames = @($script:Config.tasks | ForEach-Object { [string]$_.name })
        $staleKeys = @($script:StateControl.Keys | Where-Object { $_ -notin $validTaskNames })
        foreach ($key in $staleKeys) { $script:StateControl.Remove($key) | Out-Null }

        if (Test-Path $EmergencyLog) {
            Remove-Item $EmergencyLog -ErrorAction SilentlyContinue
        }

        Write-Log "Configuração recarregada com sucesso. Tarefas: $($script:Config.tasks.Count) (antes: $previousCount) | Hash=$($currentHash.Substring(0,8))"
        $script:LastConfigReloadAt = Get-Date
        $script:LastConfigReloadStatus = "OK"
        Add-MetricCounter -MetricName "ConfigReloadSuccess"
        return $true
    }

    return $true
}

function Remove-FinishedTasks {
    $toRemove = @()
    $logDir = Get-LogDirectory

    foreach ($taskName in $script:RunningTasks.Keys) {
        $record = $script:RunningTasks[$taskName]
        if ($null -eq $record) {
            $toRemove += $taskName
            continue
        }

        $proc = if ($record -is [hashtable]) { $record.Proc } else { $record }

        try {
            if ($proc.HasExited) {
                $finishedAt = Get-Date
                $startedAt = $null
                $durationSec = 0
                if ($record -is [hashtable] -and $record.StartedAt) {
                    $startedAt = [datetime]$record.StartedAt
                    $durationSec = [int][math]::Round((New-TimeSpan -Start $record.StartedAt -End $finishedAt).TotalSeconds, 0)
                }
                $exitCode = $proc.ExitCode
                Write-TaskCompletionLog -TaskName $taskName -ExitCode $exitCode -ProcessId $proc.Id -LogDir $logDir -StartedAt $startedAt -FinishedAt $finishedAt -DurationSeconds $durationSec
                $toRemove += $taskName
            }
            elseif ($record -is [hashtable] -and $record.MaxRuntimeMinutes -gt 0) {
                $elapsed = (New-TimeSpan -Start $record.StartedAt -End (Get-Date)).TotalMinutes
                if ($elapsed -ge $record.MaxRuntimeMinutes) {
                    Write-Log "Tarefa '$taskName' excedeu limite de $($record.MaxRuntimeMinutes) min (decorrido=$([math]::Round($elapsed,1)) min). Encerrando PID=$($proc.Id)." -Type "WARN" -LogDir $logDir
                    $finishedAt = Get-Date
                    $durationSec = [int][math]::Round((New-TimeSpan -Start $record.StartedAt -End $finishedAt).TotalSeconds, 0)
                    try { $proc.Kill() } catch {}
                    Write-TaskCompletionLog -TaskName $taskName -ExitCode 124 -ProcessId $proc.Id -LogDir $logDir -StartedAt ([datetime]$record.StartedAt) -FinishedAt $finishedAt -DurationSeconds $durationSec
                    $toRemove += $taskName
                }
            }
        }
        catch {
            $toRemove += $taskName
        }
    }

    foreach ($name in $toRemove) {
        $script:RunningTasks.Remove($name) | Out-Null
    }
}

function Start-TaskProcess {
    param(
        [string]$Path,
        [string]$Name,
        [string]$LogDir,
        [bool]$WaitForExit = $false,
        [int]$MaxRuntimeMinutes = 0
    )

    if (-not (Test-Path $Path)) {
        Write-Log "ERRO: Arquivo .vbs não encontrado para '$Name': $Path" -Type "ERRO" -LogDir $LogDir
        return $false
    }

    try {
        $ext = [System.IO.Path]::GetExtension($Path).ToLower()
        $proc = $null
        $execId = "$(Get-Date -Format 'yyyyMMdd_HHmmss')_$(Get-Random -Minimum 1000 -Maximum 9999)"

        if ($ext -eq ".vbs") {
            $proc = Start-Process "wscript.exe" -ArgumentList "`"$Path`" `"$execId`"" -WindowStyle Hidden -PassThru -ErrorAction Stop
        }
        elseif ($ext -eq ".ps1") {
            $proc = Start-Process "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$Path`" `"$execId`"" -WindowStyle Hidden -PassThru -ErrorAction Stop
        }
        else {
            throw "Extensão '$ext' não suportada."
        }

        Write-Log "Tarefa '$Name' iniciada. [ExecId=$execId] PID=$($proc.Id) | Script=$Path" -LogDir $LogDir

        if ($WaitForExit) {
            $proc.WaitForExit()
            Write-TaskCompletionLog -TaskName $Name -ExitCode $proc.ExitCode -ProcessId $proc.Id -LogDir $LogDir
            Write-Log "Tarefa '$Name' finalizada em modo síncrono. [ExecId=$execId]" -LogDir $LogDir
        }
        else {
            $script:RunningTasks[$Name] = @{
                Proc              = $proc
                StartedAt         = Get-Date
                MaxRuntimeMinutes = $MaxRuntimeMinutes
            }
        }

        return $true
    }
    catch {
        Write-Log "ERRO: Falha ao iniciar processo para '$Name': $_" -Type "ERRO" -LogDir $LogDir
        return $false
    }
}

function Test-TaskExecution {
    param(
        $Task,
        [datetime]$Now,
        [string]$TimeKey
    )

    if (-not $Task.enabled) { return $false }

    $diaSemanaInt = [int]$Now.DayOfWeek
    $hora = $Now.Hour
    $min = $Now.Minute

    if ($Task.schedule.daysOfWeek -and ($Task.schedule.daysOfWeek -notcontains $diaSemanaInt)) { return $false }

    $horaMatch = ($null -eq $Task.schedule.hours) -or ($Task.schedule.hours.Count -eq 0) -or ($Task.schedule.hours -contains $hora)
    if (-not $horaMatch) { return $false }

    if ($Task.schedule.minutes -notcontains $min) { return $false }

    $stateKey = [string]$Task.name
    if ($script:StateControl[$stateKey] -eq $TimeKey) { return $false }

    return $true
}

function Invoke-ScheduledTask {
    param(
        $Task,
        [datetime]$Now
    )

    $taskName = [string]$Task.name
    $logDir = Get-LogDirectory
    $preventOverlap = $true
    $waitForExit = $false

    if ($null -ne $Task.preventOverlap) { $preventOverlap = [bool]$Task.preventOverlap }
    if ($null -ne $Task.waitForExit) { $waitForExit = [bool]$Task.waitForExit }

    if ($preventOverlap -and $script:RunningTasks.ContainsKey($taskName)) {
        try {
            $record = $script:RunningTasks[$taskName]
            $runningProc = if ($record -is [hashtable]) { $record.Proc } else { $record }
            if ($runningProc -and -not $runningProc.HasExited) {
                Write-Log "Tarefa '$taskName' ignorada por sobreposição. PID em execução=$($runningProc.Id)" -Type "WARN" -LogDir $logDir
                Add-MetricCounter -MetricName "TasksSkippedOverlap"
                return
            }
        }
        catch {
            Write-Log "Falha ao validar sobreposição de '$taskName'. Estado local será limpo. Erro: $_" -Type "WARN" -LogDir $logDir
            $script:RunningTasks.Remove($taskName) | Out-Null
        }
    }

    Write-Log "DISPARANDO: $taskName" -LogDir $logDir
    $maxRuntimeMinutes = 0
    if ($Task.maxRuntimeMinutes) { [int]::TryParse([string]$Task.maxRuntimeMinutes, [ref]$maxRuntimeMinutes) | Out-Null }
    $started = Start-TaskProcess -Path ([string]$Task.scriptPath) -Name $taskName -LogDir $logDir -WaitForExit $waitForExit -MaxRuntimeMinutes $maxRuntimeMinutes

    if ($started) {
        $script:StateControl[$taskName] = $Now.ToString("yyyy-MM-dd HH:mm")
        Add-MetricCounter -MetricName "TasksTriggered"
    }
}

function Save-ConfigurationAtomic {
    param($ConfigObject)

    $json = $ConfigObject | ConvertTo-Json -Depth 12
    $tempPath = "$ConfigFilePath.tmp"
    $backupPath = "$ConfigFilePath.bak"

    Set-Utf8Content -FilePath $tempPath -Content $json

    if (Test-Path -Path $ConfigFilePath) {
        Copy-Item -Path $ConfigFilePath -Destination $backupPath -Force
    }

    Move-Item -Path $tempPath -Destination $ConfigFilePath -Force
}

function Get-TaskByName {
    param(
        [string]$TaskName,
        [switch]$ThrowIfMissing
    )

    foreach ($task in @($script:Config.tasks)) {
        if ([string]$task.name -eq $TaskName) {
            return $task
        }
    }

    if ($ThrowIfMissing) {
        throw "Tarefa '$TaskName' nao encontrada."
    }

    return $null
}

function Invoke-ManualTaskRun {
    param(
        [string]$TaskName,
        [switch]$DryRun
    )

    $task = Get-TaskByName -TaskName $TaskName -ThrowIfMissing
    $logDir = Get-LogDirectory

    if (-not $task.enabled -and -not $DryRun) {
        throw "Tarefa '$TaskName' esta desabilitada."
    }

    if ($DryRun) {
        Write-Log "API: DRY-RUN manual solicitado para '$TaskName'." -Type "WARN" -LogDir $logDir
        Add-MetricCounter -MetricName "TasksDryRunEligible"
        return [ordered]@{ status = "DRY_RUN"; message = "Dry run registrado para '$TaskName'." }
    }

    $preventOverlap = $true
    if ($null -ne $task.preventOverlap) { $preventOverlap = [bool]$task.preventOverlap }
    if ($preventOverlap -and $script:RunningTasks.ContainsKey($TaskName)) {
        throw "Tarefa '$TaskName' ja esta em execucao e preventOverlap=true."
    }

    $waitForExit = $false
    if ($null -ne $task.waitForExit) { $waitForExit = [bool]$task.waitForExit }
    $maxRuntimeMinutes = 0
    if ($task.maxRuntimeMinutes) { [int]::TryParse([string]$task.maxRuntimeMinutes, [ref]$maxRuntimeMinutes) | Out-Null }

    $started = Start-TaskProcess -Path ([string]$task.scriptPath) -Name ([string]$task.name) -LogDir $logDir -WaitForExit $waitForExit -MaxRuntimeMinutes $maxRuntimeMinutes
    if (-not $started) {
        throw "Falha ao iniciar a tarefa '$TaskName'."
    }

    Add-MetricCounter -MetricName "TasksTriggered"
    $script:StateControl[[string]$task.name] = (Get-Date).ToString("yyyy-MM-dd HH:mm")

    return [ordered]@{ status = "STARTED"; message = "Tarefa '$TaskName' iniciada manualmente." }
}

function Update-TaskEnabledFlag {
    param(
        [string]$TaskName,
        [bool]$Enabled
    )

    $cfg = Import-Configuration
    if (-not $cfg) { throw "Falha ao carregar config atual." }

    $target = $null
    foreach ($task in @($cfg.tasks)) {
        if ([string]$task.name -eq $TaskName) {
            $target = $task
            break
        }
    }

    if (-not $target) { throw "Tarefa '$TaskName' nao encontrada no config." }

    $target.enabled = [bool]$Enabled
    Test-Configuration -Config $cfg
    Save-ConfigurationAtomic -ConfigObject $cfg
    Update-Configuration -Force | Out-Null
}

function Update-DashboardRefreshSetting {
    param([int]$RefreshSeconds)

    if ($RefreshSeconds -lt 10 -or $RefreshSeconds -gt 3600) {
        throw "refreshSeconds deve estar entre 10 e 3600."
    }

    $cfg = Import-Configuration
    if (-not $cfg) { throw "Falha ao carregar config atual." }

    if (-not $cfg.settings.dashboard) {
        $cfg.settings | Add-Member -MemberType NoteProperty -Name dashboard -Value ([ordered]@{})
    }

    $cfg.settings.dashboard.refreshSeconds = [int]$RefreshSeconds
    Test-Configuration -Config $cfg
    Save-ConfigurationAtomic -ConfigObject $cfg
    Update-Configuration -Force | Out-Null
}

function Update-TaskSchedule {
    param(
        [string]$TaskName,
        [int[]]$DaysOfWeek,
        [int[]]$Hours,
        [int[]]$Minutes
    )

    $cfg = Import-Configuration
    if (-not $cfg) { throw "Falha ao carregar config atual." }

    $target = $null
    foreach ($task in @($cfg.tasks)) {
        if ([string]$task.name -eq $TaskName) {
            $target = $task
            break
        }
    }

    if (-not $target) { throw "Tarefa '$TaskName' nao encontrada no config." }

    if (-not $target.schedule) {
        $target | Add-Member -MemberType NoteProperty -Name schedule -Value ([ordered]@{})
    }

    $target.schedule.daysOfWeek = @($DaysOfWeek | ForEach-Object { [int]$_ })
    $target.schedule.hours = @($Hours | ForEach-Object { [int]$_ })
    $target.schedule.minutes = @($Minutes | ForEach-Object { [int]$_ })

    Test-Configuration -Config $cfg
    Save-ConfigurationAtomic -ConfigObject $cfg
    Update-Configuration -Force | Out-Null
}

function Write-ApiJsonResponse {
    param(
        [System.Net.HttpListenerResponse]$Response,
        [int]$StatusCode,
        [hashtable]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 8 -Compress
    $bytes = $Utf8Encoding.GetBytes($json)

    $Response.StatusCode = $StatusCode
    $Response.ContentType = "application/json; charset=utf-8"
    $Response.Headers.Add("Access-Control-Allow-Origin", "*")
    $Response.Headers.Add("Access-Control-Allow-Headers", "Content-Type, X-Monitor-Token")
    $Response.Headers.Add("Access-Control-Allow-Methods", "POST, OPTIONS")
    $Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $Response.OutputStream.Flush()
    $Response.Close()
}

function Invoke-ApiOperationRequest {
    param([System.Net.HttpListenerContext]$Context)

    $request = $Context.Request
    $response = $Context.Response

    if ($request.HttpMethod -eq "OPTIONS") {
        Write-ApiJsonResponse -Response $response -StatusCode 200 -Payload @{ ok = $true; status = "PRELIGHT" }
        return
    }

    if ($request.HttpMethod -ne "POST") {
        Write-ApiJsonResponse -Response $response -StatusCode 405 -Payload @{ ok = $false; status = "METHOD_NOT_ALLOWED" }
        return
    }

    if ($request.Url.AbsolutePath -ne "/api/operations") {
        Write-ApiJsonResponse -Response $response -StatusCode 404 -Payload @{ ok = $false; status = "NOT_FOUND" }
        return
    }

    $token = [string]$request.Headers["X-Monitor-Token"]
    if ([string]::IsNullOrWhiteSpace($token) -or $token -ne $script:OperationsApiToken) {
        Write-ApiJsonResponse -Response $response -StatusCode 401 -Payload @{ ok = $false; status = "UNAUTHORIZED"; message = "Token invalido." }
        return
    }

    $body = ""
    $reader = New-Object System.IO.StreamReader($request.InputStream, $request.ContentEncoding)
    try {
        $body = $reader.ReadToEnd()
    }
    finally {
        $reader.Close()
        $reader.Dispose()
    }

    $payload = $null
    try {
        $payload = $body | ConvertFrom-Json
    }
    catch {
        Write-ApiJsonResponse -Response $response -StatusCode 400 -Payload @{ ok = $false; status = "BAD_REQUEST"; message = "JSON invalido." }
        return
    }

    $action = [string]$payload.action
    $opPayload = $payload.payload
    $taskName = if ($opPayload) { [string]$opPayload.taskName } else { "" }

    try {
        $result = $null
        switch ($action) {
            "run-now" {
                $result = Invoke-ManualTaskRun -TaskName $taskName
                break
            }
            "dry-run" {
                $result = Invoke-ManualTaskRun -TaskName $taskName -DryRun
                break
            }
            "toggle-enabled" {
                $task = Get-TaskByName -TaskName $taskName -ThrowIfMissing
                $newState = -not [bool]$task.enabled
                Update-TaskEnabledFlag -TaskName $taskName -Enabled $newState
                $result = [ordered]@{ status = "UPDATED"; message = "enabled=$newState" }
                break
            }
            "open-logs" {
                $task = Get-TaskByName -TaskName $taskName -ThrowIfMissing
                $scriptDir = Split-Path -Parent ([string]$task.scriptPath)
                $logPath = Join-Path $scriptDir "Logs"
                $result = [ordered]@{ status = "OK"; logPath = $logPath; message = "Caminho de log retornado." }
                break
            }
            "set-refresh" {
                $refreshSeconds = 0
                if (-not ($opPayload -and [int]::TryParse([string]$opPayload.refreshSeconds, [ref]$refreshSeconds))) {
                    throw "Informe payload.refreshSeconds inteiro."
                }
                Update-DashboardRefreshSetting -RefreshSeconds $refreshSeconds
                $result = [ordered]@{ status = "UPDATED"; message = "refreshSeconds=$refreshSeconds" }
                break
            }
            "set-schedule" {
                if (-not $opPayload) { throw "Payload ausente para set-schedule." }
                $days = @()
                $hours = @()
                $minutes = @()
                if ($opPayload.daysOfWeek) { $days = @($opPayload.daysOfWeek | ForEach-Object { [int]$_ }) }
                if ($opPayload.hours) { $hours = @($opPayload.hours | ForEach-Object { [int]$_ }) }
                if ($opPayload.minutes) { $minutes = @($opPayload.minutes | ForEach-Object { [int]$_ }) }
                if ($minutes.Count -eq 0) { throw "minutes nao pode ser vazio." }
                Update-TaskSchedule -TaskName $taskName -DaysOfWeek $days -Hours $hours -Minutes $minutes
                $result = [ordered]@{ status = "UPDATED"; message = "Agenda atualizada para '$taskName'." }
                break
            }
            "refresh-dashboard" {
                Save-DashboardState -Now (Get-Date)
                Save-DashboardHtml -Now (Get-Date)
                $result = [ordered]@{ status = "OK"; message = "Dashboard atualizado." }
                break
            }
            "dry-run-all" {
                Add-MetricCounter -MetricName "TasksDryRunEligible" -Delta ([int]$script:Config.tasks.Count)
                $result = [ordered]@{ status = "DRY_RUN"; message = "Dry run global registrado para $($script:Config.tasks.Count) tarefas." }
                break
            }
            default {
                throw "Acao nao suportada: $action"
            }
        }

        Write-Log "API operacao '$action' concluida. Task='$taskName'" -Type "INFO"
        Write-ApiJsonResponse -Response $response -StatusCode 200 -Payload @{ ok = $true; action = $action; result = $result }
    }
    catch {
        Write-Log "API falhou em '$action': $_" -Type "WARN"
        Write-ApiJsonResponse -Response $response -StatusCode 400 -Payload @{ ok = $false; action = $action; status = "ERROR"; message = "$_" }
    }
}

function Start-OperationsApi {
    if (-not $script:OperationsApiEnabled) {
        $script:OperationsApiStatus = "Desabilitada por configuracao."
        return
    }

    try {
        $listener = New-Object System.Net.HttpListener
        $listener.Prefixes.Add($script:OperationsApiPrefix)
        $listener.Start()
        $script:HttpListener = $listener
        $script:OperationsApiAsyncResult = $script:HttpListener.BeginGetContext($null, $null)
        $script:OperationsApiStatus = "Ativa em $($script:OperationsApiPrefix) (token: $($script:OperationsApiToken.Substring(0,8))...)."
        Write-Log "API local iniciada em $($script:OperationsApiPrefix)."
    }
    catch {
        $script:OperationsApiLastError = "$_"
        $script:OperationsApiStatus = "Falha ao iniciar API local."
        Write-Log "Falha ao iniciar API local: $_" -Type "WARN"
    }
}

function Stop-OperationsApi {
    try {
        if ($script:HttpListener) {
            if ($script:HttpListener.IsListening) {
                $script:HttpListener.Stop()
            }
            $script:HttpListener.Close()
        }
    }
    catch {}
    finally {
        $script:OperationsApiAsyncResult = $null
        $script:HttpListener = $null
    }
}

function Invoke-PendingApiRequests {
    if (-not ($script:HttpListener -and $script:HttpListener.IsListening)) { return }

    while ($script:HttpListener.IsListening -and $script:OperationsApiAsyncResult -and $script:OperationsApiAsyncResult.IsCompleted) {
        $context = $script:HttpListener.EndGetContext($script:OperationsApiAsyncResult)
        $script:OperationsApiAsyncResult = $script:HttpListener.BeginGetContext($null, $null)
        Invoke-ApiOperationRequest -Context $context
    }
}

if (-not (Update-Configuration -Force)) {
    $script:MonitorExitCode = 1
    Exit $script:MonitorExitCode
}

$script:PreviousMetricsSnapshot = Import-PreviousMetricsSnapshot
if ($script:PreviousMetricsSnapshot) {
    $previousGeneratedAt = [string]$script:PreviousMetricsSnapshot.generatedAt
    $previousCompleted = [int]$script:PreviousMetricsSnapshot.cumulative.TasksCompleted
    $previousNonZero = [int]$script:PreviousMetricsSnapshot.cumulative.TasksFinishedNonZero
    Write-Log "Snapshot anterior carregado. GeradoEm=$previousGeneratedAt | PrevConcluidas=$previousCompleted | PrevNaoZero=$previousNonZero"
}
else {
    Write-Log "Nenhum snapshot anterior de metricas encontrado. Iniciando baseline local."
}

Import-PreviousDashboardState

# Registra shutdown gracioso (encerra com log)
try {
    Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        Write-Log "Monitor encerrando (sinal de saída recebido)." -Type "WARN"
    } | Out-Null
}
catch {}

$executionMode = @()
if ($RunOnce) { $executionMode += "RunOnce" }
if ($SkipTaskExecution) { $executionMode += "SkipTaskExecution" }
if ($DryRun) { $executionMode += "DryRun" }
if ($executionMode.Count -eq 0) { $executionMode += "Normal" }

Write-Log "Monitor iniciado v3.6 (hot reload ativo). Tarefas carregadas: $($script:Config.tasks.Count) | Modo=$($executionMode -join ',')"
if ($SkipTaskExecution -and $DryRun) {
    Write-Log "SkipTaskExecution e DryRun ativos simultaneamente. SkipTaskExecution tera precedencia." -Type "WARN"
}
Start-OperationsApi
Save-MetricsSnapshot -WindowEnd (Get-Date)
Save-DashboardState -Now (Get-Date)
Save-DashboardHtml -Now (Get-Date)

$lastHeartbeat = Get-Date

while ($true) {
    try {
        Invoke-PendingApiRequests
        Remove-FinishedTasks
        Update-Configuration | Out-Null

        $agora = Get-Date
        $timeKey = $agora.ToString("yyyy-MM-dd HH:mm")

        # Heartbeat log a cada 1 hora
        if ($agora -gt $lastHeartbeat.AddHours(1)) {
            $windowMinutes = [math]::Round((New-TimeSpan -Start $script:MetricsWindowStartedAt -End $agora).TotalMinutes, 1)
            Write-Log "Heartbeat: Monitor ativo. EmExecucao=$($script:RunningTasks.Count) | Disparos=$($script:Metrics.TasksTriggered) | DryRunElegiveis=$($script:Metrics.TasksDryRunEligible) | Concluidas=$($script:Metrics.TasksCompleted) | NaoZero=$($script:Metrics.TasksFinishedNonZero) | WarnOperacional=$($script:Metrics.TasksFinishedWarn) | E7=$($script:Metrics.ExitCode7ReadOnly) | E23=$($script:Metrics.ExitCode23Cooldown) | E40=$($script:Metrics.ExitCode40Concurrent) | SkipsOverlap=$($script:Metrics.TasksSkippedOverlap) | ReloadOk=$($script:Metrics.ConfigReloadSuccess) | ReloadFail=$($script:Metrics.ConfigReloadFailure) | JanelaMin=$windowMinutes | WDisparos=$($script:MetricsWindow.TasksTriggered) | WDryRunElegiveis=$($script:MetricsWindow.TasksDryRunEligible) | WConcluidas=$($script:MetricsWindow.TasksCompleted) | WNaoZero=$($script:MetricsWindow.TasksFinishedNonZero) | WWarn=$($script:MetricsWindow.TasksFinishedWarn)"
            Save-MetricsSnapshot -WindowEnd $agora -ResetWindow
            $script:LastHeartbeatAt = $agora
            $lastHeartbeat = $agora
        }

        if ($SkipTaskExecution) {
            if (-not $script:SkipTaskExecutionLogged) {
                Write-Log "Modo SkipTaskExecution ativo. Disparo de tarefas suprimido para validacao segura." -Type "WARN"
                $script:SkipTaskExecutionLogged = $true
            }
        }
        elseif ($DryRun) {
            foreach ($task in $script:Config.tasks) {
                if (Test-TaskExecution -Task $task -Now $agora -TimeKey $timeKey) {
                    $taskName = [string]$task.name
                    $taskPath = [string]$task.scriptPath
                    Write-Log "DRY-RUN: tarefa '$taskName' seria disparada neste ciclo. Script=$taskPath" -Type "WARN"
                    $script:StateControl[$taskName] = $timeKey
                    Add-MetricCounter -MetricName "TasksDryRunEligible"
                }
            }
        }
        else {
            foreach ($task in $script:Config.tasks) {
                if (Test-TaskExecution -Task $task -Now $agora -TimeKey $timeKey) {
                    Invoke-ScheduledTask -Task $task -Now $agora
                }
            }
        }

        if ($agora.Minute -eq 0 -and $agora.Second -lt 10) {
            [System.GC]::Collect()
        }

        Save-DashboardState -Now $agora
        Save-DashboardHtml -Now $agora

        if ($RunOnce) {
            Write-Log "RunOnce ativo. Encerrando monitor apos ciclo unico." -Type "WARN"
            break
        }

        $sleepTime = if ($script:Config.settings.checkIntervalSeconds) {
            [int]$script:Config.settings.checkIntervalSeconds
        }
        else {
            20
        }

        Start-Sleep -Seconds $sleepTime
        $script:MainLoopConsecutiveErrors = 0
    }
    catch {
        $script:MainLoopConsecutiveErrors++
        Write-Log "ERRO CRÍTICO no Loop Principal: $_ | Falhas consecutivas=$($script:MainLoopConsecutiveErrors)/$($script:MainLoopMaxConsecutiveErrors)" -Type "ERRO"

        if ($script:MainLoopConsecutiveErrors -ge $script:MainLoopMaxConsecutiveErrors) {
            Write-Log "Limite de falhas consecutivas atingido. Encerrando monitor para evitar estado inconsistente." -Type "ERRO"
            $script:MonitorExitCode = 1
            break
        }

        Start-Sleep -Seconds 30
    }
}

Save-MetricsSnapshot -WindowEnd (Get-Date)
Save-DashboardState -Now (Get-Date)
Save-DashboardHtml -Now (Get-Date)
Stop-OperationsApi

try {
    if ($script:MonitorMutex) {
        if ($script:MutexAcquired) {
            $script:MonitorMutex.ReleaseMutex()
            $script:MutexAcquired = $false
        }
        $script:MonitorMutex.Dispose()
    }
}
catch {}

Exit $script:MonitorExitCode

