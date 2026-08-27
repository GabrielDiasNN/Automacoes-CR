<#
.SYNOPSIS
    Emissao de eventos de log estruturados do Hub (JSON Lines).
.DESCRIPTION
    Contrato unico definido em docs/log-event.schema.json e docs/logging-standard.md.
    Cada evento e emitido como UMA linha JSON em stdout (Write-Host) E anexado ao
    arquivo Logs/<slug>.jsonl. stderr fica reservado para rastro humano.

    Ciclo de vida: Write-HubExecutionStart -> Write-HubStepStart/End (por etapa)
    -> Write-HubRetryAttempt (dentro do retry) -> Write-HubExecutionEnd.

    O mascaramento reaproveita Protect-SensitiveData de Lib-Logging.psm1 quando
    disponivel (defesa em profundidade: o Orchestrator revalida na ingestao).
.NOTES
    Version: 1.0.0
    Skill: ai-native-development-standard
#>

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8

$script:HubLogCtx = $null
$script:HubLogSteps = [System.Collections.Generic.List[object]]::new()

# ------------------------------------------------------------------------------
# New-HubTraceId  /  Resolve-HubTraceId
# ------------------------------------------------------------------------------
function New-HubTraceId {
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory = $true)][string]$Slug)

    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $suffix = "{0:x4}" -f (Get-Random -Minimum 0 -Maximum 65536)
    return "$Slug-$stamp-$suffix"
}

function Resolve-HubTraceId {
    <#
    .SYNOPSIS
        Herda HUB_TRACE_ID do processo pai (worker/run.ps1) ou cria um novo.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory = $true)][string]$Slug)

    $inherited = [Environment]::GetEnvironmentVariable("HUB_TRACE_ID", "Process")
    if (-not [string]::IsNullOrWhiteSpace($inherited)) { return $inherited }
    return (New-HubTraceId -Slug $Slug)
}

# ------------------------------------------------------------------------------
# Initialize-HubLogContext
# ------------------------------------------------------------------------------
function Initialize-HubLogContext {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Automation,
        [Parameter(Mandatory = $true)][string]$ExecId,
        [Parameter(Mandatory = $true)][string]$TraceId,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [ValidateSet("ps_script", "orchestrator_api", "orchestrator_worker", "orchestrator_scheduler")]
        [string]$Component = "ps_script"
    )

    $env:HUB_TRACE_ID = $TraceId

    $envStr = $env:ENVIRONMENT
    if ([string]::IsNullOrWhiteSpace($envStr)) { $envStr = "PRD" }

    $script:HubLogCtx = [ordered]@{
        Automation = $Automation
        ExecId     = $ExecId
        TraceId    = $TraceId
        Component  = $Component
        LogPath    = $LogPath
        Env        = $envStr
        StartedAt  = [DateTime]::UtcNow
    }
    $script:HubLogSteps = [System.Collections.Generic.List[object]]::new()
}

function Get-HubLogContext { return $script:HubLogCtx }

function Clear-HubLogContext {
    <#
    .SYNOPSIS
        Zera o contexto de log estruturado. Usado por testes; um run.ps1 normal
        encerra o processo e nao precisa chamar.
    #>
    [CmdletBinding()]
    param()
    $script:HubLogCtx = $null
    $script:HubLogSteps = [System.Collections.Generic.List[object]]::new()
}

