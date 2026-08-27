<#
.SYNOPSIS
    Biblioteca compartilhada de Retry com Backoff Exponencial (VALEG-Compliant).
.DESCRIPTION
    Fornece Invoke-WithRetry para encapsular qualquer operacao critica com:
    - Backoff configuravel por tentativa
    - Logging estruturado por tentativa (ExecId, Correlation)
    - Alerta de e-mail em falha definitiva
    - Suporte a ExitCodes que NAO disparam retry (ex: cooldown, lock)
.NOTES
    Version: 1.0.0
    Skill: protocolo-valeg, ai-native-development-standard
    VALEG: A-Arquitetura (Retry), L-Logging (por tentativa), G-Governanca (alerta definitivo)
#>

$ErrorActionPreference = "Stop"

function Invoke-WithRetry {
    <#
    .SYNOPSIS
        Executa um ScriptBlock com logica de retry e backoff exponencial.
    .PARAMETER Action
        Bloco de codigo a ser executado. Deve retornar $true em sucesso ou lancar excecao em falha.
    .PARAMETER MaxAttempts
        Numero maximo de tentativas. Default: 3.
    .PARAMETER BackoffSeconds
        Array com o tempo de espera (em segundos) entre cada tentativa.
        O indice corresponde ao numero da tentativa que FALHOU (base 0).
        Default: @(30, 60, 120)
    .PARAMETER OperationName
        Nome legivel da operacao para logging.
    .PARAMETER ExecId
        ID de execucao para rastreabilidade nos logs.
    .PARAMETER LogPath
        Caminho do arquivo de log para Write-AutomacaoLog.
    .OUTPUTS
        [bool] $true em sucesso, $false apos esgotar todas as tentativas.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action,

        [int]$MaxAttempts = 3,

        [int[]]$BackoffSeconds = @(30, 60, 120),

        [string]$OperationName = "Operacao",

        # Etapa do schema de log (docs/log-event.schema.json) para o evento
        # retry.attempt quando a automacao ja opera no padrao estruturado.
        [ValidateSet("preflight", "lock", "extract", "transform", "dispatch", "commit", "cleanup", "custom")]
        [string]$Step = "extract",

        [Parameter(Mandatory = $true)]
        [string]$ExecId,

        [Parameter(Mandatory = $true)]
        [string]$LogPath
    )

    $hubRetry = Get-Command Write-HubRetryAttempt -ErrorAction SilentlyContinue
    $hubCtx = if (Get-Command Get-HubLogContext -ErrorAction SilentlyContinue) { Get-HubLogContext } else { $null }
    $useHubRetry = ($null -ne $hubRetry) -and ($null -ne $hubCtx)

    function Write-RetryLog {
        # UTF-8 ponta a ponta: sem encoder Base64 (removido no padrao de logging,
        # ver docs/logging-standard.md). Write-AutomacaoLog ja roteia para o
        # evento estruturado quando ha contexto de LogEvent ativo.
        param([string]$Msg, [string]$Lvl = "INFO")
        Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogPath
    }

    function Write-RetryAttemptEvent {
        param([int]$AttemptNum, [string]$Lvl, [string]$Msg)
        if ($useHubRetry) {
            Write-HubRetryAttempt -Step $Step -Attempt $AttemptNum -MaxAttempts $MaxAttempts -Level $Lvl -Message $Msg
        }
    }

    $attempt = 0
    while ($attempt -lt $MaxAttempts) {
        $attempt++
        try {
            # A primeira tentativa nao gera evento proprio (o step.start/end do
            # run.ps1 ja a delimita); so retentativas e falhas viram retry.attempt.
            if ($attempt -gt 1) {
                if ($useHubRetry) {
                    Write-RetryAttemptEvent $attempt "WARN" "$OperationName - tentativa $attempt/$MaxAttempts"
                } else {
                    Write-RetryLog "[RETRY] $OperationName - Tentativa $attempt/$($MaxAttempts)" -Lvl "WARN"
                }
            }
            $result = & $Action
            if ($result -eq $false) { throw "Acao retornou false na tentativa $attempt." }
            if ($attempt -gt 1) {
                if ($useHubRetry) {
                    Write-RetryAttemptEvent $attempt "INFO" "$OperationName - sucesso apos $attempt tentativa(s)"
                } else {
                    Write-RetryLog "[RETRY] $OperationName - Sucesso na tentativa $attempt/$($MaxAttempts)"
                }
            } elseif (-not $useHubRetry) {
                Write-RetryLog "[RETRY] $OperationName - Sucesso na tentativa $attempt/$($MaxAttempts)"
            }
            return $true
        }
        catch [System.Exception] {
            $errMsg = $_.Exception.Message

            if ($attempt -ge $MaxAttempts) {
                if ($useHubRetry) {
                    Write-RetryAttemptEvent $attempt "ERRO" "$OperationName - todas as $MaxAttempts tentativas falharam. Ultimo erro: $errMsg"
                } else {
                    Write-RetryLog "[RETRY] $OperationName - Falha na tentativa $attempt/$($MaxAttempts): $errMsg" -Lvl "WARN"
                    Write-RetryLog "[RETRY_ESGOTADO] $OperationName - Todas as $MaxAttempts tentativas falharam. Ultimo erro: $errMsg" -Lvl "ERRO"
                }
                return $false
            }

            $waitIdx = [Math]::Min($attempt - 1, $BackoffSeconds.Count - 1)
            $waitSec = $BackoffSeconds[$waitIdx]
            if ($useHubRetry) {
                Write-RetryAttemptEvent $attempt "WARN" "$OperationName - falha na tentativa $attempt/$($MaxAttempts): $errMsg. Aguardando ${waitSec}s."
            } else {
                Write-RetryLog "[RETRY] $OperationName - Falha na tentativa $attempt/$($MaxAttempts): $errMsg" -Lvl "WARN"
                Write-RetryLog "[RETRY] Aguardando ${waitSec}s antes da proxima tentativa..." -Lvl "WARN"
            }
            Start-Sleep -Seconds $waitSec
        }
    }
    return $false
}

