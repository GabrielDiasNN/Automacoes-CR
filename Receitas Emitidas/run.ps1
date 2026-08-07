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
    Version: 2.7.2
    Skill: ai-native-development-standard, python-oracle-migration, protocolo-valeg
    Contract: ipc-stdio, base64-bridge-logs, retry-on-failure, granular-idempotency
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
$libRetry    = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libProcess  = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig   = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libOracle   = Join-Path $projectRoot "lib\Lib-Oracle.psm1"
$libIdempotency = Join-Path $projectRoot "lib\Lib-Idempotency.psm1"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"
$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$generatePy = Join-Path $ScriptDir "generate_html_report.py"
$configPath = Join-Path $ScriptDir "receitas_config.json"
$StatePath  = Join-Path $ScriptDir "receitas_state.json"
$StateTmp   = $StatePath + ".tmp"
$DeliveryStatePath = Join-Path $ScriptDir "delivery_state.json"
$LogDir     = Join-Path $ScriptDir "Logs"

Import-Module $libLogging -Force
Import-Module $libEmail   -Force
Import-Module $libRetry   -Force
Import-Module $libProcess -Force
Import-Module $libConfig  -Force
Import-Module $libOracle  -Force
Import-Module $libIdempotency -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Register-ExecutionTelemetry -AutomationName "Receitas Emitidas"
    } elseif (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}

$LogFile = Get-AutomacaoLogPath -Slug "ReceitasEmitidas" -LogDir $LogDir

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
}

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    Exit-AutomationWithCode -Code $Code -Msg $Msg -ExecId $ExecId -LogPath $LogFile
}

# --- BOOTSTRAP / PRE-FLIGHT ---
Import-HubEnv

$oracleClientLib = [System.Environment]::GetEnvironmentVariable("ORACLE_CLIENT_LIB_DIR", "Process")
$oracleClientFallback = [System.Environment]::GetEnvironmentVariable("ORACLE_CLIENT_PATH", "Process")
if ([string]::IsNullOrWhiteSpace($oracleClientLib)) { $oracleClientLib = $oracleClientFallback }
$oraClientPreFlightOk = $true
if ([string]::IsNullOrWhiteSpace($oracleClientLib)) {
    Write-Log "PRE-FLIGHT WARN: ORACLE_CLIENT_LIB_DIR/ORACLE_CLIENT_PATH nao definido. Thick Mode pode falhar." -Lvl "WARN"
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

Write-Log "INICIO - Arquitetura Pure-Python (CTE Nativo) Receitas Emitidas. ExecId=$ExecId"

try {
    if (-not (Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile)) {
        Exit-WithCode 0 "Execucao abortada: Mutex ja retido por outra instancia deste ExecId."
    }

    try {
        # 1. Extracao de Dados
        Write-Log "Passo 1/2: Extraindo dados via Python (Direct Oracle CTE)..."

        $extractResult = Invoke-OraclePythonScript -PythonExe $pythonExe -ScriptPath $extractPy `
            -ExecId $ExecId -LogPath $LogFile -OperationName "Extracao Oracle" `
            -MaxAttempts 3 -BackoffSeconds @(30, 60, 120)

        if ($extractResult.Idempotent) {
            Write-Log "Python detectou que nao ha alteracoes relevantes (Idempotencia). Encerrando."
            Exit-WithCode 0 "Processo finalizado (Idempotencia Python)."
        }

        if (-not $extractResult.Success) {
            Send-AlertaFalhaDefinitiva -TaskName "Receitas Emitidas" -ExecId $ExecId -UltimoErro "Falha na extracao Oracle." -Tentativas 3 -LogPath $LogFile
            throw "Falha definitiva na extracao Python."
        }

        if ([string]::IsNullOrWhiteSpace($extractResult.Output)) { throw "Extracao retornou dados vazios." }

        # 2. Geracao do HTML
        Write-Log "Passo 2/2: Gerando HTML visual moderno..."

        $htmlResult = Invoke-OraclePythonScript -PythonExe $pythonExe -ScriptPath $generatePy `
            -ExecId $ExecId -LogPath $LogFile -OperationName "Geracao HTML" `
            -MaxAttempts 3 -BackoffSeconds @(10, 30, 60) -InputData $extractResult.Output

        if (-not $htmlResult.Success) { throw "Falha definitiva na geracao do HTML." }
        if ([string]::IsNullOrWhiteSpace($htmlResult.Output)) { throw "Geracao HTML retornou conteudo vazio." }

        $htmlOutput = $htmlResult.Output

        # 3. Envio de E-mail
        Write-Log "Verificando estado de notificacoes (Idempotencia Granular)..."
        $currentHash = Get-LastContentHash -StateTmpPath $StateTmp -StatePath $StatePath

        $deliveryState = Read-DeliveryState -Path $DeliveryStatePath -Channels @("email") -OnWarning {
            param($mensagem)
            Write-Log $mensagem "WARN"
        }

        if (Update-DeliveryStateHash -State $deliveryState -CurrentHash $currentHash) {
            Write-Log "Novo Hash detectado ($currentHash). Resetando status de entrega."
        }

        if (-not (Test-DeliveryPending -State $deliveryState -Channel "email" -CurrentHash $currentHash)) {
            Write-Log "Conteudo identico ao ultimo envio e ja entregue. Suprimindo."
        } else {
            Write-Log "Enviando e-mail oficial via Outlook COM..."
            $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $subject = "$($config.email.subject_prefix) - $(Get-Date -Format 'dd/MM/yyyy')"
            # Destinatario: .env (RE_EMAIL_TO) tem prioridade; config.json e apenas fallback/placeholder.
            $targetTo = if (-not [string]::IsNullOrWhiteSpace($env:RE_EMAIL_TO)) { $env:RE_EMAIL_TO } else { $config.email.to }
            $fullHtmlBody = "<p>$($config.email.intro_text)</p>$($htmlOutput)"

            $emailOk = Invoke-WithRetry -MaxAttempts 2 -BackoffSeconds @(15, 30) -OperationName "Envio E-mail Outlook" -ExecId $ExecId -LogPath $LogFile -Action {
                $sent = Send-OutlookEmail -To $targetTo -Subject $subject -HtmlBody $fullHtmlBody -ExecId $ExecId -LogPath $LogFile
                if (-not $sent) { throw "Send-OutlookEmail retornou false." }
                return $true
            }

            if ($emailOk) {
                Write-Log "E-mail enviado com sucesso. Consolidando estado parcial."
                Set-DeliverySuccess -State $deliveryState -Channel "email"
                Save-DeliveryState -State $deliveryState -Path $DeliveryStatePath
            } else { throw "Falha definitiva no envio do e-mail." }
        }

        if (Test-Path $StateTmp) {
            Write-Log "Confirmando compromisso de estado (Commit Success)..."
            Move-Item -Path $StateTmp -Destination $StatePath -Force
        }

        Write-Log "FIM - Processo concluido com sucesso."
        Exit-WithCode 0
    } finally {
        Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile
    }
} catch [System.Exception] {
    if ($_.Exception.Message -match "Processo finalizado") { throw }
    Exit-WithCode 1 "ERRO FATAL: $_"
} finally {
    [System.GC]::Collect()
}
