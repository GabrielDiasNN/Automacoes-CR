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

    Version: 2.3.0

    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-execution-contract, protocolo-valeg

    Contract: retry-on-failure, base64-bridge-logs, granular-idempotency

#>

# {

#   "name": "orchestrator-receitas-bloqueadas",

#   "version": "2.3.0",

#   "skill": "powershell-automation-monitor",

#   "description": "Use when orchestrating the multi-channel distribution of blocked recipes (Email/WhatsApp)."

# }

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

$LogDir     = Join-Path $BasePath "Logs"

$PythonStatePath = Join-Path $BasePath "receitas_state.json"

$PythonStateTmp  = $PythonStatePath + ".tmp"

$EmailStatePath = Join-Path $BasePath "email_state.json"

$MaxTimeoutSec = 300

# Bibliotecas e Caminhos

$projectRoot = Split-Path -Parent $ScriptDir

$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"

$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"

$libRetry    = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libProcess  = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig   = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libOracle   = Join-Path $projectRoot "lib\Lib-Oracle.psm1"
$SendWhatsAppScript = Join-Path $projectRoot "lib\Send-WhatsApp.ps1"

$WhatsAppConfig = Join-Path $BasePath "whatsapp-config.json"

# Activate VENV

$venvActivate = Join-Path $projectRoot ".venv\Scripts\activate.ps1"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

Import-Module $libLogging -Force

Import-Module $libEmail   -Force

Import-Module $libRetry   -Force
Import-Module $libProcess -Force
Import-Module $libConfig  -Force
Import-Module $libOracle  -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {

    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {

        Register-ExecutionTelemetry -AutomationName "Receitas Bloqueadas"

    } elseif (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }

}

$LogFile = Get-AutomacaoLogPath -Slug "ReceitasBloqueadas" -LogDir $LogDir

# Helper para Log com suporte a Base64 Interno (Skill log-standardization)

function Write-Log {

    param([string]$Msg, [string]$Lvl = "INFO")

    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile

}

function Get-ForwardedLogLevel {

    param(
        [string]$Msg,
        [string]$Fallback = "INFO"
    )

    if ([string]::IsNullOrWhiteSpace($Msg)) { return $Fallback }

    $detected = [regex]::Match($Msg, '\[(INFO|WARN|ERROR|ERRO|DEBUG)\]', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $detected.Success) { return $Fallback }

    switch ($detected.Groups[1].Value.ToUpperInvariant()) {
        "ERROR" { return "ERRO" }
        "ERRO"  { return "ERRO" }
        "WARN"  { return "WARN" }
        "DEBUG" { return "DEBUG" }
        default { return "INFO" }
    }

}

function Exit-WithCode {

    param([int]$Code, [string]$Msg = "")

    if ($Msg) { Write-Log $Msg -Lvl $(if ($Code -eq 0 -or $Code -eq 2) { "INFO" } else { "ERRO" }) }

    Write-Log "FIM - Finalizado. ExitCode=$Code"

    Write-Log "========================================================================================="

    if (Get-Command Close-ExecutionTelemetry -ErrorAction SilentlyContinue) {

        $finalStatus = if ($Code -eq 0 -or $Code -eq 2) { "SUCCESS" } else { "ERROR" }

        Close-ExecutionTelemetry -ExecId $ExecId -Status $finalStatus -LogPath $LogFile

    }

    exit $Code

}

# --- BOOTSTRAP / PRE-FLIGHT ---

# Housekeeping: Limpa artefatos temporarios orfaos (caso existam)

Get-ChildItem -Path $ScriptDir -Filter ".tmp_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue

$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths @($PythonScript, $SendWhatsAppScript, $WhatsAppConfig, $EmailConfigPath)

if (-not $preFlight) {

    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando execucao."

}

if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {

    Invoke-LogRotation -LogPath $LogFile -KeepDays 15

}

