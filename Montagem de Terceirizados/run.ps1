<#

.SYNOPSIS

    Orquestrador Oficial para Montagem de Terceirizados (Pure-Native).

.DESCRIPTION

    Este script coordena o ciclo de vida da automação utilizando extração direta do Oracle via Python.

    Não utiliza mais dependências de Excel/VBA (Migração Concluída).

.NOTES

    Version: 2.3.0

    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-runtime-safety

    Contract: native-fetch-logic, ipc-file-payload, structured-logging, preflight-v1, granular-idempotency

    Emite eventos de log estruturados (docs/logging-standard.md).

#>

[CmdletBinding()]

param(

    [string]$ExecId = "",

    [switch]$EmailPreviewOnly,

    [string]$EmailToTest = "",

    [string]$EmailCcTest = ""

)

$ErrorActionPreference = "Stop"

# Configuração Global de Encoding para Interoperabilidade

$OutputEncoding = [System.Text.Encoding]::UTF8

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot

if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

# Bibliotecas e Caminhos

$projectRoot = Split-Path -Parent $ScriptDir

$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libLogEvent = Join-Path $projectRoot "lib\Lib-LogEvent.psm1"
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$libProcess  = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libRetry    = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libConfig   = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libOracle   = Join-Path $projectRoot "lib\Lib-Oracle.psm1"
$libIdempotency = Join-Path $projectRoot "lib\Lib-Idempotency.psm1"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

# Scripts

$extractPy  = Join-Path $ScriptDir "extract_oracle.py"

$validatePy = Join-Path $ScriptDir "validate_and_generate_html.py"

$CacheFile  = Join-Path $ScriptDir ".cache_erros.json"

$CacheTmp   = $CacheFile + ".tmp"

$LogDir     = Join-Path $ScriptDir "Logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

Import-Module $libLogging  -Force
Import-Module $libLogEvent -Force

Import-Module $libEmail   -Force
Import-Module $libConfig  -Force
Import-Module $libProcess -Force
Import-Module $libRetry   -Force
Import-Module $libOracle  -Force
Import-Module $libIdempotency -Force

$AutomationName = "Montagem de Terceirizados"

if ([string]::IsNullOrWhiteSpace($ExecId)) {

    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {

        Register-ExecutionTelemetry -AutomationName $AutomationName

    } elseif (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }

}

$LogFile = Get-AutomacaoLogPath -Slug "Montagem_Terceirizados" -LogDir $LogDir

