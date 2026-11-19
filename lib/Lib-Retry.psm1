# ==============================================================================
# ARQUIVO: Lib-Retry.psm1
# DESCRICAO: Envio de alerta de falha definitiva via Outlook COM.
# ==============================================================================

$ErrorActionPreference = "Stop"

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

Export-ModuleMember -Function Send-AlertaFalhaDefinitiva