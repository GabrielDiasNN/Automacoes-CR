<#
.SYNOPSIS
    Script de Teste para o Hub de Automacoes.
.DESCRIPTION
    Valida a importacao de bibliotecas, geracao de logs estruturados e telemetria.
#>
[CmdletBinding()]
param(
    [string]$ExecId = ""
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$projectRoot = Split-Path -Parent $ScriptDir
$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"

Import-Module $libLogging -Force

# Registra Telemetria se nao receber ExecId
if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = Register-ExecutionTelemetry -AutomationName "Test Task"
} else {
    $global:CurrentAutomationName = "Test Task"
}

$logPath = Get-AutomacaoLogPath -Slug "Test_Task"

Write-AutomacaoLog -Message "Iniciando a execucao de teste." -Level "INFO" -ExecId $ExecId -LogPath $logPath
Write-AutomacaoLog -Message "Validando operacao e geracao de log JSONL." -Level "INFO" -ExecId $ExecId -LogPath $logPath
Write-AutomacaoLog -Message "Operacao finalizada com sucesso." -Level "INFO" -ExecId $ExecId -LogPath $logPath

if ($ExecId -and $ExecId -notmatch '^MANUAL_') {
    Close-ExecutionTelemetry -ExecId $ExecId -Status "SUCCESS"
}
