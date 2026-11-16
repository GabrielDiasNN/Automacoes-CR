<#
.SYNOPSIS
    Orquestrador Nativo para Receitas Emitidas.
.DESCRIPTION
    Este script coordena a geracao do relatorio semanal de receitas emitidas (nao pesadas):
    1. Pre-Flight: Diagnostico de saude do ambiente (inclui validacao do Oracle Client local).
    2. Python (Extract): Busca dados no Oracle utilizando Query CTE Nativa.
    3. Python (HTML): Transforma JSON em relatorio adaptativo multipandonal.
    4. PowerShell: Entrega visual via Outlook.
    Cada etapa critica e executada com Invoke-WithRetry (VALEG: A-Arquitetura).

    Emite eventos de log estruturados (docs/logging-standard.md). Os filhos Python
    usam stdout como canal de dados (IPC stdio) e por isso NAO recebem
    HUB_LOG_STRUCTURED — seguem logando em stderr, encaminhado pelo run.ps1.
.NOTES
    Version: 2.8.1
    Skill: ai-native-development-standard, python-oracle-migration, protocolo-valeg
    Contract: ipc-stdio, structured-logging, retry-on-failure, granular-idempotency
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
$libLogging     = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libLogEvent    = Join-Path $projectRoot "lib\Lib-LogEvent.psm1"
$libEmail       = Join-Path $projectRoot "lib\Lib-Email.psm1"
$libRetry       = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libProcess     = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig      = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libOracle      = Join-Path $projectRoot "lib\Lib-Oracle.psm1"
$libIdempotency = Join-Path $projectRoot "lib\Lib-Idempotency.psm1"
$extractPy  = Join-Path $ScriptDir "extract_oracle.py"
$extractJs  = Join-Path $ScriptDir "extract_oracle.js"
$generatePy = Join-Path $ScriptDir "generate_html_report.py"
$configPath = Join-Path $ScriptDir "receitas_config.json"
$StatePath  = Join-Path $ScriptDir "receitas_state.json"
$StateTmp   = $StatePath + ".tmp"
$DeliveryStatePath = Join-Path $ScriptDir "delivery_state.json"
$ResultFile = Join-Path $ScriptDir "re_result.json"
$LogDir     = Join-Path $ScriptDir "Logs"

Import-Module $libLogging     -Force
Import-Module $libLogEvent    -Force
Import-Module $libEmail       -Force
Import-Module $libRetry       -Force
Import-Module $libProcess     -Force
Import-Module $libConfig      -Force
Import-Module $libOracle      -Force
Import-Module $libIdempotency -Force

# O .venv nao e versionado e vive na raiz do repositorio principal: resolver
# so por $projectRoot quebra o pre-flight quando a automacao roda de um worktree.
$pythonExe = Resolve-HubPythonExe -ProjectRoot $projectRoot
# Motor JS so com ORACLE_DRIVER_MODE=bridge (opt-in explicito); senao, Python.
$nodeExe   = if ("$env:ORACLE_DRIVER_MODE".Trim() -eq "bridge") { (Get-Command node -ErrorAction SilentlyContinue).Source } else { $null }

$AutomationName = "Receitas Emitidas"

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Register-ExecutionTelemetry -AutomationName $AutomationName
    } elseif (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}

$LogFile = Get-AutomacaoLogPath -Slug "ReceitasEmitidas" -LogDir $LogDir

