<#
.SYNOPSIS
    Orquestrador Nativo para Receitas Emitidas.
.DESCRIPTION
    Este script coordena a geracao do relatorio semanal de receitas emitidas (nao pesadas):
    1. Pre-Flight: Diagnostico de saude do ambiente (inclui validacao do Oracle Client local).
    2. Python (Extract): Busca dados no Oracle utilizando Query CTE Nativa.
    3. Python (HTML): Transforma JSON em relatorio adaptativo multipandonal.
    4. PowerShell: Entrega visual via Outlook utilizando Base64 Bridge para logs.
    Cada etapa critica e executada com Invoke-WithRetry (VALEG: A-Arquitetura).
.NOTES
    Version: 2.6.1
    Skill: ai-native-development-standard, python-oracle-migration, protocolo-valeg
    Contract: ipc-stdio, base64-bridge-logs, retry-on-failure
#>
# {
#   "name": "orchestrator-receitas-emitidas",
#   "version": "2.6.1",
#   "skill": "powershell-automation-monitor",
#   "description": "Use when orchestrating the weekly report of emitted recipes using IPC pipes."
# }
[CmdletBinding()]
param([string]$ExecId = "")

$ErrorActionPreference = "Stop"

# Configuracao Global de Encoding
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$projectRoot = Split-Path -Parent $ScriptDir
$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$libRetry    = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$envPath     = Join-Path $projectRoot ".env"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$generatePy = Join-Path $ScriptDir "generate_html_report.py"
$configPath = Join-Path $ScriptDir "receitas_config.json"
$LogDir     = Join-Path $ScriptDir "Logs"

Import-Module $libLogging -Force
Import-Module $libEmail   -Force
Import-Module $libRetry   -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}
$LogFile = Get-AutomacaoLogPath -Slug "ReceitasEmitidas" -LogDir $LogDir

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    if ($Msg -match '[\u00C0-\u00FF]') {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Msg); $b64 = [System.Convert]::ToBase64String($bytes)
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

# --- BOOTSTRAP / PRE-FLIGHT (inclui validacao do Oracle Client local) ---
# Carregar .env antes do Pre-Flight para que ORACLE_CLIENT_LIB_DIR esteja disponivel
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $key, $value = $line -split '=', 2
            if ($key -and $value) { [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process") }
        }
    }
}

# Validacao do Oracle Client local (causa do DPY-3015/Thin Mode involuntario)
$oracleClientLib = [System.Environment]::GetEnvironmentVariable("ORACLE_CLIENT_LIB_DIR", "Process")
$oraClientPreFlightOk = $true
if ([string]::IsNullOrWhiteSpace($oracleClientLib)) {
    Write-Log "PRE-FLIGHT WARN: ORACLE_CLIENT_LIB_DIR nao definido. Thick Mode pode falhar." -Lvl "WARN"
    $oraClientPreFlightOk = $false
} elseif (-not (Test-Path $oracleClientLib)) {
    Write-Log "PRE-FLIGHT WARN: Oracle Client nao encontrado em '$oracleClientLib'. Thick Mode indisponivel." -Lvl "WARN"
    $oraClientPreFlightOk = $false
} else {
    $ociDll = Join-Path $oracleClientLib "oci.dll"
    if (-not (Test-Path $ociDll)) {
        Write-Log "PRE-FLIGHT WARN: oci.dll ausente em '$oracleClientLib'. Thick Mode invalido." -Lvl "WARN"
        $oraClientPreFlightOk = $false
    } else {
        Write-Log "PRE-FLIGHT OK: Oracle Client Thick Mode validado em '$oracleClientLib'."
    }
}

if (-not $oraClientPreFlightOk) {
    Exit-WithCode 9 "ERRO CRITICO: Oracle Client invalido. Extracao vai falhar em Thin Mode. Abortando."
}

$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths @($pythonExe, $extractPy, $generatePy, $configPath)
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando execucao."
}

Write-Log "========================================================================================="
Write-Log "INICIO - Arquitetura Pure-Python (CTE Nativo) Receitas Emitidas. ExecId=$ExecId"

