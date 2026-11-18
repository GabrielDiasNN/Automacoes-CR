<#
.SYNOPSIS
    CLI fina sobre Lib-Email.psm1 e Lib-Retry.psm1, chamada pelo runner Python.
.DESCRIPTION
    O runner Python (lib/python/hub_runner.py) nao fala com o Outlook COM. Ele
    chama este script com powershell.exe -NoProfile -ExecutionPolicy Bypass -File,
    que reaproveita as mesmas funcoes dos run.ps1: Send-OutlookEmail e
    Send-AlertaFalhaDefinitiva.

    Modo e-mail: -To, -Subject e -HtmlBodyFile (arquivo UTF-8 com o corpo HTML).
    Opcionais: -Cc, -Bcc, -Attachments (caminhos separados por ";", porque -File nao
    recebe array) e -PreviewOnly (abre o rascunho sem enviar), repassados a Send-OutlookEmail.
    Modo alerta: -Alerta, com -TaskName, -UltimoErro e -Tentativas.

    Exit code: 0 quando o envio e confirmado (modo e-mail) ou a chamada de alerta
    termina sem excecao; 1 quando faltam parametros, o envio retorna false ou ha
    excecao. O alerta nao confirma envio: Send-AlertaFalhaDefinitiva nao devolve
    valor, entao so falhas de execucao aparecem como exit 1.
.NOTES
    Version: 1.1.0
    Skill: powershell-automation-monitor, enterprise-orchestration-contract
    Runtime: Windows PowerShell 5.1 (powershell.exe).
#>

[CmdletBinding()]
param(
    [string]$To = "",
    [string]$Subject = "",
    [string]$HtmlBodyFile = "",
    [string]$Cc = "",
    [string]$Bcc = "",
    [string]$Attachments = "",
    [switch]$PreviewOnly,
    [switch]$Alerta,
    [string]$TaskName = "",
    [string]$UltimoErro = "Consulte o log para detalhes.",
    [int]$Tentativas = 0,
    [string]$ExecId = "N/A",
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding (mesma das bibliotecas)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$libDir = $PSScriptRoot
# -Global: Lib-Retry procura Send-OutlookEmail no escopo global ao disparar o alerta.
Import-Module (Join-Path $libDir "Lib-Config.psm1") -Force -Global
Import-Module (Join-Path $libDir "Lib-Email.psm1") -Force -Global
Import-Module (Join-Path $libDir "Lib-Retry.psm1") -Force -Global

try {
    # Carrega o .env da raiz (AUTOMACAO_ALERT_EMAIL, ORCHESTRATOR_TEST_MODE etc.).
    Import-HubEnv

    if ($Alerta) {
        if ([string]::IsNullOrWhiteSpace($TaskName)) {
            Write-Host "[ERRO] -TaskName e obrigatorio no modo -Alerta."
            exit 1
        }
        Send-AlertaFalhaDefinitiva -TaskName $TaskName -ExecId $ExecId -UltimoErro $UltimoErro -Tentativas $Tentativas -LogPath $LogPath
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($To) -or [string]::IsNullOrWhiteSpace($Subject) -or [string]::IsNullOrWhiteSpace($HtmlBodyFile)) {
        Write-Host "[ERRO] Modo e-mail exige -To, -Subject e -HtmlBodyFile."
        exit 1
    }
    if (-not (Test-Path -LiteralPath $HtmlBodyFile -PathType Leaf)) {
        Write-Host "[ERRO] Arquivo do corpo nao encontrado: $HtmlBodyFile"
        exit 1
    }

    $htmlBody = Get-Content -LiteralPath $HtmlBodyFile -Raw -Encoding UTF8
    $anexos = @($Attachments -split ";" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    foreach ($anexo in $anexos) {
        if (-not (Test-Path -LiteralPath $anexo -PathType Leaf)) {
            Write-Host "[ERRO] Anexo nao encontrado: $anexo"
            exit 1
        }
    }
    $saidaEnvio = @(Send-OutlookEmail -To $To -CC $Cc -BCC $Bcc -Subject $Subject -HtmlBody $htmlBody -Attachments $anexos -ExecId $ExecId -LogPath $LogPath -PreviewOnly:$PreviewOnly)
    $resultadoEnvio = $saidaEnvio[-1]
    if ($resultadoEnvio -eq $true) { exit 0 }
    exit 1
}
catch [System.Exception] {
    Write-Host "[ERRO] Falha na CLI de e-mail: $($_.Exception.Message)"
    exit 1
}
