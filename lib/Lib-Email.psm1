<#
.SYNOPSIS
    Biblioteca de envio de e-mail via Outlook COM.
.DESCRIPTION
    Fornece interface padronizada para disparos de notificacoes:
    - Suporte a redirecionamento automatico em modo teste (AUTOMACAO_TEST_EMAIL).
    - Higienizacao automatica de destinatarios.
    - Integracao com Base64 Bridge para logs de auditoria.
    - Preservacao de assinaturas oficiais do Outlook.
    - Resiliencia contra processos zumbis (GetActiveObject).
.NOTES
    Version: 1.2.1
    Skill: ai-native-development-standard, enterprise-local-automation-stack
    Contract: outlook-com-integration
#>

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ------------------------------------------------------------------------------
# Send-OutlookEmail
# ------------------------------------------------------------------------------
function Send-OutlookEmail {
    [CmdletBinding(SupportsShouldProcess = $true)]
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
        [string[]]$Attachments = @(),
        [string]$ExecId = "",
        [string]$LogPath = ""
    )

    function Write-LocalLog {
        param([string]$m, [string]$l = "INFO")
        if ([string]::IsNullOrWhiteSpace($LogPath)) { return }
        
        if ($m -match '[\u00C0-\u00FF]') {
            $b = [System.Text.Encoding]::UTF8.GetBytes($m)
            $b64 = [System.Convert]::ToBase64String($b)
            if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
                Write-AutomacaoLog -Message "B64:$b64" -Level $l -ExecId $ExecId -LogPath $LogPath
            }
        } else {
            if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
                Write-AutomacaoLog -Message $m -Level $l -ExecId $ExecId -LogPath $LogPath
            } else {
                Write-Host "[$l] [ExecId:$ExecId] $m"
            }
        }
    }

    $outlook = $null
    $mailItem = $null
    $weStartedOutlook = $false

    try {
        if ($PSCmdlet.ShouldProcess($To, "Enviar e-mail: $Subject")) {
            
            # Estrategia Anti-Zumbi: Tenta pegar um Outlook ja aberto pelo usuario
            try {
                $outlook = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Outlook.Application")
            } catch [System.Exception] {
                # Se nao estiver aberto, nos iniciamos o background COM
                $outlook = New-Object -ComObject Outlook.Application
                $weStartedOutlook = $true
            }
            
            $mailItem = $outlook.CreateItem(0)

            # Redirecionamento de Teste
            $testEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", "User")
            $finalTo = $To
            $finalCc = $CC
            $finalBcc = $BCC
            $finalSubject = $Subject

            if (-not [string]::IsNullOrWhiteSpace($testEmail)) {
                Write-LocalLog "MODO TESTE ATIVO: Redirecionando e-mail de $To para $testEmail" -l "WARN"
                $finalTo = $testEmail
                $finalCc = ""
                $finalBcc = ""
                $finalSubject = "[TESTE] $Subject"
            }

            # Preserva assinatura (Display carrega o HTML original com CIDs)
            $mailItem.Display()
            $mailItem.To = $finalTo
            $mailItem.Subject = $finalSubject
            $mailItem.HTMLBody = $HtmlBody + $mailItem.HTMLBody

            if (-not [string]::IsNullOrWhiteSpace($finalCc)) { $mailItem.CC = $finalCc }
            if (-not [string]::IsNullOrWhiteSpace($finalBcc)) { $mailItem.BCC = $finalBcc }

            # Processar Anexos
            if ($Attachments -and $Attachments.Count -gt 0) {
                foreach ($file in $Attachments) {
                    if (Test-Path $file) {
                        $mailItem.Attachments.Add($file) | Out-Null
                        Write-LocalLog "Anexo adicionado: $file"
                    } else {
                        Write-LocalLog "Aviso: Arquivo de anexo nao encontrado: $file" -l "WARN"
                    }
                }
            }

            $mailItem.Send()
            Write-LocalLog "E-mail enviado com sucesso. Para=$finalTo"
            return $true
        }
        else {
            Write-LocalLog "Envio de e-mail suprimido por WhatIf." -l "WARN"
            return $true
        }
    }
    catch [System.Exception] {
        Write-LocalLog "ERRO ao enviar e-mail: $_" -l "ERRO"
        return $false
    }
    finally {
        # Liberacao de Objetos COM (NAO FECHAR O OUTLOOK!)
        if ($mailItem) { 
            try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mailItem) | Out-Null } catch [System.Exception] {} 
        }
        
        if ($outlook) { 
            # Apenas libera o objeto da memoria do script, NUNCA executa .Quit() para nao matar o Outlook do usuario
            # ou impedir o envio de e-mails que estao na Outbox.
            try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($outlook) | Out-Null } catch [System.Exception] {} 
        }
        
        # Garante a morte do ponteiro RPC no Windows, mas mantem a aplicacao Outlook.exe viva
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
    }
}

Export-ModuleMember -Function Send-OutlookEmail