try {
    # =========================================================================
    # 1. Extracao de Dados (Python -> JSON Stdout) com Retry
    # =========================================================================
    Write-Log "Passo 1/2: Extraindo dados via Python (Direct Oracle CTE)..."
    
    $pythonOutput = $null
    $extractOk = Invoke-WithRetry -MaxAttempts 3 -BackoffSeconds @(30, 60, 120) `
        -OperationName "Extracao Oracle (extract_oracle.py)" -ExecId $ExecId -LogPath $LogFile `
        -Action {
            $processInfo = New-Object System.Diagnostics.ProcessStartInfo
            $processInfo.FileName = $pythonExe
            $processInfo.Arguments = "`"$extractPy`" `"$ExecId`""
            $processInfo.RedirectStandardOutput = $true
            $processInfo.RedirectStandardError = $true
            $processInfo.UseShellExecute = $false
            $processInfo.CreateNoWindow = $true
            $processInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8

            $process = [System.Diagnostics.Process]::Start($processInfo)
            $out = $process.StandardOutput.ReadToEnd()
            $err = $process.StandardError.ReadToEnd()
            $process.WaitForExit()

            if ($err) { $err -split "`n" | ForEach-Object { if ($_.Trim()) { Write-AutomacaoLog -Message $_.Trim() -Level "INFO" -ExecId $ExecId -LogPath $LogFile } } }
            
            if ($process.ExitCode -eq 2) {
                Write-Log "Python detectou que nao ha alteracoes relevantes (Idempotencia). Encerrando."
                Exit-WithCode 0 "Processo finalizado (Idempotencia Python)."
            }
            
            if ($process.ExitCode -ne 0) { throw "Python extract_oracle.py falhou com ExitCode=$($process.ExitCode)." }
            if ([string]::IsNullOrWhiteSpace($out)) { throw "Extracao retornou dados vazios (stdout vazio)." }
            
            $script:pythonOutput = $out
            return $true
        }
    
    if (-not $extractOk) {
        Send-AlertaFalhaDefinitiva -TaskName "Receitas Emitidas" -ExecId $ExecId `
            -UltimoErro "Falha definitiva na extracao Oracle apos 3 tentativas." -Tentativas 3 -LogPath $LogFile
        throw "Falha definitiva na extracao Python. Alerta enviado."
    }

    # =========================================================================
    # 2. Geracao do HTML (JSON Stdout -> HTML Stdout) com Retry
    # =========================================================================
    Write-Log "Passo 2/2: Gerando HTML visual moderno..."

    $htmlOutput = $null
    $htmlOk = Invoke-WithRetry -MaxAttempts 3 -BackoffSeconds @(10, 30, 60) `
        -OperationName "Geracao HTML (generate_html_report.py)" -ExecId $ExecId -LogPath $LogFile `
        -Action {
            $genInfo = New-Object System.Diagnostics.ProcessStartInfo
            $genInfo.FileName = $pythonExe
            $genInfo.Arguments = "`"$generatePy`" `"$ExecId`""
            $genInfo.RedirectStandardInput = $true
            $genInfo.RedirectStandardOutput = $true
            $genInfo.RedirectStandardError = $true
            $genInfo.UseShellExecute = $false
            $genInfo.CreateNoWindow = $true
            $genInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8

            $genProcess = [System.Diagnostics.Process]::Start($genInfo)
            $genProcess.StandardInput.Write($script:pythonOutput)
            $genProcess.StandardInput.Close()

            $html = $genProcess.StandardOutput.ReadToEnd()
            $genErr = $genProcess.StandardError.ReadToEnd()
            $genProcess.WaitForExit()

            if ($genErr) { $genErr -split "`n" | ForEach-Object { if ($_.Trim()) { Write-AutomacaoLog -Message $_.Trim() -Level "INFO" -ExecId $ExecId -LogPath $LogFile } } }
            if ($genProcess.ExitCode -ne 0) { throw "Python generate_html_report.py falhou com ExitCode=$($genProcess.ExitCode)." }
            if ([string]::IsNullOrWhiteSpace($html)) { throw "Geracao HTML retornou conteudo vazio." }

            $script:htmlOutput = $html
            return $true
        }

    if (-not $htmlOk) { throw "Falha definitiva na geracao do HTML apos 3 tentativas." }

    # =========================================================================
    # 3. Envio de E-mail com Retry
    # =========================================================================
    Write-Log "Enviando e-mail oficial via Outlook COM..."
    $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $subject = "$($config.email.subject_prefix) - $(Get-Date -Format 'dd/MM/yyyy')"

    $fullHtmlBody = @"
    <p>$($config.email.intro_text)</p>
    $($script:htmlOutput)
"@

    $emailOk = Invoke-WithRetry -MaxAttempts 2 -BackoffSeconds @(15, 30) `
        -OperationName "Envio E-mail Outlook" -ExecId $ExecId -LogPath $LogFile `
        -Action {
            $sent = Send-OutlookEmail -To $config.email.to -Subject $subject -HtmlBody $fullHtmlBody -ExecId $ExecId -LogPath $LogFile
            if (-not $sent) { throw "Send-OutlookEmail retornou false." }
            return $true
        }

    if (-not $emailOk) { throw "Falha definitiva no envio do e-mail via Outlook COM." }

    Write-Log "FIM - Processo concluido com sucesso."
    Exit-WithCode 0

} catch [System.Exception] {
    # Re-throw para nao engolir o Exit-WithCode 0 do bloco de idempotencia
    if ($_.Exception.Message -match "Processo finalizado") { throw }
    Exit-WithCode 1 "ERRO FATAL: $_"
} finally {
    [System.GC]::Collect()
}