# ------------------------------------------------------------------------------
# Write-HubLogEvent  (nucleo de emissao)
# ------------------------------------------------------------------------------
function Write-HubLogEvent {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("execution.start", "execution.end", "step.start", "step.end", "retry.attempt", "log")]
        [string]$Event,

        [ValidateSet("INFO", "WARN", "ERRO", "DEBUG")]
        [string]$Level = "INFO",

        [string]$Message = "",
        [string]$Step,
        [string]$StepName,

        # Campos adicionais especificos do evento (attempt, duration_ms, ok,
        # outcome_code, outcome_reason, record_counts, steps).
        [hashtable]$Extra
    )

    if (-not $script:HubLogCtx) {
        throw "Initialize-HubLogContext deve ser chamado antes de Write-HubLogEvent."
    }
    $ctx = $script:HubLogCtx

    $clean = $Message
    if (Get-Command Protect-SensitiveData -ErrorAction SilentlyContinue) {
        $clean = Protect-SensitiveData $Message
    }

    $evt = [ordered]@{
        ts         = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        level      = $Level
        component  = $ctx.Component
        event      = $Event
        automation = $ctx.Automation
        exec_id    = $ctx.ExecId
        trace_id   = $ctx.TraceId
        message    = $clean
    }
    if ($ctx.Env -and $ctx.Env -ne "PRD") { $evt["env"] = $ctx.Env }
    if ($Step) { $evt["step"] = $Step }
    if ($StepName) { $evt["step_name"] = $StepName }
    if ($Extra) {
        foreach ($k in $Extra.Keys) { $evt[$k] = $Extra[$k] }
    }

    $jsonLine = ($evt | ConvertTo-Json -Depth 8 -Compress)

    try {
        $logDir = Split-Path -Parent $ctx.LogPath
        if ($logDir -and -not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        }
        [System.IO.File]::AppendAllText($ctx.LogPath, "$jsonLine`r`n", [System.Text.Encoding]::UTF8)
    } catch [System.Exception] {
        Write-Verbose ("Falha ao persistir evento de log: {0}" -f $_.Exception.Message)
    }

    # stdout: exclusivamente a linha JSON (contrato do canal).
    Write-Host $jsonLine
}

# ------------------------------------------------------------------------------
# Test-HubLogEnvelope / Write-HubForwardedLine
# ------------------------------------------------------------------------------
$script:HubEnvelopeKeys = @("ts", "level", "component", "event", "automation", "exec_id", "trace_id", "message")

function Test-HubLogEnvelope {
    <#
    .SYNOPSIS
        True quando a linha ja e um evento de log completo no envelope do schema
        (emitido por um processo filho ja migrado). Nesse caso o run.ps1 apenas
        encaminha a linha, sem re-embrulhar.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param([string]$Line)

    if ([string]::IsNullOrWhiteSpace($Line)) { return $false }
    $trimmed = $Line.Trim()
    if (-not $trimmed.StartsWith("{")) { return $false }
    try {
        $obj = $trimmed | ConvertFrom-Json -ErrorAction Stop
    } catch [System.Exception] { return $false }
    $names = @($obj.PSObject.Properties.Name)
    foreach ($k in $script:HubEnvelopeKeys) {
        if ($names -notcontains $k) { return $false }
    }
    return $true
}

function Write-HubForwardedLine {
    <#
    .SYNOPSIS
        Encaminha uma linha de saida de processo filho para o log estruturado.

        Envelope completo -> anexa ao arquivo e ecoa em stdout verbatim.
        Texto avulso      -> embrulha como evento `log` (nivel derivado do texto
                             ou do fallback informado).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Line,
        [string]$FallbackLevel = "INFO",
        [string]$Step
    )
    if ([string]::IsNullOrWhiteSpace($Line)) { return }

    if (Test-HubLogEnvelope -Line $Line) {
        $jsonLine = $Line.Trim()
        $ctx = $script:HubLogCtx
        if ($ctx) {
            try {
                [System.IO.File]::AppendAllText($ctx.LogPath, "$jsonLine`r`n", [System.Text.Encoding]::UTF8)
            } catch [System.Exception] {
                Write-Verbose ("Falha ao encaminhar evento: {0}" -f $_.Exception.Message)
            }
        }
        Write-Host $jsonLine
        return
    }

    $lvl = $FallbackLevel
    if (Get-Command Get-ForwardedLogLevel -ErrorAction SilentlyContinue) {
        $lvl = Get-ForwardedLogLevel -Msg $Line -Fallback $FallbackLevel
    }
    Write-HubLogEvent -Event "log" -Level $lvl -Message $Line -Step $Step
}