Write-Log "INICIO - run.ps1 Receitas Bloqueadas (Python + Node.js). ExecId=$ExecId"

    try {

        $channelFailureExitCode = 0
        $channelFailureMessage = ""

        # 0. Bloqueio de Concorrencia (Pilar A - Valeg)

        Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile

        try {

            try {

                Import-HubEnv

            } catch [System.Exception] {

                Write-Log "Falha ao carregar .env: $_" -Lvl "WARN"

            }

            # 1. Executar Python Script com Retry

            Write-Log "Acionando script Python..."

            if (-not (Test-Path $pythonExe)) {

                Exit-WithCode 2 "Python do ambiente virtual nao encontrado em $pythonExe."

            }

            try {

                $pyResult = Invoke-OraclePythonScript -PythonExe $pythonExe -ScriptPath $PythonScript `
                    -ExecId $ExecId -LogPath $LogFile `
                    -OperationName "Processamento Python (processar_receitas.py)" `
                    -MaxAttempts 3 -BackoffSeconds @(60, 120, 300)

                if ($pyResult.Idempotent) {
                    Write-Log "Python detectou idempotencia (ExitCode 2). Suprimindo notificacoes."
                    Exit-WithCode 2 "Processo finalizado (Idempotencia Python)."
                }

                if (-not $pyResult.Success) {
                    Send-AlertaFalhaDefinitiva -TaskName "Receitas Bloqueadas" -ExecId $ExecId -UltimoErro "Falha definitiva no processamento Python apos 3 tentativas." -Tentativas 3 -LogPath $LogFile
                    Exit-WithCode 3 "Falha definitiva no script Python. Alerta de falha enviado."
                }
            } catch [System.Exception] {
                if ($_.Exception.Message -match "Processo finalizado") { throw }
                Exit-WithCode 4 "Falha ao invocar script Python: $_"
            }

            # 2. Resolucao de Idempotencia Granular (ADR-013)

            Write-Log "Verificando estado de notificacoes (Idempotencia Granular)..."

            if (Test-Path $HtmlPath) {

                $currentHash = ""

                if (Test-Path $PythonStatePath) {

                    $currentHash = (Get-Content $PythonStatePath -Raw -Encoding UTF8 | ConvertFrom-Json).last_hash

                }

                # Leitura Resiliente do Estado

                $deliveryState = @{

                    last_sent_hash = ""

                    delivery_status = @{

                        email = @{ success = $false; sent_at = $null }

                        whatsapp = @{ success = $false; sent_at = $null; exit_code = $null }

                    }

                }

                if (Test-Path $EmailStatePath) {

                    try {

                        $savedState = Get-Content $EmailStatePath -Raw -Encoding UTF8 | ConvertFrom-Json

                        if ($savedState.last_sent_hash) { $deliveryState.last_sent_hash = $savedState.last_sent_hash }

                        if ($null -ne $savedState.delivery_status) {

                            if ($null -ne $savedState.delivery_status.email) {

                                $deliveryState.delivery_status.email.success = [bool]$savedState.delivery_status.email.success

                                $deliveryState.delivery_status.email.sent_at = $savedState.delivery_status.email.sent_at

                            }

                            if ($null -ne $savedState.delivery_status.whatsapp) {

                                $deliveryState.delivery_status.whatsapp.success = [bool]$savedState.delivery_status.whatsapp.success

                                $deliveryState.delivery_status.whatsapp.sent_at = $savedState.delivery_status.whatsapp.sent_at

                            }

                        }

                    } catch [System.Exception] {

                        Write-Log "Aviso: Falha ao parsear email_state.json. Iniciando com estado limpo." -Lvl "WARN"

                    }

                }

                # Se o hash mudou, resetar status de entrega

                if ($currentHash -and $currentHash -ne $deliveryState.last_sent_hash) {

                    Write-Log "Novo Hash detectado ($currentHash). Resetando status de entrega."

                    $deliveryState.last_sent_hash = $currentHash

                    $deliveryState.delivery_status.email.success = $false

                    $deliveryState.delivery_status.whatsapp.success = $false

                }

                $skipEmail = $deliveryState.delivery_status.email.success -and ($currentHash -eq $deliveryState.last_sent_hash)

                $skipWhatsApp = $deliveryState.delivery_status.whatsapp.success -and ($currentHash -eq $deliveryState.last_sent_hash)

                if ($skipEmail -and $skipWhatsApp) {

                    Write-Log "Conteudo identico ao ultimo envio (Hash match) e canais entregues. Suprimindo E-mail e WhatsApp."

                    # Consolidar Python State mesmo se pular notificacoes (caso nao tenha sido consolidado antes)

                    if (Test-Path $PythonStateTmp) {

                        Move-Item -Path $PythonStateTmp -Destination $PythonStatePath -Force

                        Write-Log "Estado Python atualizado: $PythonStatePath"

                    }

                } else {

                    $htmlBody = Get-Content $HtmlPath -Raw -Encoding UTF8

                    $emailConfig = Get-Content $EmailConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json

                    # Destinatarios: .env (RB_EMAIL_TO/CC) tem prioridade; config.json e apenas fallback/placeholder.
                    $to = if (-not [string]::IsNullOrWhiteSpace($env:RB_EMAIL_TO)) { $env:RB_EMAIL_TO } else { $emailConfig.email.to -join ";" }

                    $cc = if (-not [string]::IsNullOrWhiteSpace($env:RB_EMAIL_CC)) { $env:RB_EMAIL_CC } elseif ($emailConfig.email.cc) { $emailConfig.email.cc -join ";" } else { $null }

                    $bcc = if ($emailConfig.email.bcc) { $emailConfig.email.bcc -join ";" } else { $null }

                    $subject = "Alerta: Receitas Bloqueadas - $(Get-Date -Format 'dd/MM/yyyy')"

                    # --- Envio de E-mail ---

                    if (-not $skipEmail) {

                        if ([string]::IsNullOrWhiteSpace($to)) {

                            Write-Log "Destinatarios 'to' nao configurados. Pulando e-mail." -Lvl "WARN"

                            $deliveryState.delivery_status.email.success = $true

                        } else {

                            # Verificar Modo Teste (Hierarquia: Orquestrador > VS Code)

                            $globalTestEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", "User")

                            $isTestMode = $false

                            if ($env:ORCHESTRATOR_TEST_MODE -eq "true") {

                                $isTestMode = $true

                            } elseif ($env:ORCHESTRATOR_TEST_MODE -eq "false") {

                                $isTestMode = $false

                            } else {

                                if (-not [string]::IsNullOrWhiteSpace($globalTestEmail)) { $isTestMode = $true }

                            }

                            Write-Log "Enviando e-mail para $to..."

                            $emailOk = Invoke-WithRetry -MaxAttempts 2 -BackoffSeconds @(15, 30) -OperationName "Envio E-mail Outlook" -ExecId $ExecId -LogPath $LogFile -Action {
                                $sent = Send-OutlookEmail -To $to -Cc $cc -Bcc $bcc -Subject $subject -HtmlBody $htmlBody -Attachments @($ExcelPath) -ExecId $ExecId -LogPath $LogFile
                                if (-not $sent) { throw "Send-OutlookEmail retornou false." }
                                return $true
                            }

                            if ($emailOk) {

                                Write-Log "E-mail enviado com sucesso. Consolidando estado parcial (E-mail)."

                                $deliveryState.delivery_status.email.success = $true

                                $deliveryState.delivery_status.email.sent_at = (Get-Date -Format 'dd/MM/yyyy HH:mm:ss')

                                $deliveryState | ConvertTo-Json -Depth 5 | Out-File $EmailStatePath -Encoding UTF8

                            } else {

                                Write-Log "Falha definitiva no envio de e-mail. Canal pendente para retentativa." -Lvl "ERRO"

                            }

                        }

                    } else {

                        Write-Log "E-mail ja entregue para este lote. Pulando envio."

                    }

                    # --- Envio de WhatsApp ---

                    if (-not $skipWhatsApp) {

                        Write-Log "Disparando Send-WhatsApp.ps1. ExecId=$ExecId Mode=AUTO"

                        try {

                            $waArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -Mode AUTO -ConfigPath `"$WhatsAppConfig`""
                            $waResult = Invoke-NativeProcess -FilePath "powershell.exe" -Arguments $waArgs -WorkingDirectory $BasePath -LogAction {
                                param($msg, $lvl)
                                if (-not [string]::IsNullOrWhiteSpace($msg)) {
                                    Write-AutomacaoLog -Message $msg -Level (Get-ForwardedLogLevel -Msg $msg -Fallback $lvl) -ExecId $ExecId -LogPath $LogFile
                                }
                            }
                            $whatsAppExit = $waResult.ExitCode

                            Write-Log "Send-WhatsApp.ps1 finalizado. ExitCode=$whatsAppExit"

                            $deliveryState.delivery_status.whatsapp.exit_code = $whatsAppExit

                            $whatsappSuccess = $false

                            if ($whatsAppExit -eq 0 -or $whatsAppExit -eq 40 -or $whatsAppExit -eq 23) {

                                if ($whatsAppExit -eq 40) { Write-Log "WhatsApp ignorado por lock ativo (comportamento normal)." -Lvl "INFO" }

                                if ($whatsAppExit -eq 23) { Write-Log "WhatsApp em cooldown (comportamento normal)." -Lvl "INFO" }

                                $whatsappSuccess = $true

                            } elseif ($whatsAppExit -eq 21) {

                                Write-Log "WhatsApp requer reautenticacao. Verifique o QR Code." -Lvl "WARN"
                                $channelFailureExitCode = 21
                                $channelFailureMessage = "Execucao concluida com falha parcial: WhatsApp requer reautenticacao antes de nova tentativa."

                            } else {

                                Write-Log "Send-WhatsApp.ps1 retornou ExitCode $whatsAppExit. Notificacao incompleta." -Lvl "WARN"
                                $channelFailureExitCode = if ($whatsAppExit -gt 0) { $whatsAppExit } else { 24 }
                                $channelFailureMessage = "Execucao concluida com falha parcial no canal WhatsApp. Revise os logs do canal antes de novo requeue."

                            }

                            if ($whatsappSuccess) {

                                Write-Log "WhatsApp concluido com sucesso. Consolidando estado parcial (WhatsApp)."

                                $deliveryState.delivery_status.whatsapp.success = $true

                                $deliveryState.delivery_status.whatsapp.sent_at = (Get-Date -Format 'dd/MM/yyyy HH:mm:ss')

                                $deliveryState | ConvertTo-Json -Depth 5 | Out-File $EmailStatePath -Encoding UTF8

                            }

                        } catch [System.Exception] {

                            Write-Log "Falha ao iniciar processo WhatsApp: $_" -Lvl "WARN"
                            $deliveryState.delivery_status.whatsapp.exit_code = 24
                            $channelFailureExitCode = 24
                            $channelFailureMessage = "Execucao concluida com falha parcial no canal WhatsApp. O wrapper nao conseguiu completar a notificacao."

                        }

                    } else {

                        Write-Log "WhatsApp ja entregue para este lote. Pulando envio."

                    }

                    # --- SAFE-STATE COMMIT (Python Engine) ---

                    if (Test-Path $PythonStateTmp) {

                        Move-Item -Path $PythonStateTmp -Destination $PythonStatePath -Force

                        Write-Log "Estado Python atualizado: $PythonStatePath"

                    }

                }

            }

            if ($channelFailureExitCode -ne 0) {

                Exit-WithCode $channelFailureExitCode $channelFailureMessage

            }

            Exit-WithCode 0 "Execucao concluida com sucesso."

        } finally {

            # Liberacao do bloqueio global INDEPENDENTE de erro interno

            Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile

        }

    } catch [System.Exception] {

        if ($_.Exception.Message -match "Processo finalizado") { throw }

        Exit-WithCode 4 "Falha critica na orquestracao: $_"

    }


