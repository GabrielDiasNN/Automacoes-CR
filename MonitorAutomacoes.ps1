# ==============================================================================
# ARQUIVO: MonitorAutomacoes.ps1
# VERSÃO: 3.5
# ==============================================================================

$ErrorActionPreference = "Stop"

$Utf8Bom   = New-Object System.Text.UTF8Encoding($true)
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
try {
    [Console]::InputEncoding  = $Utf8NoBom
    [Console]::OutputEncoding = $Utf8NoBom
    $OutputEncoding = $Utf8NoBom
} catch {}

$MutexName = "Global\MonitorAutomacoesMutex"
$MutexCreated = $false
try {
    # Mantemos o objeto Mutex no escopo do script para garantir que ele não seja coletado
    # pelo Garbage Collector enquanto o monitor estiver rodando.
    $script:MonitorMutex = New-Object System.Threading.Mutex($true, $MutexName, [ref]$MutexCreated)
} catch {
    Write-Host "ERRO: Falha crítica ao inicializar Mutex: $_" -ForegroundColor Red
    Exit
}

if (-not $MutexCreated) {
    Write-Host "AVISO: Já existe uma instância do MonitorAutomacoes em execução." -ForegroundColor Yellow
    Exit
}

$ScriptPath = $PSScriptRoot
if (-not $ScriptPath) { $ScriptPath = "C:\Automacoes" }

$ConfigFilePath = Join-Path $ScriptPath "config.json"
$EmergencyLog   = Join-Path $ScriptPath "Startup_Error.txt"

$script:Config = $null
$script:ConfigLastWrite = $null
$script:RunningTasks = @{}
$script:StateControl = @{}

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

    $sw = New-Object System.IO.StreamWriter($FilePath, $true, $Utf8Bom)
    try {
        $sw.WriteLine($Line)
        $sw.Flush()
    } finally {
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

    $sw = New-Object System.IO.StreamWriter($FilePath, $false, $Utf8Bom)
    try {
        $sw.Write($Content)
        $sw.Flush()
    } finally {
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

    $fileName  = "$(Get-Date -Format 'yyyy-MM')_Monitor.log"
    $logPath   = Join-Path -Path $LogDir -ChildPath $fileName
    $timestamp = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    $line      = "[$timestamp] [$type] $msg"

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

function Test-Configuration {
    param($Config)

    if (-not $Config) { throw "Configuração vazia." }
    if (-not $Config.settings) { throw "Bloco 'settings' ausente." }
    if (-not $Config.tasks) { throw "Bloco 'tasks' ausente." }

    $names = @{}
    foreach ($task in $Config.tasks) {
        $structureError = Test-TaskStructure -Task $task
        if ($structureError) { throw $structureError }

        $taskName = [string]$task.name
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
    } catch {
        $err = "ERRO CRÍTICO: Falha ao carregar config.json. Detalhes: $_"
        Set-Utf8Content -FilePath $EmergencyLog -Content $err
        return $null
    }
}

function Update-Configuration {
    param([switch]$Force)

    if (-not (Test-Path $ConfigFilePath)) {
        Write-Log "Arquivo config.json não encontrado em $ConfigFilePath" -Type "ERRO"
        return $false
    }

    $currentWrite = (Get-Item $ConfigFilePath).LastWriteTime

    if ($Force -or $null -eq $script:ConfigLastWrite -or $currentWrite -ne $script:ConfigLastWrite) {
        $newConfig = Import-Configuration
        if (-not $newConfig) { return $false }

        $previousCount = 0
        if ($script:Config -and $script:Config.tasks) {
            $previousCount = $script:Config.tasks.Count
        }

        $script:Config = $newConfig
        $script:ConfigLastWrite = $currentWrite

        if (Test-Path $EmergencyLog) {
            Remove-Item $EmergencyLog -ErrorAction SilentlyContinue
        }

        Write-Log "Configuração recarregada com sucesso. Tarefas: $($script:Config.tasks.Count) (antes: $previousCount)"
        return $true
    }

    return $true
}

function Remove-FinishedTasks {
    $toRemove = @()

    foreach ($taskName in $script:RunningTasks.Keys) {
        $proc = $script:RunningTasks[$taskName]
        if ($null -eq $proc) {
            $toRemove += $taskName
            continue
        }

        try {
            if ($proc.HasExited) {
                $exitCode = $proc.ExitCode
                $desc = ""
                if ($script:Config.settings.exitCodeMap -and $script:Config.settings.exitCodeMap."$exitCode") {
                    $desc = " - $($script:Config.settings.exitCodeMap."$exitCode")"
                }

                if ($exitCode -ne 0) {
                    Write-Log "Tarefa '$taskName' finalizada com ERRO. ExitCode=$exitCode$desc PID=$($proc.Id)" -Type "ERRO"
                } else {
                    Write-Log "Tarefa '$taskName' finalizada. ExitCode=$exitCode$desc PID=$($proc.Id)"
                }
                $toRemove += $taskName
            }
        } catch {
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
        } elseif ($ext -eq ".ps1") {
            $proc = Start-Process "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$Path`" `"$execId`"" -WindowStyle Hidden -PassThru -ErrorAction Stop
        } else {
            throw "Extensão '$ext' não suportada."
        }

        Write-Log "Tarefa '$Name' iniciada. [ExecId=$execId] PID=$($proc.Id) | Script=$Path" -LogDir $LogDir

        if ($WaitForExit) {
            $proc.WaitForExit()
            Write-Log "Tarefa '$Name' finalizada em modo síncrono. [ExecId=$execId] ExitCode=$($proc.ExitCode) PID=$($proc.Id)" -LogDir $LogDir
        } else {
            $script:RunningTasks[$Name] = $proc
        }

        return $true
    } catch {
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
    $min  = $Now.Minute

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
                return
            }
        } catch {}
    }

    Write-Log "DISPARANDO: $taskName" -LogDir $logDir
    $started = Start-TaskProcess -Path ([string]$Task.scriptPath) -Name $taskName -LogDir $logDir -WaitForExit $waitForExit

    if ($started) {
        $script:StateControl[$taskName] = $Now.ToString("yyyy-MM-dd HH:mm")
    }
}

