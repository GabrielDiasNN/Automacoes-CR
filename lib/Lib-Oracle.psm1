<#
.SYNOPSIS
    Biblioteca compartilhada para invocacao de scripts Python Oracle com retry padronizado.
.DESCRIPTION
    Fornece Invoke-OraclePythonScript: wrapper unificado sobre Invoke-NativeProcess +
    Invoke-WithRetry para as automacoes que invocam extracao Oracle via Python.
    Elimina a duplicacao do padrao retry+log-forward nos run.ps1 de Receitas Bloqueadas,
    Receitas Emitidas e Montagem de Terceirizados.
.NOTES
    Version: 1.0.0
    Skill: protocolo-valeg, ai-native-development-standard
    VALEG: A-Arquitetura (Retry), L-Logging (forwarding padronizado)
#>

$ErrorActionPreference = "Stop"

function Invoke-OraclePythonScript {
    <#
    .SYNOPSIS
        Executa um script Python com retry, log-forwarding e deteccao de idempotencia.
    .PARAMETER PythonExe
        Caminho para o executavel Python do ambiente virtual.
    .PARAMETER ScriptPath
        Caminho absoluto para o script Python a executar.
    .PARAMETER ExecId
        Identificador da execucao corrente (correlacao de logs).
    .PARAMETER LogPath
        Caminho para o arquivo de log JSONL da automacao.
    .PARAMETER OperationName
        Nome legivel da operacao para logs de retry.
    .PARAMETER MaxAttempts
        Numero maximo de tentativas. Default: 3.
    .PARAMETER BackoffSeconds
        Array com backoff em segundos por tentativa. Default: @(30, 60, 120).
    .PARAMETER InputData
        Dados a serem passados via stdin para o processo Python.
    .OUTPUTS
        [PSCustomObject] com campos: Success, Idempotent, Output, ExitCode.
        Success=true  -> script concluiu normalmente.
        Idempotent=true -> script retornou ExitCode 2 (sem alteracoes detectadas).
        O chamador decide o exit code apropriado para cada caso.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$PythonExe,
        [Parameter(Mandatory)] [string]$ScriptPath,
        [Parameter(Mandatory)] [string]$ExecId,
        [Parameter(Mandatory)] [string]$LogPath,
        [string]$OperationName  = "Oracle Python Script",
        [ValidateSet("preflight", "lock", "extract", "transform", "dispatch", "commit", "cleanup", "custom")]
        [string]$Step           = "extract",
        [int]$MaxAttempts       = 3,
        [int[]]$BackoffSeconds  = @(30, 60, 120),
        [string]$InputData      = "",
        # IPC via stdio: o script filho escreve o PAYLOAD DE DADOS em stdout
        # (capturado em .Output e repassado adiante). Nesse caso as linhas de
        # stdout (Level=INFO no ProcessRunner) NAO devem virar log — so as de
        # stderr (Level=WARN). Ex.: Receitas Emitidas (extract -> HTML).
        [switch]$StdoutIsData,
        # Exit codes nao-transitorios (5=deterministico/bloqueado, 6=worker offline,
        # 7=timeout) nao devem disparar novas rodadas de retry PowerShell.
        [int[]]$NonRetryableExitCodes = @(5, 6, 7)
    )

    $state = @{ Idempotent = $false; NonRetryable = $false; Output = [string]::Empty; ExitCode = -1 }
    $stdoutIsDataFlag = [bool]$StdoutIsData

    $forwardStructured = ($null -ne (Get-Command Write-HubForwardedLine -ErrorAction SilentlyContinue)) -and `
        ($null -ne (Get-Command Get-HubLogContext -ErrorAction SilentlyContinue)) -and `
        ($null -ne (Get-HubLogContext))

    $ok = Invoke-WithRetry -MaxAttempts $MaxAttempts -BackoffSeconds $BackoffSeconds `
        -OperationName $OperationName -Step $Step -ExecId $ExecId -LogPath $LogPath `
        -Action {
            $invokeParams = @{
                FilePath  = $PythonExe
                Arguments = "`"$ScriptPath`" `"$ExecId`""
                LogAction = {
                    param($msg, $lvl)
                    if ([string]::IsNullOrWhiteSpace($msg)) { return }
                    # stdout do ProcessRunner vem como INFO; se for canal de dados, ignora.
                    if ($stdoutIsDataFlag -and $lvl -eq "INFO") { return }
                    if ($forwardStructured) {
                        Write-HubForwardedLine -Line $msg -FallbackLevel $lvl -Step $Step
                    } else {
                        Write-AutomacaoLog -Message $msg -Level $lvl -ExecId $ExecId -LogPath $LogPath
                    }
                }
            }
            if (-not [string]::IsNullOrEmpty($InputData)) { $invokeParams['InputData'] = $InputData }

            $res = Invoke-NativeProcess @invokeParams
            $state['ExitCode'] = $res.ExitCode
            $state['Output']   = $res.StandardOutput

            if ($res.ExitCode -eq 2) {
                $state['Idempotent'] = $true
                return $true
            }
            if ($res.ExitCode -ne 0) {
                if ($res.ExitCode -in $NonRetryableExitCodes) {
                    $state['NonRetryable'] = $true
                    $nonRetryEx = New-Object System.Exception "Python '$([System.IO.Path]::GetFileName($ScriptPath))' retornou ExitCode nao-transitorio $($res.ExitCode)."
                    $nonRetryEx.Data['NonRetryable'] = $true
                    $nonRetryEx.Data['ExitCode'] = $res.ExitCode
                    throw $nonRetryEx
                }
                throw "Python '$([System.IO.Path]::GetFileName($ScriptPath))' retornou ExitCode=$($res.ExitCode)."
            }
            return $true
        }

    return [PSCustomObject]@{
        Success      = [bool]$ok -and (-not $state['Idempotent'])
        Idempotent   = $state['Idempotent']
        NonRetryable = $state['NonRetryable']
        Output       = $state['Output']
        ExitCode     = $state['ExitCode']
    }
}

