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
# Helpers Internos
# ------------------------------------------------------------------------------
function Wait-OutlookEditorReady {
    param(
        [Parameter(Mandatory = $true)]
        [object]$MailItem,

        [int]$MaxAttempts = 20,
        [int]$DelayMilliseconds = 250
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            $inspector = $MailItem.GetInspector()
            $htmlBody = $MailItem.HTMLBody
            if ($inspector -and -not [string]::IsNullOrWhiteSpace($htmlBody)) {
                return $true
            }
        } catch [System.Exception] {
            # Aguarda a materializacao do editor do Outlook.
        }

        Start-Sleep -Milliseconds $DelayMilliseconds
    }

    return $false
}

function Get-InlineAttachmentCount {
    param(
        [Parameter(Mandatory = $true)]
        [object]$MailItem
    )

    $contentIdTag = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
    $hiddenTag = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
    $inlineCount = 0

    try {
        for ($index = 1; $index -le $MailItem.Attachments.Count; $index++) {
            $attachment = $null
            try {
                $attachment = $MailItem.Attachments.Item($index)
                $propertyAccessor = $attachment.PropertyAccessor
                $contentId = $propertyAccessor.GetProperty($contentIdTag)
                $isHidden = $propertyAccessor.GetProperty($hiddenTag)
                if (-not [string]::IsNullOrWhiteSpace($contentId) -or $isHidden) {
                    $inlineCount++
                }
            } catch [System.Exception] {
                # Nem todo anexo expone as propriedades MAPI esperadas; ignorar.
            } finally {
                if ($attachment) {
                    try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($attachment) | Out-Null } catch [System.Exception] { }
                }
            }
        }
    } catch [System.Exception] {
        return 0
    }

    return $inlineCount
}