# ------------------------------------------------------------------------------
# Wrappers de ciclo de vida
# ------------------------------------------------------------------------------
function Write-HubExecutionStart {
    [CmdletBinding()]
    param([string]$Message = "Inicio da execucao")
    $script:HubLogSteps = [System.Collections.Generic.List[object]]::new()
    Write-HubLogEvent -Event "execution.start" -Level "INFO" -Message $Message
}

function Write-HubStepStart {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("preflight", "lock", "extract", "transform", "dispatch", "commit", "cleanup", "custom")]
        [string]$Step,
        [string]$StepName,
        [string]$Message = ""
    )
    Write-HubLogEvent -Event "step.start" -Level "INFO" -Message $Message -Step $Step -StepName $StepName
}

function Write-HubStepEnd {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("preflight", "lock", "extract", "transform", "dispatch", "commit", "cleanup", "custom")]
        [string]$Step,
        [string]$StepName,
        [Parameter(Mandatory = $true)][bool]$Ok,
        [Parameter(Mandatory = $true)][int]$DurationMs,
        [string]$Message = ""
    )
    $entry = [ordered]@{ step = $Step; ok = $Ok; duration_ms = $DurationMs }
    if ($StepName) { $entry["step_name"] = $StepName }
    $script:HubLogSteps.Add($entry)

    $lvl = if ($Ok) { "INFO" } else { "WARN" }
    Write-HubLogEvent -Event "step.end" -Level $lvl -Message $Message -Step $Step -StepName $StepName `
        -Extra @{ ok = $Ok; duration_ms = $DurationMs }
}

function Write-HubRetryAttempt {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("preflight", "lock", "extract", "transform", "dispatch", "commit", "cleanup", "custom")]
        [string]$Step,
        [Parameter(Mandatory = $true)][int]$Attempt,
        [Parameter(Mandatory = $true)][int]$MaxAttempts,
        [ValidateSet("INFO", "WARN", "ERRO", "DEBUG")]
        [string]$Level = "INFO",
        [string]$Message = ""
    )
    Write-HubLogEvent -Event "retry.attempt" -Level $Level -Message $Message -Step $Step `
        -Extra @{ attempt = $Attempt; max_attempts = $MaxAttempts }
}

function Write-HubExecutionEnd {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][int]$OutcomeCode,
        [Parameter(Mandatory = $true)][string]$OutcomeReason,
        [int]$DurationMs = -1,
        [string]$Message = "",
        [hashtable]$RecordCounts,
        [object[]]$Steps
    )
    if ($DurationMs -lt 0) {
        $startedAt = if ($script:HubLogCtx) { $script:HubLogCtx.StartedAt } else { $null }
        $DurationMs = if ($startedAt) {
            [int][Math]::Round(([DateTime]::UtcNow - $startedAt).TotalMilliseconds)
        } else { 0 }
    }
    $stepList = if ($null -ne $Steps) { $Steps } else { $script:HubLogSteps.ToArray() }

    $lvl = if ($OutcomeCode -in @(0, 2, 22)) { "INFO" }
    elseif ($OutcomeCode -in @(24, 25)) { "WARN" }
    else { "ERRO" }

    $extra = [ordered]@{
        outcome_code   = $OutcomeCode
        outcome_reason = $OutcomeReason
        duration_ms    = $DurationMs
        steps          = @($stepList)
    }
    if ($RecordCounts -and $RecordCounts.Count -gt 0) { $extra["record_counts"] = $RecordCounts }

    Write-HubLogEvent -Event "execution.end" -Level $lvl -Message $Message -Extra $extra
}

Export-ModuleMember -Function `
    New-HubTraceId, Resolve-HubTraceId, Initialize-HubLogContext, Get-HubLogContext, Clear-HubLogContext, `
    Write-HubLogEvent, Test-HubLogEnvelope, Write-HubForwardedLine, `
    Write-HubExecutionStart, Write-HubStepStart, Write-HubStepEnd, `
    Write-HubRetryAttempt, Write-HubExecutionEnd
