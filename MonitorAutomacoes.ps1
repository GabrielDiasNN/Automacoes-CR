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
        $line = "[$timestamp] [$Type] $Message"
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
        [string]$LogDir
    )

    $desc = ""
    if ($script:Config.settings.exitCodeMap -and $script:Config.settings.exitCodeMap."$ExitCode") {
        $desc = " - $($script:Config.settings.exitCodeMap."$ExitCode")"
    }

    Register-TaskCompletionMetrics -ExitCode $ExitCode
    $logType = Get-ExitCodeLogType -ExitCode $ExitCode

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
    $line = "[$timestamp] [$type] $msg"

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
        return (Get-FileHash -Path $Path -Algorithm SHA256 -ErrorAction Stop).Hash
    }
    catch {
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
        Add-MetricCounter -MetricName "ConfigReloadFailure"
        return $false
    }

    $currentWrite = (Get-Item $ConfigFilePath).LastWriteTime
    $currentHash = Get-ConfigHash -Path $ConfigFilePath

    if (-not $currentHash) {
        Write-Log "Falha ao calcular hash de config.json em $ConfigFilePath" -Type "ERRO"
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
                Write-Log "Falha ao carregar config.json (tentativa $attempt/$maxAttempts). Nova tentativa em 2s." -Type "WARN"
                Start-Sleep -Seconds 2
            }
        }

        if (-not $newConfig) {
            Write-Log "Falha ao carregar config.json após $maxAttempts tentativas. Mantendo configuração atual." -Type "ERRO"
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

        if (Test-Path $EmergencyLog) {
            Remove-Item $EmergencyLog -ErrorAction SilentlyContinue
        }

        Write-Log "Configuração recarregada com sucesso. Tarefas: $($script:Config.tasks.Count) (antes: $previousCount) | Hash=$($currentHash.Substring(0,8))"
        Add-MetricCounter -MetricName "ConfigReloadSuccess"
        return $true
    }

    return $true
}

function Remove-FinishedTasks {
    $toRemove = @()
    $logDir = Get-LogDirectory

    foreach ($taskName in $script:RunningTasks.Keys) {
        $proc = $script:RunningTasks[$taskName]
        if ($null -eq $proc) {
            $toRemove += $taskName
            continue
        }

        try {
            if ($proc.HasExited) {
                $exitCode = $proc.ExitCode
                Write-TaskCompletionLog -TaskName $taskName -ExitCode $exitCode -ProcessId $proc.Id -LogDir $logDir
                $toRemove += $taskName
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
        [bool]$WaitForExit = $false
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
            $script:RunningTasks[$Name] = $proc
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
            $proc = $script:RunningTasks[$taskName]
            if ($proc -and -not $proc.HasExited) {
                Write-Log "Tarefa '$taskName' ignorada por sobreposição. PID em execução=$($proc.Id)" -Type "WARN" -LogDir $logDir
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
    $started = Start-TaskProcess -Path ([string]$Task.scriptPath) -Name $taskName -LogDir $logDir -WaitForExit $waitForExit

    if ($started) {
        $script:StateControl[$taskName] = $Now.ToString("yyyy-MM-dd HH:mm")
        Add-MetricCounter -MetricName "TasksTriggered"
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
Save-MetricsSnapshot -WindowEnd (Get-Date)

$lastHeartbeat = Get-Date

while ($true) {
    try {
        Remove-FinishedTasks
        Update-Configuration | Out-Null

        $agora = Get-Date
        $timeKey = $agora.ToString("yyyy-MM-dd HH:mm")

        # Heartbeat log a cada 1 hora
        if ($agora -gt $lastHeartbeat.AddHours(1)) {
            $windowMinutes = [math]::Round((New-TimeSpan -Start $script:MetricsWindowStartedAt -End $agora).TotalMinutes, 1)
            Write-Log "Heartbeat: Monitor ativo. EmExecucao=$($script:RunningTasks.Count) | Disparos=$($script:Metrics.TasksTriggered) | DryRunElegiveis=$($script:Metrics.TasksDryRunEligible) | Concluidas=$($script:Metrics.TasksCompleted) | NaoZero=$($script:Metrics.TasksFinishedNonZero) | WarnOperacional=$($script:Metrics.TasksFinishedWarn) | E7=$($script:Metrics.ExitCode7ReadOnly) | E23=$($script:Metrics.ExitCode23Cooldown) | E40=$($script:Metrics.ExitCode40Concurrent) | SkipsOverlap=$($script:Metrics.TasksSkippedOverlap) | ReloadOk=$($script:Metrics.ConfigReloadSuccess) | ReloadFail=$($script:Metrics.ConfigReloadFailure) | JanelaMin=$windowMinutes | WDisparos=$($script:MetricsWindow.TasksTriggered) | WDryRunElegiveis=$($script:MetricsWindow.TasksDryRunEligible) | WConcluidas=$($script:MetricsWindow.TasksCompleted) | WNaoZero=$($script:MetricsWindow.TasksFinishedNonZero) | WWarn=$($script:MetricsWindow.TasksFinishedWarn)"
            Save-MetricsSnapshot -WindowEnd $agora -ResetWindow
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
