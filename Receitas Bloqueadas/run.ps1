<#
.SYNOPSIS
    Orquestrador PS-Nativo para Receitas Bloqueadas.
.DESCRIPTION
    Este script coordena o processamento de receitas retidas e sua distribuicao multicanal:
    1. Pre-Flight: Diagnostico de saude (Excel, WhatsApp Config, Espaco em Disco).
    2. Excel/VBA: Processa a logica de negocio e gera artefatos de saida (E-mail legado).
    3. WhatsApp Bridge: Dispara notificacoes via Node.js utilizando idempotencia.
.NOTES
    Version: 1.2.1
    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-execution-contract
    Contract: legacy-vba-logic, base64-bridge-logs, preflight-v1
#>
[CmdletBinding()]
param([string]$ExecId = "")

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$BasePath = $ScriptDir
$ExcelPath = Join-Path $BasePath "Receitas Bloqueadas.xlsm"
$LogDir = Join-Path $BasePath "Logs"
$MacroName = "ExecutarProcessoCompleto"
$MaxTimeoutSec = 300
$PollIntervalMs = 3000

# Bibliotecas e Caminhos
$projectRoot = Split-Path -Parent $ScriptDir
$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$SendWhatsAppScript = Join-Path $projectRoot "lib\Send-WhatsApp.ps1"
$WhatsAppConfig = Join-Path $BasePath "whatsapp-config.json"

Import-Module $libLogging -Force
Import-Module $libEmail   -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}
$LogFile = Get-AutomacaoLogPath -Slug "ReceitasBloqueadas" -LogDir $LogDir

# Helper para Log com suporte a Base64 Interno (Skill log-standardization)
function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    if ($Msg -match '[\u00C0-\u00FF]') {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Msg)
        $b64 = [System.Convert]::ToBase64String($bytes)
        Write-AutomacaoLog -Message "B64:$b64" -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    } else {
        Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    }
}

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    if ($Msg) { Write-Log $Msg -Lvl $(if ($Code -eq 0) { "INFO" } else { "ERRO" }) }
    Write-Log "FIM - Finalizado. ExitCode=$Code"
    Write-Log "========================================================================================="
    exit $Code
}

# --- BOOTSTRAP / PRE-FLIGHT ---
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths @($ExcelPath, $SendWhatsAppScript, $WhatsAppConfig)
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando execucao."
}

if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
    Invoke-LogRotation -LogPath $LogFile -KeepDays 15
}

Write-Log "========================================================================================="
Write-Log "INICIO - run.ps1 Receitas Bloqueadas (VBA + Node.js). ExecId=$ExecId"

$excel = $null
$wb = $null
$success = $false
$vbaLogFile = $LogFile

