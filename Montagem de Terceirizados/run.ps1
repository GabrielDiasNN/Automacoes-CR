<#

.SYNOPSIS

    Orquestrador Oficial para Montagem de Terceirizados (Pure-Native).

.DESCRIPTION

    Este script coordena o ciclo de vida da automação utilizando extração direta do Oracle via Python.

    Não utiliza mais dependências de Excel/VBA (Migração Concluída).

.NOTES

    Version: 2.2.0

    Skill: ai-native-development-standard, enterprise-local-automation-stack, automation-runtime-safety

    Contract: native-fetch-logic, ipc-file-payload, base64-bridge-logs, preflight-v1, granular-idempotency

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
$libEmail    = Join-Path $projectRoot "lib\Lib-Email.psm1"
$libProcess  = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig   = Join-Path $projectRoot "lib\Lib-Config.psm1"
$pythonExe   = Join-Path $projectRoot ".venv\Scripts\python.exe"

# Scripts

$extractPy  = Join-Path $ScriptDir "extract_oracle.py"

$validatePy = Join-Path $ScriptDir "validate_and_generate_html.py"

$CacheFile  = Join-Path $ScriptDir ".cache_erros.json"

$CacheTmp   = $CacheFile + ".tmp"

$LogDir     = Join-Path $ScriptDir "Logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

Import-Module $libLogging -Force

Import-Module $libEmail   -Force
Import-Module $libConfig  -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {

    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {

        Register-ExecutionTelemetry -AutomationName "Montagem de Terceirizados"

    } elseif (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }

}

$LogFile = Get-AutomacaoLogPath -Slug "Montagem_Terceirizados" -LogDir $LogDir

# Helper para Log (v5.4.0)

function Write-Log {

    param([string]$Msg, [string]$Lvl = "INFO")

    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile

}

# --- BOOTSTRAP / PRE-FLIGHT ---

$pathsToCheck = @($pythonExe, $extractPy, $validatePy)

# Housekeeping: Limpa arquivos temporários órfãos com mais de 24h

Get-ChildItem -Path $ScriptDir -Filter ".data_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue

Get-ChildItem -Path $ScriptDir -Filter ".payload_*.json" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } | Remove-Item -Force -ErrorAction SilentlyContinue

if (-not (Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths $pathsToCheck)) {

    Write-Log "FALHA NO PRE-FLIGHT (Python/Oracle/Paths). Abortando execução." -Lvl "ERRO"; exit 9

}

Write-Log "========================================================================================="

Write-Log "INÍCIO - Execução Montagem Terceirizados (Pure-Native). ExecId=$ExecId"
Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile

$execStatus = "ERROR"

