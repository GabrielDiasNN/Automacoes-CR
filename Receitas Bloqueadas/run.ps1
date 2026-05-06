<#
.SYNOPSIS
    Orquestrador PS-Nativo para Receitas Bloqueadas.
.DESCRIPTION
    Este script coordena o processamento de receitas retidas e sua distribuicao multicanal:
    1. Pre-Flight: Diagnostico de saude (Python, WhatsApp Config, Espaco em Disco).
    2. Python: Processa a logica de negocio, consulta Oracle e gera artefatos de saida (.xlsx e .html).
    3. E-mail: Envia o HTML gerado para os destinatarios configurados.
    4. WhatsApp Bridge: Dispara notificacoes via Node.js utilizando idempotencia.
.NOTES
    Version: 2.0.1
    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-execution-contract
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
$PythonScript = Join-Path $BasePath "processar_receitas.py"
$ExcelPath = Join-Path $BasePath "Receitas Bloqueadas.xlsx"
$HtmlPath = Join-Path $BasePath "email_body.html"
$EmailConfigPath = Join-Path $BasePath "receitas_config.json"
$LogDir = Join-Path $BasePath "Logs"
$MaxTimeoutSec = 300

# Bibliotecas e Caminhos
$projectRoot = Split-Path -Parent $ScriptDir
$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$SendWhatsAppScript = Join-Path $projectRoot "lib\Send-WhatsApp.ps1"
$WhatsAppConfig = Join-Path $BasePath "whatsapp-config.json"

# Activate VENV
$venvActivate = Join-Path $projectRoot ".venv\Scripts\activate.ps1"

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
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths @($PythonScript, $SendWhatsAppScript, $WhatsAppConfig, $EmailConfigPath)
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando execucao."
}

if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
    Invoke-LogRotation -LogPath $LogFile -KeepDays 15
}

Write-Log "========================================================================================="
Write-Log "INICIO - run.ps1 Receitas Bloqueadas (Python + Node.js). ExecId=$ExecId"

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
} catch [System.IO.IOException] {
    Write-Log "Falha de IO ao carregar .env: $_" -Lvl "WARN"
} catch [System.Exception] {
    Write-Log "Falha generica ao carregar .env: $_" -Lvl "WARN"
}

# 1. Executar Python Script
Write-Log "Acionando script Python..."
if (-not (Test-Path $venvActivate)) {
    Exit-WithCode 2 "Virtual environment nao encontrado em $venvActivate."
}

try {
    # Carrega VENV
    . $venvActivate
    
    # Chama o script python capturando StdErr (os logs em base64)
    $proc = Start-Process -FilePath "python" -ArgumentList "`"$PythonScript`" `"$ExecId`"" -NoNewWindow -Wait -PassThru -RedirectStandardError "$LogDir\python_stderr.log"
    
    # Processa os logs retornados do python (skill ipc-stdio)
    if (Test-Path "$LogDir\python_stderr.log") {
        $pyLogs = Get-Content "$LogDir\python_stderr.log" -Encoding UTF8
        foreach ($l in $pyLogs) {
            if ([string]::IsNullOrWhiteSpace($l)) { continue }
            if ($l.StartsWith("B64:")) {
                try {
                    $b64Str = $l.Substring(4)
                    $bytes = [System.Convert]::FromBase64String($b64Str)
                    $decoded = [System.Text.Encoding]::UTF8.GetString($bytes)
                    Write-AutomacaoLog -Message "B64:$b64Str" -Level "INFO" -ExecId $ExecId -LogPath $LogFile
                } catch [System.Exception] {
                    Write-AutomacaoLog -Message "Falha ao decodificar B64: $l" -Level "WARN" -ExecId $ExecId -LogPath $LogFile
                }
            } else {
                Write-AutomacaoLog -Message $l -Level "INFO" -ExecId $ExecId -LogPath $LogFile
            }
        }
        Remove-Item "$LogDir\python_stderr.log" -Force -ErrorAction SilentlyContinue
    }
    
    if ($proc.ExitCode -ne 0) {
        Exit-WithCode 3 "Script Python retornou ExitCode $($proc.ExitCode)."
    }

} catch [System.ComponentModel.Win32Exception] {
    Exit-WithCode 4 "Falha de processo ao invocar script Python: $_"
} catch [System.Exception] {
    Exit-WithCode 4 "Falha ao invocar script Python: $_"
}

# 2. Enviar E-mail
Write-Log "Preparando envio de e-mail..."
if (Test-Path $HtmlPath) {
    try {
        $htmlBody = Get-Content $HtmlPath -Raw -Encoding UTF8
        $emailConfig = Get-Content $EmailConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        
        $to = $emailConfig.email.to -join ";"
        $cc = if ($emailConfig.email.cc) { $emailConfig.email.cc -join ";" } else { $null }
        $bcc = if ($emailConfig.email.bcc) { $emailConfig.email.bcc -join ";" } else { $null }
        
        $subject = "Alerta: Receitas Bloqueadas - $(Get-Date -Format 'dd/MM/yyyy')"
        
        if ([string]::IsNullOrWhiteSpace($to)) {
            Write-Log "Destinatarios 'to' nao configurados. Pulando e-mail." -Lvl "WARN"
        } else {
            Write-Log "Enviando e-mail para $to..."
            Send-OutlookEmail -To $to -Cc $cc -Bcc $bcc -Subject $subject -HtmlBody $htmlBody -Attachments @($ExcelPath) -ExecId $ExecId -LogPath $LogFile
            Write-Log "E-mail enviado com sucesso."
        }
    } catch [System.Management.Automation.RuntimeException] {
        Write-Log "Falha de runtime ao enviar e-mail: $_" -Lvl "ERRO"
    } catch [System.Exception] {
        Write-Log "Falha ao enviar e-mail: $_" -Lvl "ERRO"
    }
} else {
    Write-Log "Arquivo $HtmlPath nao gerado. Nenhuma receita para notificar ou erro no processo." -Lvl "WARN"
    Exit-WithCode 0 "Processo concluido sem dados."
}

# 3. WhatsApp Post-Execution
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