# --- CONTEXTO DE LOG ESTRUTURADO (docs/logging-standard.md) ---
# extract_oracle.py e generate_html_report.py usam stdout como CANAL DE DADOS
# (IPC stdio), entao os processos filhos NAO recebem HUB_LOG_STRUCTURED — seguem
# logando em stderr (formato legado), que o run.ps1 encaminha. O run.ps1 em si
# emite o envelope estruturado.
$TraceId = Resolve-HubTraceId -Slug "re"
Initialize-HubLogContext -Automation $AutomationName -ExecId $ExecId -TraceId $TraceId `
    -LogPath $LogFile -Component "ps_script"
$env:HUB_AUTOMATION = $AutomationName
$env:HUB_EXEC_ID    = $ExecId
$env:HUB_TRACE_ID   = $TraceId

$script:RunSw = [System.Diagnostics.Stopwatch]::StartNew()
$script:HasFreshResult = $false

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO", [string]$Step = "")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile -Step $Step
}

# Codes que NAO representam falha operacional (apenas 0: esta automacao nao usa exit 2).
$NonFailureCodes = @(0)

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    $countsPath = if ($script:HasFreshResult) { $ResultFile } else { "" }
    Exit-AutomationWithCode -Code $Code -Msg $Msg -ExecId $ExecId -LogPath $LogFile `
        -NonFailureCodes $NonFailureCodes `
        -RecordCountsPath $countsPath -DurationMs ([int]$script:RunSw.Elapsed.TotalMilliseconds)
}

# --- BOOTSTRAP / PRE-FLIGHT ---
Import-HubEnv

Write-HubExecutionStart -Message "INICIO — $AutomationName (RE-03). ExecId=$ExecId"
Start-HubStep -Step "preflight" -Message "Oracle Client e ambiente (Oracle/Python/paths)"

$oracleClientLib = [System.Environment]::GetEnvironmentVariable("ORACLE_CLIENT_LIB_DIR", "Process")
$oracleClientFallback = [System.Environment]::GetEnvironmentVariable("ORACLE_CLIENT_PATH", "Process")
if ([string]::IsNullOrWhiteSpace($oracleClientLib)) { $oracleClientLib = $oracleClientFallback }
$oraClientPreFlightOk = $true
$driverMode = [System.Environment]::GetEnvironmentVariable("ORACLE_DRIVER_MODE", "Process")
if ([string]::IsNullOrWhiteSpace($driverMode)) { $driverMode = Get-EnvFileValue -Key "ORACLE_DRIVER_MODE" }
$driverModeNormalized = if ([string]::IsNullOrWhiteSpace($driverMode)) { "auto" } else { $driverMode.Trim().ToLowerInvariant() }

# So queue dispensa Oracle Client local. Os demais modos (thick, bridge e auto, padrao do
# .env.example) exigem oci.dll: em auto, sem cliente o fallback Thick falha na extracao com
# exit 3 em vez de falhar aqui com 9 no pre-flight. Nao ha modo "thin" valido
# (lib/python/oracle_client.py get_driver_mode); valor invalido tambem cai aqui.
if ($driverModeNormalized -ne "queue") {
    if ([string]::IsNullOrWhiteSpace($oracleClientLib)) {
        Write-Log "PRE-FLIGHT ERRO: ORACLE_CLIENT_LIB_DIR/ORACLE_CLIENT_PATH nao definido para modo '$driverModeNormalized'." -Lvl "ERRO" -Step "preflight"
        $oraClientPreFlightOk = $false
    } elseif (-not (Test-Path $oracleClientLib)) {
        Write-Log "PRE-FLIGHT ERRO: Oracle Client nao encontrado em '$oracleClientLib' para modo '$driverModeNormalized'." -Lvl "ERRO" -Step "preflight"
        $oraClientPreFlightOk = $false
    } else {
        $ociDll = Join-Path $oracleClientLib "oci.dll"
        if (-not (Test-Path $ociDll)) {
            Write-Log "PRE-FLIGHT ERRO: oci.dll ausente em '$oracleClientLib' para modo '$driverModeNormalized'." -Lvl "ERRO" -Step "preflight"
            $oraClientPreFlightOk = $false
        } else {
            Write-Log "PRE-FLIGHT OK: Oracle Client validado em '$oracleClientLib' (modo '$driverModeNormalized')." -Step "preflight"
        }
    }
} else {
    Write-Log "PRE-FLIGHT OK: Oracle Driver Mode '$driverModeNormalized' nao exige Oracle Client local." -Step "preflight"
}

$preFlight = $false
if ($oraClientPreFlightOk) {
    $preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckOracle -CheckPaths @($pythonExe, $extractPy, $generatePy, $configPath)
}
$preFlightAllOk = ($oraClientPreFlightOk -and $preFlight)
Complete-HubStep -Ok $preFlightAllOk
if (-not $preFlightAllOk) {
    $pfCode = if (Get-Command Get-OraclePreFlightExitCode -ErrorAction SilentlyContinue) { Get-OraclePreFlightExitCode -OutrosChecks { Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckPaths @($pythonExe, $extractPy, $generatePy, $configPath) } } else { 9 }
    Exit-WithCode $pfCode "FALHA NO PRE-FLIGHT CHECK. Abortando execucao."
}

try {
    Start-HubStep -Step "lock" -Message "Adquirindo lock global"
    Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile -LockKey "RE-03" | Out-Null
    Complete-HubStep

    try {
        if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
            Invoke-LogRotation -LogPath $LogFile -KeepDays 15
        }
        Remove-Item $ResultFile -Force -ErrorAction SilentlyContinue
        # 1. Extracao de Dados
        $useJsExtractor = (Test-Path $extractJs) -and (-not [string]::IsNullOrWhiteSpace($nodeExe))
        $extractorExe   = if ($useJsExtractor) { $nodeExe } else { $pythonExe }
        $extractorPath  = if ($useJsExtractor) { $extractJs } else { $extractPy }
        $engineName     = if ($useJsExtractor) { "Node.js (Oracle OCI 19c)" } else { "Python (Direct Oracle CTE)" }

        Start-HubStep -Step "extract" -Message "Extraindo dados via $engineName"

        $extractResult = Invoke-OraclePythonScript -PythonExe $extractorExe -ScriptPath $extractorPath `
            -ExecId $ExecId -LogPath $LogFile -OperationName "Extracao Oracle" -Step "extract" `
            -StdoutIsData -MaxAttempts 3 -BackoffSeconds @(30, 60, 120)
        $extractOk = ($extractResult.Success -or $extractResult.Idempotent)
        if ($extractOk) {
            $script:HasFreshResult = $true
        }
        Complete-HubStep -Ok $extractOk

        if ($extractResult.Idempotent) {
            Write-Log "Extrator detectou que nao ha alteracoes relevantes (Idempotencia). Encerrando."
            Exit-WithCode 0 "Processo finalizado (Idempotencia Extrator)."
        }

        if (-not $extractResult.Success) {
            $extractExitCode = Resolve-OracleFailureExitCode -ExitCode $extractResult.ExitCode -DefaultExitCode 3
            $tentativasRealizadas = if ($extractResult.NonRetryable) { 1 } else { 3 }
            Send-AlertaFalhaDefinitiva -TaskName "Receitas Emitidas" -ExecId $ExecId -UltimoErro "Falha na extracao Oracle (PythonExit=$($extractResult.ExitCode))." -Tentativas $tentativasRealizadas -LogPath $LogFile
            Exit-WithCode $extractExitCode "Falha definitiva na extracao Oracle ($engineName) (PythonExit=$($extractResult.ExitCode))."
        }

        if ([string]::IsNullOrWhiteSpace($extractResult.Output)) { throw "Extracao retornou dados vazios." }

        # 2. Geracao do HTML
        Start-HubStep -Step "transform" -Message "Gerando HTML visual moderno"

        $htmlResult = Invoke-OraclePythonScript -PythonExe $pythonExe -ScriptPath $generatePy `
            -ExecId $ExecId -LogPath $LogFile -OperationName "Geracao HTML" -Step "transform" `
            -StdoutIsData -MaxAttempts 3 -BackoffSeconds @(10, 30, 60) -InputData $extractResult.Output

        Complete-HubStep -Ok $htmlResult.Success
        if (-not $htmlResult.Success) { throw "Falha definitiva na geracao do HTML." }
        if ([string]::IsNullOrWhiteSpace($htmlResult.Output)) { throw "Geracao HTML retornou conteudo vazio." }

        $htmlOutput = $htmlResult.Output

        # 3. Envio de E-mail
        Start-HubStep -Step "dispatch" -Message "E-mail oficial via Outlook COM"
        Write-Log "Verificando estado de notificacoes (Idempotencia Granular)..." -Step "dispatch"
        $currentHash = Get-LastContentHash -StateTmpPath $StateTmp -StatePath $StatePath

        $deliveryState = Read-DeliveryState -Path $DeliveryStatePath -Channels @("email") -OnWarning {
            param($mensagem)
            Write-Log $mensagem "WARN"
        }

        if (Update-DeliveryStateHash -State $deliveryState -CurrentHash $currentHash) {
            Write-Log "Novo Hash detectado ($currentHash). Resetando status de entrega." -Step "dispatch"
        }

        if (-not (Test-DeliveryPending -State $deliveryState -Channel "email" -CurrentHash $currentHash)) {
            Write-Log "Conteudo identico ao ultimo envio e ja entregue. Suprimindo." -Step "dispatch"
        } else {
            Write-Log "Enviando e-mail oficial via Outlook COM..." -Step "dispatch"
            $config = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $subject = "$($config.email.subject_prefix) - $(Get-Date -Format 'dd/MM/yyyy')"
            # Destinatario: .env (RE_EMAIL_TO) tem prioridade; config.json e apenas fallback/placeholder.
            $targetTo = if (-not [string]::IsNullOrWhiteSpace($env:RE_EMAIL_TO)) { $env:RE_EMAIL_TO } else { $config.email.to }
            $fullHtmlBody = "<p>$($config.email.intro_text)</p>$($htmlOutput)"

            $emailOk = Invoke-WithRetry -MaxAttempts 2 -BackoffSeconds @(15, 30) -OperationName "Envio E-mail Outlook" -Step "dispatch" -ExecId $ExecId -LogPath $LogFile -Action {
                $sent = Send-OutlookEmail -To $targetTo -Subject $subject -HtmlBody $fullHtmlBody -ExecId $ExecId -LogPath $LogFile
                if (-not $sent) { throw "Send-OutlookEmail retornou false." }
                return $true
            }

            if ($emailOk) {
                Write-Log "E-mail enviado com sucesso. Consolidando estado parcial." -Step "dispatch"
                Set-DeliverySuccess -State $deliveryState -Channel "email"
                Save-DeliveryState -State $deliveryState -Path $DeliveryStatePath
            } else { throw "Falha definitiva no envio do e-mail." }
        }
        Complete-HubStep -Ok $true

        Start-HubStep -Step "commit" -Message "Confirmando compromisso de estado"
        if (Test-Path $StateTmp) {
            Write-Log "Confirmando compromisso de estado (Commit Success)..." -Step "commit"
            Move-Item -Path $StateTmp -Destination $StatePath -Force
        }
        Complete-HubStep

        Exit-WithCode 0 "Processo concluido com sucesso."
    } finally {
        Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile -LockKey "RE-03"
    }
} catch [System.Exception] {
    Exit-WithCode 1 "ERRO FATAL: $_"
} finally {
    [System.GC]::Collect()
}