if (-not (Update-Configuration -Force)) { Exit }

# Registra shutdown gracioso (encerra com log)
try {
    Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
        Write-Log "Monitor encerrando (sinal de saída recebido)." -Type "WARN"
    } | Out-Null
} catch {}

Write-Log "Monitor iniciado v3.5 (hot reload ativo). Tarefas carregadas: $($script:Config.tasks.Count)"

$lastHeartbeat = Get-Date

while ($true) {
    try {
        Remove-FinishedTasks
        Update-Configuration | Out-Null

    $agora = Get-Date
    $timeKey = $agora.ToString("yyyy-MM-dd HH:mm")

        # Heartbeat log a cada 1 hora
        if ($agora -gt $lastHeartbeat.AddHours(1)) {
            Write-Log "Heartbeat: Monitor ativo. Tarefas em execução: $($script:RunningTasks.Count)"
            $lastHeartbeat = $agora
        }

    foreach ($task in $script:Config.tasks) {
        if (Test-TaskExecution -Task $task -Now $agora -TimeKey $timeKey) {
            Invoke-ScheduledTask -Task $task -Now $agora
        }
    }

    if ($agora.Minute -eq 0 -and $agora.Second -lt 10) {
        [System.GC]::Collect()
    }

    $sleepTime = if ($script:Config.settings.checkIntervalSeconds) {
        [int]$script:Config.settings.checkIntervalSeconds
    } else {
        20
    }

    Start-Sleep -Seconds $sleepTime
    } catch {
        Write-Log "ERRO CRÍTICO no Loop Principal: $_" -Type "ERRO"
        Start-Sleep -Seconds 30
    }
}
