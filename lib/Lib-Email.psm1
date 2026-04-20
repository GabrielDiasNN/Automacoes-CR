# ==============================================================================
# ARQUIVO: Lib-Email.psm1
# VERSÃƒO: 1.0
# DESCRIÃ‡ÃƒO: Biblioteca de envio de e-mail via Outlook COM para scripts PS.
#            Wrapper fino sobre o objeto Outlook.Application â€” projetado para
#            notificaÃ§Ãµes originadas em scripts PowerShell (nÃ£o-VBA).
# DEPENDÃŠNCIA: Lib-Logging.psm1 (deve ser importado antes no script chamador)
# ==============================================================================

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------------------
# Send-OutlookEmail
# Cria e envia um e-mail HTML via Outlook COM (MAPI).
# Requer Outlook instalado e configurado com perfil ativo.
#
# ParÃ¢metros obrigatÃ³rios:
#   -To       EndereÃ§o(s) destinatÃ¡rio(s); use ";" para mÃºltiplos
#   -Subject  Assunto do e-mail
#   -HtmlBody Corpo HTML completo
#
# ParÃ¢metros opcionais:
#   -CC       EndereÃ§o(s) CC
#   -BCC      EndereÃ§o(s) CCO
#   -ExecId   ID de execuÃ§Ã£o para rastreio nos logs
#   -LogPath  Caminho do arquivo de log (usa Write-AutomacaoLog se disponÃ­vel)
#
# Retorno: $true se enviado; $false se falhou (erro gravado em LogPath/console)
# ------------------------------------------------------------------------------
function Send-OutlookEmail {
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$To,

        [Parameter(Mandatory = $true)]
        [string]$Subject,

        [Parameter(Mandatory = $true)]
        [string]$HtmlBody,

        [string]$CC = "",
        [string]$BCC = "",
        [string]$ExecId = "",
        [string]$LogPath = ""
    )

    $logCtx = if ([string]::IsNullOrWhiteSpace($ExecId)) { "" } else { " [ExecId=$ExecId]" }

    function Write-Log {
        param([string]$Msg, [string]$Lvl = "INFO")
        if (-not [string]::IsNullOrWhiteSpace($LogPath)) {
            # Write-AutomacaoLog disponÃ­vel se o chamador importou Lib-Logging
            if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
                Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogPath
                return
            }
        }
        Write-Host "[$Lvl]$logCtx $Msg"
    }

    $outlook = $null
    $mailItem = $null

    try {
        if ($PSCmdlet.ShouldProcess($To, "Enviar e-mail: $Subject")) {
            $outlook = New-Object -ComObject Outlook.Application

            # Verificar sessÃ£o MAPI ativa
            try {
                $ns = $outlook.GetNamespace("MAPI")
                $ns.Logon($null, $null, $false, $false) | Out-Null
            }
            catch {
                # SessÃ£o pode jÃ¡ estar ativa â€” falha aqui nÃ£o Ã© fatal
            }

            $mailItem = $outlook.CreateItem(0) # olMailItem = 0

            $mailItem.To = $To
            $mailItem.Subject = $Subject
            $mailItem.HTMLBody = $HtmlBody

            if (-not [string]::IsNullOrWhiteSpace($CC)) { $mailItem.CC = $CC }
            if (-not [string]::IsNullOrWhiteSpace($BCC)) { $mailItem.BCC = $BCC }

            $mailItem.Send()

            Write-Log "E-mail enviado com sucesso. Para=$To | Assunto=$Subject"
            return $true
        }
        else {
            Write-Log "Envio de e-mail suprimido por WhatIf. Para=$To | Assunto=$Subject" -Lvl "WARN"
            return $false
        }
    }
    catch {
        Write-Log "Falha ao enviar e-mail. Para=$To | Assunto=$Subject | Erro=$_" -Lvl "ERRO"
        return $false
    }
    finally {
        if ($mailItem) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mailItem) | Out-Null } catch { } } # Ignorado
        if ($outlook) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($outlook)  | Out-Null } catch { } } # Ignorado
    }
}

Export-ModuleMember -Function Send-OutlookEmail
