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
        [string]$InputData      = ""
    )

    $state = @{ Idempotent = $false; Output = [string]::Empty; ExitCode = -1 }

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
                throw "Python '$([System.IO.Path]::GetFileName($ScriptPath))' retornou ExitCode=$($res.ExitCode)."
            }
            return $true
        }

    return [PSCustomObject]@{
        Success    = [bool]$ok -and (-not $state['Idempotent'])
        Idempotent = $state['Idempotent']
        Output     = $state['Output']
        ExitCode   = $state['ExitCode']
    }
}