function Send-AlertaFalhaDefinitiva {
    <#
    .SYNOPSIS
        Envia e-mail de alerta quando uma automacao falha definitivamente apos esgotar retries.
    .PARAMETER TaskName
        Nome da automacao que falhou.
    .PARAMETER ExecId
        ID de execucao para rastreabilidade.
    .PARAMETER UltimoErro
        Mensagem do ultimo erro registrado.
    .PARAMETER Tentativas
        Numero de tentativas realizadas.
    .PARAMETER LogPath
        Caminho do log para inclusao no alerta.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$TaskName,

        [string]$ExecId = "N/A",
        [string]$UltimoErro = "Consulte o log para detalhes.",
        [int]$Tentativas = 0,
        [string]$LogPath = ""
    )

    $alertEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_ALERT_EMAIL", "Process")
    if ([string]::IsNullOrWhiteSpace($alertEmail)) {
        # Sem AUTOMACAO_ALERT_EMAIL no .env: suprime o alerta em vez de e-mail hardcoded.
        Write-Warning "[ALERT] AUTOMACAO_ALERT_EMAIL nao configurado; alerta suprimido."
        return
    }

    $agora = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
    $subject = "[FALHA CRITICA] Automacao '$TaskName' - $agora"

    $htmlBody = @"
<div style="font-family:'Segoe UI',Arial,sans-serif; font-size:11pt; color:#1f2937; padding:20px;">
    <table style="width:100%; max-width:700px; border-collapse:collapse; border:2px solid #dc2626;">
        <thead>
            <tr style="background-color:#dc2626;">
                <th style="padding:15px; color:#ffffff; text-align:left; font-size:13pt;">
                    &#x26A0; FALHA DEFINITIVA - Intervencao Necessaria
                </th>
            </tr>
        </thead>
        <tbody>
            <tr><td style="padding:20px; background-color:#fff5f5;">
                <p style="margin:0 0 15px 0; font-size:12pt; color:#dc2626; font-weight:bold;">
                    A automacao <b>$TaskName</b> falhou definitivamente apos <b>$Tentativas tentativas</b>.
                </p>
                <table style="width:100%; border-collapse:collapse; font-size:10.5pt;">
                    <tr style="background:#f9fafb; border-bottom:1px solid #e5e7eb;">
                        <td style="padding:8px; font-weight:bold; width:30%;">Automacao:</td>
                        <td style="padding:8px;">$TaskName</td>
                    </tr>
                    <tr style="background:#ffffff; border-bottom:1px solid #e5e7eb;">
                        <td style="padding:8px; font-weight:bold;">ExecId:</td>
                        <td style="padding:8px; font-family:monospace;">$ExecId</td>
                    </tr>
                    <tr style="background:#f9fafb; border-bottom:1px solid #e5e7eb;">
                        <td style="padding:8px; font-weight:bold;">Ocorrencia:</td>
                        <td style="padding:8px;">$agora</td>
                    </tr>
                    <tr style="background:#ffffff; border-bottom:1px solid #e5e7eb;">
                        <td style="padding:8px; font-weight:bold;">Tentativas Realizadas:</td>
                        <td style="padding:8px; color:#dc2626; font-weight:bold;">$Tentativas de $Tentativas (esgotadas)</td>
                    </tr>
                    <tr style="background:#fef2f2;">
                        <td style="padding:8px; font-weight:bold; vertical-align:top;">Ultimo Erro:</td>
                        <td style="padding:8px; font-family:monospace; font-size:9pt; color:#7f1d1d;">$UltimoErro</td>
                    </tr>
                </table>
                <p style="margin:20px 0 5px 0; color:#374151;">
                    Por favor, verifique o log em: <code style="background:#f3f4f6; padding:2px 5px; border-radius:3px;">$LogPath</code>
                </p>
                <p style="margin:0; font-size:9pt; color:#9ca3af;">Mensagem automatica do sistema de monitoramento de automacoes.</p>
            </td></tr>
        </tbody>
    </table>
</div>
"@

    try {
        if (Get-Command Send-OutlookEmail -ErrorAction SilentlyContinue) {
            $sent = Send-OutlookEmail -To $alertEmail -Subject $subject -HtmlBody $htmlBody -ExecId $ExecId -LogPath $LogPath
            if (-not $sent) { Write-Warning "[ALERT] Falha ao enviar e-mail de alerta para $alertEmail" }
        } else {
            Write-Warning "[ALERT] Send-OutlookEmail nao disponivel. Alerta para $alertEmail nao enviado."
        }
    }
    catch [System.Exception] {
        Write-Warning "[ALERT] Excecao ao enviar alerta: $_"
    }
}

Export-ModuleMember -Function Invoke-WithRetry, Send-AlertaFalhaDefinitiva

