# ==============================================================================
# ARQUIVO: run.ps1
# VERSÃO: 2.1 (ARQUITETURA CORPORATIVA - IPC STDIO)
# DESCRIÇÃO: Orquestrador nativo para Receitas Emitidas.
#            Comunicação via memória (JSON/HTML) eliminando arquivos temporários.
# ==============================================================================
[CmdletBinding()]
param([string]$ExecId = "")

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

# Bibliotecas e Caminhos (Validação de Caminhos Absolutos)
$projectRoot = Split-Path -Parent $ScriptDir
$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$envPath     = Join-Path $projectRoot ".env"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

# Scripts Python
$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$generatePy = Join-Path $ScriptDir "generate_html_report.py"
$configPath = Join-Path $ScriptDir "receitas_config.json"
$LogDir     = Join-Path $ScriptDir "Logs"

# 🔹 Validação Preventiva de Caminhos (Rule 4)
foreach ($p in @($libLogging, $libEmail, $envPath, $pythonExe, $extractPy, $generatePy, $configPath)) {
    if (-not (Test-Path $p)) { throw "Caminho obrigatorio nao encontrado: $p" }
}

# Importa bibliotecas
Import-Module $libLogging -Force
Import-Module $libEmail   -Force

# ID de Execução
if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}
$LogFile = Get-AutomacaoLogPath -Slug "ReceitasEmitidas" -LogDir $LogDir

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
}

Write-Log "========================================================================================="
Write-Log "INICIO - Arquitetura IPC Stdio Receitas Emitidas. ExecId=$ExecId"

try {
    # 1. Carregar Variáveis de Ambiente (.env) para o PROCESSO ATUAL (Rule 1)
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $key, $value = $line -split '=', 2
            if ($key -and $value) { 
                [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process") 
            }
        }
    }

    # 2. Extração de Dados (Fase 1: Oracle -> JSON via STDOUT)
    Write-Log "Passo 1/2: Extraindo dados via Python (Stdout IPC)..."
    
    $pythonOutput = ""
    $pythonErrors = ""
    
    # Executa Python capturando stdout (dados) e stderr (logs) separadamente
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
    
    # Processa logs do Python vindos pelo stderr
    if ($pythonErrors) {
        $pythonErrors -split "`n" | ForEach-Object { if ($_.Trim()) { Write-Log "Python-Extract-Log: $($_.Trim())" } }
    }

    if ($process.ExitCode -ne 0) { throw "Falha critica no processo de extracao Python (ExitCode: $($process.ExitCode))." }
    if ([string]::IsNullOrWhiteSpace($pythonOutput)) { throw "Python nao retornou dados JSON no stdout." }

    # 3. Geração do HTML (Fase 2: JSON via STDIN -> HTML via STDOUT)
    Write-Log "Passo 2/2: Gerando HTML via Python (Pipe IPC)..."
    
    $htmlOutput = ""
    $genErrors = ""
    
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

    if ($genErrors) {
        $genErrors -split "`n" | ForEach-Object { if ($_.Trim()) { Write-Log "Python-HTML-Log: $($_.Trim())" } }
    }

    if ($genProcess.ExitCode -ne 0) { throw "Falha na geracao do HTML via Python." }
    if ([string]::IsNullOrWhiteSpace($htmlOutput)) { throw "Python nao retornou corpo HTML no stdout." }

    # 4. Envio de E-mail (Memória Pura)
    Write-Log "Enviando e-mail oficial (Memória Pura)..."
    $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $subject = "$($config.email.subject_prefix) - $(Get-Date -Format 'dd/MM/yyyy')"
    
    # Injetar Intro Text no HTML vindo da memória
    $fullHtmlBody = @"
    <p>$($config.email.intro_text)</p>
    $htmlOutput
"@

    $sent = Send-OutlookEmail -To $config.email.to -Subject $subject -HtmlBody $fullHtmlBody -ExecId $ExecId -LogPath $LogFile
    if (-not $sent) { throw "Falha no envio via Outlook COM." }

    Write-Log "FIM - Processo concluido com sucesso via IPC Stdio."
    Write-Log "========================================================================================="
    
} catch {
    Write-Log "ERRO FATAL: $_" -Lvl "ERRO"
    # Garante fechamento de processos em caso de erro
    Write-Log "========================================================================================="
    exit 1
} finally {
    # Coleta de lixo forçada para liberar objetos COM residuais
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