# --- CONTEXTO DE LOG ESTRUTURADO (docs/logging-standard.md) ---
$TraceId = Resolve-HubTraceId -Slug "mt"
Initialize-HubLogContext -Automation $AutomationName -ExecId $ExecId -TraceId $TraceId `
    -LogPath $LogFile -Component "ps_script"
$env:HUB_LOG_STRUCTURED = "1"
$env:HUB_AUTOMATION     = $AutomationName
$env:HUB_EXEC_ID        = $ExecId
$env:HUB_TRACE_ID       = $TraceId

$script:RunSw = [System.Diagnostics.Stopwatch]::StartNew()

function Write-Log {

    param([string]$Msg, [string]$Lvl = "INFO", [string]$Step = "")

    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile -Step $Step

}

# execution.end e emitido uma unica vez (guarda $script:fimEmitted). MT-02 tem
# multiplos pontos de exit (preflight/catch/pos-finally), por isso o helper em
# vez do Exit-WithCode dos demais run.ps1. Os contadores sao capturados do
# payload em $script:fimCounts antes de o .payload_*.json ser apagado.
$script:fimEmitted = $false
$script:fimCounts = $null
function Write-Fim {
    param([int]$Code, [string]$Reason = "", [hashtable]$Counts)
    if ($script:fimEmitted) { return }
    $script:fimEmitted = $true
    if ((Get-Command Get-HubLogContext -ErrorAction SilentlyContinue) -and (Get-HubLogContext)) {
        $counts = if ($Counts) { $Counts } else { $script:fimCounts }
        $fimArgs = @{
            OutcomeCode   = $Code
            OutcomeReason = if ($Reason) { $Reason } else { "ExitCode=$Code" }
            DurationMs    = [int]$script:RunSw.Elapsed.TotalMilliseconds
            Message       = "FIM - ExitCode=$Code"
        }
        if ($counts) { $fimArgs["RecordCounts"] = $counts }
        Write-HubExecutionEnd @fimArgs
    }
}

# --- BOOTSTRAP / PRE-FLIGHT ---

$pathsToCheck = @($pythonExe, $extractPy, $validatePy)

# Housekeeping: Limpa arquivos temporários órfãos com mais de 24h

Get-ChildItem -Path $ScriptDir -Filter ".data_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue

Get-ChildItem -Path $ScriptDir -Filter ".payload_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue

Write-HubExecutionStart -Message "INICIO — $AutomationName (MT-02). ExecId=$ExecId"
Start-HubStep -Step "preflight" -Message "Python, Oracle e paths"

$preFlightOk = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths $pathsToCheck
Complete-HubStep -Ok $preFlightOk

if (-not $preFlightOk) {

    Write-Log "FALHA NO PRE-FLIGHT (Python/Oracle/Paths). Abortando execução." -Lvl "ERRO"
    Write-Fim 9 "FALHA NO PRE-FLIGHT (Python/Oracle/Paths)."
    exit 9

}

Start-HubStep -Step "lock" -Message "Adquirindo lock global"
Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile
Complete-HubStep

$execStatus = "ERROR"
$emailChannelFailed = $false

try {

    Import-HubEnv

    $dataFile = Join-Path $ScriptDir ".data_$ExecId.json"

    if (Test-Path $dataFile) { Remove-Item $dataFile -Force }

    # 1. Extração Nativa (Pure-Python via Oracle)
    Start-HubStep -Step "extract" -Message "Extração nativa direta do Oracle"

    $extractResult = Invoke-OraclePythonScript -PythonExe $pythonExe -ScriptPath $extractPy `
        -ExecId $ExecId -LogPath $LogFile -Step "extract" `
        -OperationName "Extracao Oracle (extract_oracle.py)" `
        -MaxAttempts 3 -BackoffSeconds @(30, 60, 120)
    Complete-HubStep -Ok $extractResult.Success

    if (-not $extractResult.Success) {
        throw "Falha definitiva na extracao nativa apos 3 tentativas."
    }

    if (-not (Test-Path $dataFile)) {
        throw "Extracao concluiu mas arquivo de dados nao foi gerado: $dataFile"
    }

    $fileSize = (Get-Item $dataFile).Length

    try {
        $extractedData = Get-Content $dataFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch [System.Exception] {
        throw "Arquivo de dados $dataFile gerado mas contem JSON invalido (Tamanho: $fileSize bytes): $_"
    }

    # Lista vazia ([]) e um resultado de negocio valido (0 divergencias) e nao um erro de extracao.
    $extractedCount = if ($null -eq $extractedData) { 0 } else { @($extractedData).Count }

    Write-Log "Dados extraídos com sucesso ($( [math]::round($fileSize/1kb, 2) ) KB, $extractedCount registro(s))."

    # 2. Validação e HTML
    Start-HubStep -Step "transform" -Message "Validando dados e gerando notificação"
    $payloadFile = Join-Path $ScriptDir ".payload_$ExecId.json"
    if (Test-Path $payloadFile) { Remove-Item $payloadFile -Force }

    $validateResult = Invoke-OraclePythonScript -PythonExe $pythonExe -ScriptPath $validatePy `
        -ExecId $ExecId -LogPath $LogFile -Step "transform" `
        -OperationName "Validacao e Geracao HTML (validate_and_generate_html.py)" `
        -MaxAttempts 2 -BackoffSeconds @(15, 30)
    Complete-HubStep -Ok $validateResult.Success

    if (-not $validateResult.Success) { throw "Falha definitiva na validacao Python apos 2 tentativas." }

    # 3. Envio do E-mail (Se houver payload)

    if (Test-Path $payloadFile) {
        Start-HubStep -Step "dispatch" -Message "Envio de e-mail via Outlook"

        $jsonOutput = Get-Content $payloadFile -Raw -Encoding UTF8

        $payload = $jsonOutput | ConvertFrom-Json

        $subject = $payload.subject

        $htmlOutput = $payload.html
        $tipoNotif = [string]$payload.tipo_notificacao
        $totalLinhas = [int]$payload.total_linhas
        $totalErros = [int]$payload.total_erros
        $totalPecasNfIncorreta = [int]$payload.total_pecas_nf_incorreta
        $novos = [int]$payload.novos
        $novosPecasNfIncorreta = [int]$payload.novos_pecas_nf_incorreta
        $corrigidos = [int]$payload.corrigidos
        $corrigidosPecasNfIncorreta = [int]$payload.corrigidos_pecas_nf_incorreta
        $permanentes = [int]$payload.permanentes
        $permanentesPecasNfIncorreta = [int]$payload.permanentes_pecas_nf_incorreta

        Write-Log "Notificação gerada: $subject" -Step "dispatch"
        Write-Log "Resumo seguro payload => tipo=$tipoNotif; total_linhas=$totalLinhas; total_erros=$totalErros; total_pecas_nf_incorreta=$totalPecasNfIncorreta; novos=$novos; novos_pecas_nf_incorreta=$novosPecasNfIncorreta; corrigidos=$corrigidos; corrigidos_pecas_nf_incorreta=$corrigidosPecasNfIncorreta; permanentes=$permanentes; permanentes_pecas_nf_incorreta=$permanentesPecasNfIncorreta" -Step "dispatch"

        $script:fimCounts = @{
            read      = $totalLinhas
            errors    = $totalErros
            new       = $novos
            fixed     = $corrigidos
            permanent = $permanentes
        }

        # Idempotência Granular (ADR-013)

        $currentHash = [BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($jsonOutput))).Replace("-", "")

        $DeliveryStatePath = Join-Path $ScriptDir "delivery_state.json"

        $deliveryState = Read-DeliveryState -Path $DeliveryStatePath -Channels @("email") -OnWarning {
            param($mensagem)
            Write-Log $mensagem -Lvl "WARN"
        }

        if (Update-DeliveryStateHash -State $deliveryState -CurrentHash $currentHash) {
            Write-Log "Mudança de conteúdo detectada. Resetando status de entrega."
        }

        $skipEmail = -not (Test-DeliveryPending -State $deliveryState -Channel "email")

        if ($skipEmail) {

            Write-Log "E-mail já enviado para este conteúdo (Hash Match). Suprimindo."

            $sent = $true

        } else {

            # Carregar Configurações Oficiais (config.json)

            $configFile = Join-Path $ScriptDir "config.json"

            $config = if (Test-Path $configFile) { Get-Content $configFile -Raw | ConvertFrom-Json } else { $null }

            # Destinatarios: .env (MT_EMAIL_TO/CC) tem prioridade; config.json e apenas fallback/placeholder.
            $officialTo = if (-not [string]::IsNullOrWhiteSpace($env:MT_EMAIL_TO)) { $env:MT_EMAIL_TO } elseif ($config -and $config.email -and $config.email.to) { $config.email.to } else { $env:AUTOMACAO_ALERT_EMAIL }

            $officialCc = if (-not [string]::IsNullOrWhiteSpace($env:MT_EMAIL_CC)) { $env:MT_EMAIL_CC } elseif ($config -and $config.email -and $config.email.cc) { $config.email.cc } else { "" }

            # Verificar Modo Teste (Hierarquia: Orquestrador > VS Code)

            $globalTestEmail = [Environment]::GetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", "User")

            $isTestMode = $false

            if ($env:ORCHESTRATOR_TEST_MODE -eq "true") {

                $isTestMode = $true

            } elseif ($env:ORCHESTRATOR_TEST_MODE -eq "false") {

                $isTestMode = $false

            } else {

                if ((-not [string]::IsNullOrWhiteSpace($EmailToTest)) -or (-not [string]::IsNullOrWhiteSpace($globalTestEmail))) {

                    $isTestMode = $true

                }

            }

            if ($isTestMode) {

                $testTarget = if (-not [string]::IsNullOrWhiteSpace($EmailToTest)) { $EmailToTest } else { $globalTestEmail }

                $finalTo = if (-not [string]::IsNullOrWhiteSpace($testTarget)) { $testTarget } else { $env:AUTOMACAO_ALERT_EMAIL }

                Write-Log "MODO TESTE ATIVO: Redirecionando para $finalTo" -Lvl "WARN"

                $sent = Send-OutlookEmail -To $finalTo -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile -PreviewOnly:([bool]$EmailPreviewOnly)

            } else {

                Write-Log "MODO OFICIAL ATIVO (config.json): Disparando para $officialTo"

                $sent = Send-OutlookEmail -To $officialTo -Cc $officialCc -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile -PreviewOnly:([bool]$EmailPreviewOnly)

            }

            if ($sent) {

                Write-Log "E-mail enviado com sucesso. Consolidando estado parcial (E-mail)."

                Set-DeliverySuccess -State $deliveryState -Channel "email"

                Save-DeliveryState -State $deliveryState -Path $DeliveryStatePath

            }

        }

        if ($sent) {

            Write-Log "Confirmando compromisso de estado (Commit Success)..."

            if (Test-Path $CacheTmp) {

                Move-Item -Path $CacheTmp -Destination $CacheFile -Force

                Write-Log "Cache de erros consolidado: $CacheFile"

            }

        } else {

            Write-Log "Falha no envio de e-mail. O cache NÃO será atualizado para garantir retentativa." -Lvl "WARN"

            $emailChannelFailed = $true

        }

        Remove-Item $payloadFile -Force

        if (Test-Path $dataFile) { Remove-Item $dataFile -Force }

        Complete-HubStep -Ok (-not $emailChannelFailed)

    } else {

        Write-Log "Nenhuma divergência ou mudança de estado. Nenhuma notificação enviada."

    }

    if ($emailChannelFailed) {

        $execStatus = "ERROR"
        Write-Fim 25 "Execucao concluida com falha parcial no canal E-mail."

    } else {

        $execStatus = "SUCCESS"
        Write-Fim 0 "Execucao concluida com sucesso."

    }

} catch [System.Exception] {

    Write-Log "ERRO FATAL NA EXECUÇÃO NATIVA: $_" -Lvl "ERRO"
    Write-Fim 1 "ERRO FATAL NA EXECUCAO NATIVA: $_"
    exit 1

} finally {

    if ($ExecId) {

        $tempPatterns = ".data_$ExecId.json", ".payload_$ExecId.json"

        foreach ($p in $tempPatterns) {

            $f = Join-Path $ScriptDir $p

            if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }

        }

    }

    if (Test-Path $CacheTmp) { Remove-Item $CacheTmp -Force -ErrorAction SilentlyContinue }

    if (Get-Command Close-ExecutionTelemetry -ErrorAction SilentlyContinue) {

        Close-ExecutionTelemetry -ExecId $ExecId -Status $execStatus -LogPath $LogFile

    }

    Write-Log "FIM - Processo finalizado."

    Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile

}

if ($emailChannelFailed) {

    exit 25

}

<#

## Gestão de Contexto (AI-Native) - Atualizado em 13/05/2026

- Estado: Estabilizado v2.1.1 (Saneamento de Espaços e Encoding).

- Governança: Sincronia total v5.4.3 Gold Standard.

#>

