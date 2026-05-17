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
Import-Module $libConfig  -Force

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
    if ($Msg) { Write-Log $Msg -Lvl $(if ($Code -eq 0) { "INFO" } else { "ERRO" }) }
    Write-Log "FIM - Finalizado. ExitCode=$Code"
    Write-Log "========================================================================================="
    if (Get-Command Close-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        $finalStatus = if ($Code -eq 0) { "SUCCESS" } else { "ERROR" }
        Close-ExecutionTelemetry -ExecId $ExecId -Status $finalStatus -LogPath $LogFile
    }
    exit $Code
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
        $pythonOutput = $null
        Import-Module $libProcess -Force

        $extractOk = Invoke-WithRetry -MaxAttempts 3 -BackoffSeconds @(30, 60, 120) -OperationName "Extracao Oracle" -ExecId $ExecId -LogPath $LogFile -Action {
            $res = Invoke-NativeProcess -FilePath $pythonExe -Arguments "`"$extractPy`" `"$ExecId`"" -LogAction {
                param($msg, $lvl)
                # Filtramos logs do motor Python, nao precisamos do stdout JSON aqui
                if ($lvl -ne "INFO" -or ($msg.Trim() -and -not $msg.StartsWith("[") -and -not $msg.StartsWith("{"))) {
                    Write-AutomacaoLog -Message $msg.Trim() -Level $lvl -ExecId $ExecId -LogPath $LogFile
                }
            }

            if ($res.ExitCode -eq 2) {
                Write-Log "Python detectou que nao ha alteracoes relevantes (Idempotencia). Encerrando."
                Exit-WithCode 0 "Processo finalizado (Idempotencia Python)."
            }

            if ($res.ExitCode -ne 0) { throw "Python extract_oracle.py falhou com ExitCode=$($res.ExitCode)." }
            if ([string]::IsNullOrWhiteSpace($res.StandardOutput)) { throw "Extracao retornou dados vazios." }

            $script:pythonOutput = $res.StandardOutput
            return $true
        }

        if (-not $extractOk) {
            Send-AlertaFalhaDefinitiva -TaskName "Receitas Emitidas" -ExecId $ExecId -UltimoErro "Falha na extracao Oracle." -Tentativas 3 -LogPath $LogFile
            throw "Falha definitiva na extracao Python."
        }

        # 2. Geracao do HTML
        Write-Log "Passo 2/2: Gerando HTML visual moderno..."
        $htmlOutput = $null
        $htmlOk = Invoke-WithRetry -MaxAttempts 3 -BackoffSeconds @(10, 30, 60) -OperationName "Geracao HTML" -ExecId $ExecId -LogPath $LogFile -Action {
            $res = Invoke-NativeProcess -FilePath $pythonExe -Arguments "`"$generatePy`" `"$ExecId`"" -InputData $script:pythonOutput -LogAction {
                param($msg, $lvl)
                if ($lvl -ne "INFO") { Write-AutomacaoLog -Message $msg.Trim() -Level $lvl -ExecId $ExecId -LogPath $LogFile }
            }
            if ($res.ExitCode -ne 0) { throw "Python generate_html_report.py falhou com ExitCode=$($res.ExitCode)." }
            if ([string]::IsNullOrWhiteSpace($res.StandardOutput)) { throw "Geracao HTML retornou conteudo vazio." }
            $script:htmlOutput = $res.StandardOutput
            return $true
        }

        if (-not $htmlOk) { throw "Falha definitiva na geracao do HTML." }

        # 3. Envio de E-mail
        Write-Log "Verificando estado de notificacoes (Idempotencia Granular)..."
        $currentHash = ""
        if (Test-Path $StateTmp) {
            $currentHash = (Get-Content $StateTmp -Raw -Encoding UTF8 | ConvertFrom-Json).last_hash
        } elseif (Test-Path $StatePath) {
            $currentHash = (Get-Content $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json).last_hash
        }

        $deliveryState = @{ last_sent_hash = ""; delivery_status = @{ email = @{ success = $false; sent_at = $null } } }
        if (Test-Path $DeliveryStatePath) {
            try {
                $savedState = Get-Content $DeliveryStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($savedState.last_sent_hash) { $deliveryState.last_sent_hash = $savedState.last_sent_hash }
                if ($null -ne $savedState.delivery_status.email) {
                    $deliveryState.delivery_status.email.success = [bool]$savedState.delivery_status.email.success
                    $deliveryState.delivery_status.email.sent_at = $savedState.delivery_status.email.sent_at
                }
            } catch [System.Exception] {
                Write-Log ("Falha ao ler delivery_state.json existente. Estado sera reiniciado. Motivo: {0}" -f $_.Exception.Message) "WARN"
            }
        }

        if ($currentHash -and $currentHash -ne $deliveryState.last_sent_hash) {
            Write-Log "Novo Hash detectado ($currentHash). Resetando status de entrega."
            $deliveryState.last_sent_hash = $currentHash
            $deliveryState.delivery_status.email.success = $false
        }

        if ($deliveryState.delivery_status.email.success -and ($currentHash -eq $deliveryState.last_sent_hash)) {
            Write-Log "Conteudo identico ao ultimo envio e ja entregue. Suprimindo."
        } else {
            Write-Log "Enviando e-mail oficial via Outlook COM..."
            $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $subject = "$($config.email.subject_prefix) - $(Get-Date -Format 'dd/MM/yyyy')"
            $targetTo = $config.email.to
            $fullHtmlBody = "<p>$($config.email.intro_text)</p>$($script:htmlOutput)"

            $emailOk = Invoke-WithRetry -MaxAttempts 2 -BackoffSeconds @(15, 30) -OperationName "Envio E-mail Outlook" -ExecId $ExecId -LogPath $LogFile -Action {
                $sent = Send-OutlookEmail -To $targetTo -Subject $subject -HtmlBody $fullHtmlBody -ExecId $ExecId -LogPath $LogFile
                if (-not $sent) { throw "Send-OutlookEmail retornou false." }
                return $true
            }

            if ($emailOk) {
                Write-Log "E-mail enviado com sucesso. Consolidando estado parcial."
                $deliveryState.delivery_status.email.success = $true
                $deliveryState.delivery_status.email.sent_at = (Get-Date -Format 'dd/MM/yyyy HH:mm:ss')
                $deliveryState | ConvertTo-Json -Depth 5 | Out-File $DeliveryStatePath -Encoding UTF8
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