function Get-OutlookDraftReloaded {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Outlook,

        [Parameter(Mandatory = $true)]
        [object]$MailItem
    )

    $entryId = $MailItem.EntryID
    if ([string]::IsNullOrWhiteSpace($entryId)) {
        return $null
    }

    $storeId = $null
    try {
        if ($MailItem.Parent) {
            $storeId = $MailItem.Parent.StoreID
        }
    } catch [System.Exception] {
        $storeId = $null
    }

    try {
        $MailItem.Close(0)
    } catch [System.Exception] {
        # Se nao for possivel fechar o draft, tentaremos reabrir assim mesmo.
    }

    try {
        if ([string]::IsNullOrWhiteSpace($storeId)) {
            return $Outlook.Session.GetItemFromID($entryId)
        }

        return $Outlook.Session.GetItemFromID($entryId, $storeId)
    } catch [System.Exception] {
        return $null
    }
}

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
        [string]$LogPath = "",
        [switch]$PreviewOnly
    )

    function Write-LocalLog {
        param([string]$m, [string]$l = "INFO")
        if ([string]::IsNullOrWhiteSpace($LogPath)) { return }

        if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
            Write-AutomacaoLog -Message $m -Level $l -ExecId $ExecId -LogPath $LogPath
        } else {
            Write-Host "[$l] [ExecId:$ExecId] $m"
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
                Write-LocalLog "Outlook ja estava aberto no perfil do usuario."
            } catch [System.Exception] {
                # Se nao estiver aberto, nos iniciamos o background COM
                $outlook = New-Object -ComObject Outlook.Application
                $weStartedOutlook = $true
                Write-LocalLog "Outlook iniciado via COM para este envio."
            }

            $mailItem = $outlook.CreateItem(0)

            # Redirecionamento de Teste
            $testEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", "User")
            $finalTo = $To
            $finalCc = $CC
            $finalBcc = $BCC
            $finalSubject = $Subject

            $isTestMode = $false
            if ($env:ORCHESTRATOR_TEST_MODE -eq "true") {
                $isTestMode = $true
            } elseif ($env:ORCHESTRATOR_TEST_MODE -eq "false") {
                $isTestMode = $false
            } else {
                # Fallback para execucao manual via VS Code
                if (-not [string]::IsNullOrWhiteSpace($testEmail)) {
                    $isTestMode = $true
                }
            }

            if ($isTestMode) {
                # Garante um destino fallback se a variavel global foi limpa mas o db manda testar
                $finalTestEmail = if (-not [string]::IsNullOrWhiteSpace($testEmail)) { $testEmail } else { "gabriel.dias@costaricamalhas.ind.br" }
                Write-LocalLog "MODO TESTE ATIVO: Redirecionando e-mail de $To para $finalTestEmail" -l "WARN"
                $finalTo = $finalTestEmail
                $finalCc = ""
                $finalBcc = ""
                $finalSubject = "[TESTE] $Subject"
            }

            # Preserva assinatura (Display carrega o HTML original com CIDs)
            $mailItem.BodyFormat = 2
            $mailItem.Display()
            if (-not (Wait-OutlookEditorReady -MailItem $mailItem)) {
                Write-LocalLog "Editor do Outlook nao confirmou prontidao completa no tempo esperado; prosseguindo com a melhor evidencia disponivel." -l "WARN"
            }

            $mailItem.Save()
            $signatureHtml = $mailItem.HTMLBody
            $inlineAttachmentsBeforeMerge = Get-InlineAttachmentCount -MailItem $mailItem
            Write-LocalLog "Assinatura carregada. InlineAttachments=$inlineAttachmentsBeforeMerge HtmlLength=$($signatureHtml.Length)"

            $mailItem.To = $finalTo
            $mailItem.Subject = $finalSubject
            $mailItem.HTMLBody = $HtmlBody + $signatureHtml

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

            $mailItem.Save()
            $inlineAttachmentsAfterMerge = Get-InlineAttachmentCount -MailItem $mailItem
            Write-LocalLog "Mensagem persistida antes do envio. InlineAttachments=$inlineAttachmentsAfterMerge"

            $signatureHasInlineReferences = $signatureHtml -match '(_arquivos/image\d+\.(png|jpg|gif))|(cid:)'
            if ($signatureHasInlineReferences -and $inlineAttachmentsAfterMerge -le 0) {
                Write-LocalLog "Nenhum anexo inline detectado apos merge do HTML. Executando recarga controlada do draft antes do envio." -l "WARN"
                $reloadedMailItem = Get-OutlookDraftReloaded -Outlook $outlook -MailItem $mailItem
                if ($reloadedMailItem) {
                    try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mailItem) | Out-Null } catch [System.Exception] { }
                    $mailItem = $reloadedMailItem
                    $mailItem.Display()
                    if (-not (Wait-OutlookEditorReady -MailItem $mailItem -MaxAttempts 12 -DelayMilliseconds 250)) {
                        Write-LocalLog "Draft recarregado sem confirmacao completa do editor no tempo esperado." -l "WARN"
                    }
                    $mailItem.Save()
                    $inlineAttachmentsAfterReload = Get-InlineAttachmentCount -MailItem $mailItem
                    Write-LocalLog "Draft recarregado com sucesso. InlineAttachments=$inlineAttachmentsAfterReload"
                } else {
                    Write-LocalLog "Falha ao recarregar o draft para revalidar anexos inline. Mantendo envio com a mensagem atual." -l "WARN"
                }
            }

            Start-Sleep -Milliseconds 350
            Write-LocalLog "Mensagem estabilizada e pronta para envio."

            if ($PreviewOnly) {
                Write-LocalLog "Modo PREVIEW ativo. E-mail exibido mas NAO enviado automaticamente." -l "WARN"
                return $true
            }

            Write-LocalLog "Disparando envio Outlook COM."
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
            try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($mailItem) | Out-Null } catch [System.Exception] { Write-Verbose ("Falha ao liberar mailItem COM: {0}" -f $_.Exception.Message) }
        }

        if ($outlook) {
            # Apenas libera o objeto da memoria do script, NUNCA executa .Quit() para nao matar o Outlook do usuario
            # ou impedir o envio de e-mails que estao na Outbox.
            try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($outlook) | Out-Null } catch [System.Exception] { Write-Verbose ("Falha ao liberar Outlook COM: {0}" -f $_.Exception.Message) }
        }

        # Garante a morte do ponteiro RPC no Windows, mas mantem a aplicacao Outlook.exe viva
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
    }
}

Export-ModuleMember -Function Send-OutlookEmail