function Resolve-OracleFailureExitCode {
    <#
    .SYNOPSIS
        Mapeia ExitCode de erro Python da camada Oracle para ExitCode canonico do Orchestrator.
    #>
    [CmdletBinding()]
    [OutputType([int])]
    param(
        [int]$ExitCode = 1,
        [int]$DefaultExitCode = 3
    )

    switch ($ExitCode) {
        6 { return 26 }  # ORACLE_WORKER_OFFLINE
        7 { return 27 }  # ORACLE_QUEUE_TIMEOUT
        default { return $DefaultExitCode }
    }
}

function Test-OraclePreFlightOutrosChecksOk {
    <#
    .SYNOPSIS
        Executa o bloco que reavalia os checks do pre-flight que NAO sao do worker Oracle.
    .DESCRIPTION
        Devolve $true somente se o ultimo valor produzido pelo bloco for $true. Qualquer
        excecao ou saida sem booleano conta como reprovacao: na duvida, nao reenfileirar.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Bloco
    )

    try {
        $saida = @(& $Bloco)
        if ($saida.Count -eq 0) { return $false }
        $ultimo = $saida[-1]
        return (($ultimo -is [bool]) -and [bool]$ultimo)
    }
    catch [System.Exception] {
        return $false
    }
}

function Get-OraclePreFlightExitCode {
    <#
    .SYNOPSIS
        Retorna o ExitCode canonico de falha no pre-flight Oracle.
        - Modo queue, pasta da fila resolvida, worker offline e nenhum outro check reprovado: 26
          (ORACLE_WORKER_OFFLINE, reenfileirado pelo Orchestrator quando o heartbeat do worker voltar).
        - Modo queue, worker offline e outro check reprovado (script ausente, config WhatsApp etc.): 9.
          Falha deterministica somada ao worker parado nao pode virar 26: seria reenfileirada
          ignorando max_retries.
        - Modo queue sem pasta da fila resolvida: 9 (erro de configuracao, deterministico).
          A pasta vem de ORACLE_QUEUE_DIR (processo ou .env) ou, na falta dela, do
          DEFAULT_QUEUE_DIR de lib/python/oracle_queue.py; quem resolve e o proprio
          Test-OracleQueueWorkerAlive. So sem nenhuma das duas fontes e configuracao quebrada.
        - Qualquer outro modo: 9 (PREFLIGHT_FAILED, exige revisao antes de requeue).
    .PARAMETER OutrosChecks
        ScriptBlock que reavalia o pre-flight SEM o check do worker Oracle e devolve $true se
        tudo passou. E avaliado somente quando o worker esta offline no modo queue. Sem o
        parametro, vale o comportamento anterior (26 para worker offline).
    #>
    [CmdletBinding()]
    [OutputType([int])]
    param(
        [scriptblock]$OutrosChecks
    )

    $driverMode = [System.Environment]::GetEnvironmentVariable("ORACLE_DRIVER_MODE", "Process")
    if ([string]::IsNullOrWhiteSpace($driverMode) -and (Get-Command Get-EnvFileValue -ErrorAction SilentlyContinue)) {
        $driverMode = Get-EnvFileValue -Key "ORACLE_DRIVER_MODE"
    }
    if ([string]::IsNullOrWhiteSpace($driverMode)) { $driverMode = "" }
    if ($driverMode.Trim() -eq "queue" -and (Get-Command Test-OracleQueueWorkerAlive -ErrorAction SilentlyContinue)) {
        $status = Test-OracleQueueWorkerAlive
        if (-not $status.Alive) {
            # Pasta vazia depois de todos os fallbacks: configuracao quebrada, nao worker
            # offline. Reenfileirar (26) repetiria o mesmo erro indefinidamente.
            if ([string]::IsNullOrWhiteSpace([string]$status.QueueDir)) { return 9 }
            # Outro check reprovado junto com o worker parado: a falha e deterministica.
            if (($null -ne $OutrosChecks) -and (-not (Test-OraclePreFlightOutrosChecksOk -Bloco $OutrosChecks))) { return 9 }
            return 26
        }
    }
    return 9
}