try {
    # 0. Limpeza de Excel (Removido para evitar fechar a instancia do usuario)
    # Get-Process excel -ErrorAction SilentlyContinue | Stop-Process -Force

    # 1. Abrir Excel COM
    Write-Log "Abrindo Excel COM..."
    $testEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", "User")
    if (-not [string]::IsNullOrWhiteSpace($testEmail)) {
        Write-Log "TRAVA DE SEGURANCA: Modo de teste detectado ($testEmail)." -Lvl "WARN"
    }

    try { $excel = New-Object -ComObject Excel.Application } catch [System.Exception] { Exit-WithCode 2 "Falha Excel COM." }
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false

    Write-Log "Abrindo workbook: $ExcelPath"
    try { $wb = $excel.Workbooks.Open($ExcelPath) } catch [System.Exception] { Exit-WithCode 3 "Falha ao abrir workbook." }
    if ($wb.ReadOnly) { Exit-WithCode 7 "Workbook em modo somente leitura." }

    if (-not (Test-Path $vbaLogFile)) {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
        New-Item -ItemType File -Path $vbaLogFile -Force | Out-Null
    }
    $initialLogSize = (Get-Item $vbaLogFile).Length
    Write-Log "Monitoramento VBA ativo. LogVBA=$vbaLogFile | Inicial=$initialLogSize bytes"

    # Executar macro com fallback
    $fullMacroName = "modReceitasBloqueadas.$MacroName"
    Write-Log "Executando macro VBA: $fullMacroName com ExecId=$ExecId"
    
    try {
        $excel.Run($fullMacroName, $ExecId) | Out-Null
        $successVba = $true
    } catch [System.Exception] {
        Write-Log "Falha na chamada da macro: $_" -Lvl "ERRO"
        $successVba = $false
    }

    if (-not $successVba) {
        Exit-WithCode 4 "Falha ao invocar macro VBA."
    }

    # Monitorar VBA log por conclusao
    Write-Log "Aguardando conclusao via log VBA (timeout: ${MaxTimeoutSec}s)..."

    $watchStart = Get-Date
    $previousSize = $initialLogSize
    $foundEnd = $false
    $successResult = $false

    while (-not $foundEnd) {
        $elapsed = (New-TimeSpan -Start $watchStart -End (Get-Date)).TotalSeconds
        if ($elapsed -ge $MaxTimeoutSec) {
            Exit-WithCode 5 "TIMEOUT: VBA nao registrou termino em ${MaxTimeoutSec}s"
        }

        Start-Sleep -Milliseconds $PollIntervalMs

        if (-not (Test-Path $vbaLogFile)) { continue }

        $currentSize = (Get-Item $vbaLogFile).Length
        if ($currentSize -lt $previousSize) {
            $initialLogSize = $currentSize; $previousSize = $currentSize; continue
        }

        if ($currentSize -gt $previousSize) {
            try { $allContent = Get-Content $vbaLogFile -Raw -Encoding UTF8 -ErrorAction Stop } catch [System.Exception] { continue }
            $newContent = if ($allContent.Length -gt $initialLogSize) { $allContent.Substring([int]$initialLogSize) } else { "" }

            if ($newContent -match "ERRO FATAL") {
                $successResult = $false; $foundEnd = $true
            } elseif ($newContent -match "FIM DO PROCESSO\.") {
                $successResult = ($newContent -match "Resultado=Sucesso")
                $foundEnd = $true
            }
            $previousSize = $currentSize
        }
    }

    if (-not $successResult) { Exit-WithCode 6 "VBA reportou falha ou erro fatal nos logs" }
    
    # BUFFER PARA OUTLOOK
    Write-Log "VBA finalizado com sucesso. Aguardando 5 segundos para flush do Outlook Outbox..."
    Start-Sleep -Seconds 5
    $success = $true

} finally {
    if ($wb) { try { $wb.Close($false) } catch [System.Exception] {} }
    if ($excel) { try { $excel.Quit() } catch [System.Exception] {} }
    [System.GC]::Collect()
}

if (-not $success) { Exit-WithCode 6 "Conclusao anormal do Excel/VBA." }

# 2. WhatsApp Post-Execution
Write-Log "Disparando Send-WhatsApp.ps1. ExecId=$ExecId Mode=AUTO"
try {
    $whatsAppProc = Start-Process "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -Mode AUTO" `
        -WindowStyle Hidden -Wait -PassThru -ErrorAction Stop

    $whatsAppExit = $whatsAppProc.ExitCode
    Write-Log "Send-WhatsApp.ps1 finalizado. ExitCode=$whatsAppExit"

    if ($whatsAppExit -eq 40) { Exit-WithCode 40 "WhatsApp ignorado por lock ativo." }
    elseif ($whatsAppExit -eq 23) { Exit-WithCode 23 "WhatsApp em cooldown." }
    elseif ($whatsAppExit -ne 0) { Write-Log "Send-WhatsApp.ps1 retornou ExitCode $whatsAppExit." -Lvl "WARN" }
} catch [System.Exception] {
    Write-Log "Falha ao iniciar processo WhatsApp: $_" -Lvl "WARN"
}

Exit-WithCode 0 "Processo concluido com sucesso."