try {

    Import-HubEnv

    $dataFile = Join-Path $ScriptDir ".data_$ExecId.json"

    if (Test-Path $dataFile) { Remove-Item $dataFile -Force }

    # 1. Extração Nativa (Pure-Python via Oracle)
    Write-Log "Fase 1: Executando extração nativa direta do Oracle..."
    Import-Module $libProcess -Force

    $res = Invoke-NativeProcess -FilePath $pythonExe -Arguments "`"$extractPy`" `"$ExecId`"" -LogAction {
        param($msg, $lvl)
        # Filtramos logs do motor Python que podem ser redundantes
        if ($lvl -ne "INFO" -or -not $msg.Contains("[DEBUG]")) {
            Write-Log $msg -Lvl $lvl
        }
    }

    if ($res.ExitCode -ne 0 -or -not (Test-Path $dataFile)) {
        throw "Falha crítica na extração nativa (ExitCode: $($res.ExitCode)). Arquivo de dados não encontrado."
    }

    $fileSize = (Get-Item $dataFile).Length

    if ($fileSize -lt 10) {

        throw "Arquivo de dados $dataFile gerado mas parece vazio ou corrompido (Tamanho: $fileSize bytes)."

    }

    Write-Log "Dados extraídos com sucesso ($( [math]::round($fileSize/1kb, 2) ) KB)."

    # 2. Validação e HTML
    Write-Log "Fase 2: Validando dados e gerando notificação..."
    $payloadFile = Join-Path $ScriptDir ".payload_$ExecId.json"
    if (Test-Path $payloadFile) { Remove-Item $payloadFile -Force }

    $resGen = Invoke-NativeProcess -FilePath $pythonExe -Arguments "`"$validatePy`" `"$ExecId`"" -LogAction {
        param($msg, $lvl)
        Write-Log $msg -Lvl $lvl
    }

    if ($resGen.ExitCode -ne 0) { throw "Falha na validação Python (ExitCode: $($resGen.ExitCode))." }

    # 3. Envio do E-mail (Se houver payload)

    if (Test-Path $payloadFile) {

        $jsonOutput = Get-Content $payloadFile -Raw -Encoding UTF8

        $payload = $jsonOutput | ConvertFrom-Json

        $subject = $payload.subject

        $htmlOutput = $payload.html

        Write-Log "Notificação gerada: $subject"

        # Idempotência Granular (ADR-013)

        $currentHash = [BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($jsonOutput))).Replace("-", "")

        $deliveryState = @{

            last_sent_hash = ""

            delivery_status = @{

                email = @{ success = $false; sent_at = $null }

            }

        }

        $DeliveryStatePath = Join-Path $ScriptDir "delivery_state.json"

        if (Test-Path $DeliveryStatePath) {

            try {

                $savedState = Get-Content $DeliveryStatePath -Raw -Encoding UTF8 | ConvertFrom-Json

                if ($savedState.last_sent_hash) { $deliveryState.last_sent_hash = $savedState.last_sent_hash }

                if ($null -ne $savedState.delivery_status -and $null -ne $savedState.delivery_status.email) {

                    $deliveryState.delivery_status.email.success = [bool]$savedState.delivery_status.email.success

                    $deliveryState.delivery_status.email.sent_at = $savedState.delivery_status.email.sent_at

                }

            } catch [System.Exception] { Write-Log "Aviso: Falha ao parsear delivery_state.json." -Lvl "WARN" }

        }

        if ($currentHash -ne $deliveryState.last_sent_hash) {

            Write-Log "Mudança de conteúdo detectada. Resetando status de entrega."

            $deliveryState.last_sent_hash = $currentHash

            $deliveryState.delivery_status.email.success = $false

        }

        $skipEmail = $deliveryState.delivery_status.email.success

        if ($skipEmail) {

            Write-Log "E-mail já enviado para este conteúdo (Hash Match). Suprimindo."

            $sent = $true

        } else {

            # Carregar Configurações Oficiais (config.json)

            $configFile = Join-Path $ScriptDir "config.json"

            $config = if (Test-Path $configFile) { Get-Content $configFile -Raw | ConvertFrom-Json } else { $null }

            $officialTo = if ($config -and $config.email -and $config.email.to) { $config.email.to } else { "gabriel.dias@costaricamalhas.ind.br" }

            $officialCc = if ($config -and $config.email -and $config.email.cc) { $config.email.cc } else { "" }

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

                $finalTo = if (-not [string]::IsNullOrWhiteSpace($testTarget)) { $testTarget } else { "gabriel.dias@costaricamalhas.ind.br" }

                Write-Log "MODO TESTE ATIVO: Redirecionando para $finalTo" -Lvl "WARN"

                $sent = Send-OutlookEmail -To $finalTo -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile -PreviewOnly:([bool]$EmailPreviewOnly)

            } else {

                Write-Log "MODO OFICIAL ATIVO (config.json): Disparando para $officialTo"

                $sent = Send-OutlookEmail -To $officialTo -Cc $officialCc -Subject $subject -HtmlBody $htmlOutput -ExecId $ExecId -LogPath $LogFile -PreviewOnly:([bool]$EmailPreviewOnly)

            }

            if ($sent) {

                Write-Log "E-mail enviado com sucesso. Consolidando estado parcial (E-mail)."

                $deliveryState.delivery_status.email.success = $true

                $deliveryState.delivery_status.email.sent_at = (Get-Date -Format 'dd/MM/yyyy HH:mm:ss')

                $deliveryState | ConvertTo-Json -Depth 5 | Out-File $DeliveryStatePath -Encoding UTF8

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

        }

        Remove-Item $payloadFile -Force

        if (Test-Path $dataFile) { Remove-Item $dataFile -Force }

    } else {

        Write-Log "Nenhuma divergência ou mudança de estado. Nenhuma notificação enviada."

    }

    $execStatus = "SUCCESS"

} catch [System.Exception] {

    Write-Log "ERRO FATAL NA EXECUÇÃO NATIVA: $_" -Lvl "ERRO"; exit 1

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

<#

## Gestão de Contexto (AI-Native) - Atualizado em 13/05/2026

- Estado: Estabilizado v2.1.1 (Saneamento de Espaços e Encoding).

- Governança: Sincronia total v5.4.3 Gold Standard.

#>

