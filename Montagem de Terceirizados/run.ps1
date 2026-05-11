<#
.SYNOPSIS
    Orquestrador Ofical para Montagem de Terceirizados (Pure-Native).
.DESCRIPTION
    Este script coordena o ciclo de vida da automacao utilizando extracao direta do Oracle via Python.
    Nao utiliza mais dependencias de Excel/VBA (Migracao Concluida).
.NOTES
    Version: 2.0.0
    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-runtime-safety
    Contract: native-fetch-logic, ipc-file-payload, base64-bridge-logs, preflight-v1
    #>
    # {
    #   "name": "orchestrator-montagem-terceirizados",
    #   "version": "2.0.0",
    #   "skill": "powershell-automation-monitor",
    #   "description": "Use when orchestrating fiscal validation of outsourcing assembly orders."
    # }
    [CmdletBinding()]
param(
    [string]$ExecId = "",
    [switch]$EmailPreviewOnly,
    [string]$EmailToTest = "",
    [string]$EmailCcTest = ""
)

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding para Interoperabilidade
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

# Bibliotecas e Caminhos
$projectRoot = Split-Path -Parent $ScriptDir
$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

# Scripts
$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$validatePy = Join-Path $ScriptDir "validate_and_generate_html.py"
$LogDir     = Join-Path $ScriptDir "Logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

Import-Module $libLogging -Force
Import-Module $libEmail   -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}
$LogFile = Get-AutomacaoLogPath -Slug "Montagem_Terceirizados" -LogDir $LogDir

# Helper para Log com suporte a Base64 Interno (v5.0.0)
function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    if ($Msg -match '[^\x00-\x7F]') {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Msg)
        $b64 = [System.Convert]::ToBase64String($bytes)
        Write-AutomacaoLog -Message "B64:$b64" -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    } else {
        Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    }
}

# --- BOOTSTRAP / PRE-FLIGHT ---
$pathsToCheck = @($pythonExe, $extractPy, $validatePy)

# Housekeeping: Limpa arquivos temporarios orfaos com mais de 24h
Get-ChildItem -Path $ScriptDir -Filter ".data_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $ScriptDir -Filter ".payload_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue

if (-not (Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths $pathsToCheck)) {
    Write-Log "FALHA NO PRE-FLIGHT (Python/Oracle/Paths). Abortando execucao." -Lvl "ERRO"; exit 9
}

Write-Log "========================================================================================="
Write-Log "INICIO - Execucao Montagem Terceirizados (Pure-Native). ExecId=$ExecId"

try {
    # Carregar Variaveis de Ambiente (.env)
    $envPath = Join-Path $projectRoot ".env"
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $key, $value = $line -split '=', 2
                if ($key -and $value) { [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process") }
            }
        }
    }

    $dataFile = Join-Path $ScriptDir ".data_$ExecId.json"
    if (Test-Path $dataFile) { Remove-Item $dataFile -Force }

    # 1. Extracao Nativa (Pure-Python via Oracle)
    Write-Log "Fase 1: Executando extracao nativa direta do Oracle..."
    $nativeExtractInfo = New-Object System.Diagnostics.ProcessStartInfo
    $nativeExtractInfo.FileName = $pythonExe
    $nativeExtractInfo.Arguments = "`"$extractPy`" `"$ExecId`""
    $nativeExtractInfo.RedirectStandardOutput = $true 
    $nativeExtractInfo.RedirectStandardError = $true
    $nativeExtractInfo.UseShellExecute = $false
    $nativeExtractInfo.CreateNoWindow = $true
    $nativeExtractInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    
    # Injetar variaveis do .env no processo filho
    $envVars = [System.Environment]::GetEnvironmentVariables("Process")
    foreach ($key in $envVars.Keys) {
        if (-not $nativeExtractInfo.Environment.ContainsKey($key)) {
            $nativeExtractInfo.Environment.Add($key, $envVars[$key])
        }
    }
    
    $nativeProc = [System.Diagnostics.Process]::Start($nativeExtractInfo)
    
    # Processa logs do Python em tempo real
    while (-not $nativeProc.HasExited) {
        $line = $nativeProc.StandardOutput.ReadLine()
        if ($line) { Write-Log $line }
        $err = $nativeProc.StandardError.ReadLine()
        if ($err) { Write-Log $err -Lvl "WARN" }
    }
    $nativeProc.WaitForExit()

    if ($nativeProc.ExitCode -ne 0 -or -not (Test-Path $dataFile)) {
        throw "Falha critica na extracao nativa (ExitCode: $($nativeProc.ExitCode))."
    }

    # 2. Validacao e HTML
    Write-Log "Fase 2: Validando dados e gerando notificacao..."
    $payloadFile = Join-Path $ScriptDir ".payload_$ExecId.json"
    if (Test-Path $payloadFile) { Remove-Item $payloadFile -Force }

    $genInfo = New-Object System.Diagnostics.ProcessStartInfo
    $genInfo.FileName = $pythonExe
    $genInfo.Arguments = "`"$validatePy`" `"$ExecId`""
    $genInfo.RedirectStandardOutput = $true
    $genInfo.RedirectStandardError = $true
    $genInfo.UseShellExecute = $false
    $genInfo.CreateNoWindow = $true
    
    $genProcess = [System.Diagnostics.Process]::Start($genInfo)
    while (-not $genProcess.HasExited) {
        $line = $genProcess.StandardOutput.ReadLine()
        if ($line) { Write-Log $line }
        $err = $genProcess.StandardError.ReadLine()
        if ($err) { Write-Log $err -Lvl "WARN" }
    }
    $genProcess.WaitForExit()
    
    if ($genProcess.ExitCode -ne 0) { throw "Falha na validacao Python (ExitCode: $($genProcess.ExitCode))." }

    # 3. Envio do E-mail (Se houver payload)
    if (Test-Path $payloadFile) {
        $jsonOutput = Get-Content $payloadFile -Raw -Encoding UTF8
        $payload = $jsonOutput | ConvertFrom-Json
        $bytes = [System.Convert]::FromBase64String($payload.subject_b64)
        $subject = [System.Text.Encoding]::UTF8.GetString($bytes)
        $htmlOutput = $payload.html

        Write-Log "Notificacao gerada: $subject"
        
        $globalTestEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", "User")
        $finalTo = $EmailToTest
        if ([string]::IsNullOrWhiteSpace($finalTo)) { $finalTo = $globalTestEmail }
        
        if ($EmailPreviewOnly -or -not [string]::IsNullOrWhiteSpace($finalTo)) {
            Write-Log "Enviando e-mail de teste para: $finalTo"
            Send-OutlookEmail -To $finalTo -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile -PreviewOnly:([bool]$EmailPreviewOnly)
        } else {
            Write-Log "Disparando e-mail oficial..."
            Send-OutlookEmail -To "gabriel.dias@costaricamalhas.ind.br" -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile
        }
        Remove-Item $payloadFile -Force
        if (Test-Path $dataFile) { Remove-Item $dataFile -Force }
    } else {
        Write-Log "Nenhuma divergencia ou mudanca de estado. Nenhuma notificacao enviada."
    }

} catch [System.Exception] {
    Write-Log "ERRO FATAL NA EXECUCAO NATIVA: $_" -Lvl "ERRO"; exit 1
} finally {
    # Limpeza rigorosa de arquivos temporarios de intercambio
    if ($ExecId) {
        $tempPatterns = ".data_$ExecId.json", ".payload_$ExecId.json"
        foreach ($p in $tempPatterns) {
            $f = Join-Path $ScriptDir $p
            if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
        }
    }
    Write-Log "FIM - Processo finalizado."
}

