<#
.SYNOPSIS
    Orquestrador Nativo para Receitas Emitidas.
.DESCRIPTION
    Este script coordena a geracao do relatorio semanal de receitas emitidas (nao pesadas):
    1. Pre-Flight: Diagnostico de saude do ambiente.
    2. Python (Extract): Busca dados no Oracle utilizando Query CTE Nativa.
    3. Python (HTML): Transforma JSON em relatorio adaptativo multipandonal.
    4. PowerShell: Entrega visual via Outlook utilizando Base64 Bridge para logs.
.NOTES
    Version: 2.5.0
    Skill: ai-native-development-standard, python-oracle-migration
    Contract: ipc-stdio, base64-bridge-logs
#>
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
$envPath     = Join-Path $projectRoot ".env"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$generatePy = Join-Path $ScriptDir "generate_html_report.py"
$configPath = Join-Path $ScriptDir "receitas_config.json"
$LogDir     = Join-Path $ScriptDir "Logs"

Import-Module $libLogging -Force
Import-Module $libEmail   -Force

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

# --- BOOTSTRAP / PRE-FLIGHT ---
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths @($pythonExe, $extractPy, $generatePy, $configPath)
if (-not $preFlight) {
    Write-Log "FALHA NO PRE-FLIGHT CHECK. Abortando execucao." -Lvl "ERRO"; exit 9
}

Write-Log "========================================================================================="
Write-Log "INICIO - Arquitetura Pure-Python (CTE Nativo) Receitas Emitidas. ExecId=$ExecId"

try {
    # 1. Carregar Variaveis
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $key, $value = $line -split '=', 2
                if ($key -and $value) { [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process") }
            }
        }
    }

    # 2. Extracao de Dados (Python -> JSON Stdout)
    Write-Log "Passo 1/2: Extraindo dados via Python (Direct Oracle CTE)..."
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $pythonExe
    $processInfo.Arguments = "`"$extractPy`" `"$ExecId`""
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    
    $process = [System.Diagnostics.Process]::Start($processInfo)
    $pythonOutput = $process.StandardOutput.ReadToEnd() 
    $pythonErrors = $process.StandardError.ReadToEnd() 
    $process.WaitForExit()
    
    if ($pythonErrors) { $pythonErrors -split "`n" | ForEach-Object { if ($_.Trim()) { Write-AutomacaoLog -Message $_.Trim() -Level "INFO" -ExecId $ExecId -LogPath $LogFile } } }
    if ($process.ExitCode -ne 0) { throw "Falha na extracao Python oficial (ExitCode: $($process.ExitCode))." }
    if ([string]::IsNullOrWhiteSpace($pythonOutput)) { throw "Extracao retornou dados vazios." }

    # 3. Geracao do HTML (JSON Stdout -> HTML Stdout)
    Write-Log "Passo 2/2: Gerando HTML visual moderno..."
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
    $genProcess.StandardInput.Write($pythonOutput)
    $genProcess.StandardInput.Close()
    
    $htmlOutput = $genProcess.StandardOutput.ReadToEnd()
    $genErrors = $genProcess.StandardError.ReadToEnd()
    $genProcess.WaitForExit()

    if ($genErrors) { $genErrors -split "`n" | ForEach-Object { if ($_.Trim()) { Write-AutomacaoLog -Message $_.Trim() -Level "INFO" -ExecId $ExecId -LogPath $LogFile } } }
    if ($genProcess.ExitCode -ne 0) { throw "Falha na geracao do HTML (ExitCode: $($genProcess.ExitCode))." }

    # 4. Envio de E-mail
    Write-Log "Enviando e-mail oficial via Outlook COM..."
    $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $subject = "$($config.email.subject_prefix) - $(Get-Date -Format 'dd/MM/yyyy')"
    
    $fullHtmlBody = @"
    <p>$($config.email.intro_text)</p>
    $htmlOutput
"@

    $sent = Send-OutlookEmail -To $config.email.to -Subject $subject -HtmlBody $fullHtmlBody -ExecId $ExecId -LogPath $LogFile
    if (-not $sent) { throw "Falha no envio via Outlook COM." }

    Write-Log "FIM - Processo concluido com sucesso."
    Write-Log "========================================================================================="
    
} catch [System.Exception] {
    Write-Log "ERRO FATAL: $_" -Lvl "ERRO"; exit 1
} finally {
    [System.GC]::Collect()
}

