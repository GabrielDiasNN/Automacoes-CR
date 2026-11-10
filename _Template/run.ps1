<#
.SYNOPSIS
    TEMPLATE: Orquestrador PowerShell (AI-Native / Soberano).
.DESCRIPTION
    Template oficial para novas automacoes. Mesmo esqueleto das automacoes de
    dominio (OFST-06, ORB-07, OBP-04, RB-01, RE-03, MT-02) e Protocolo V.A.L.E.G.:
    1. Validacao (Pre-Flight): diagnostico de saude do ambiente.
    2. Arquitetura: etapas nomeadas com Start-HubStep/Complete-HubStep e lock global.
    3. Logging: log estruturado com ExecId e TraceId.
    4. Escala e Governanca: idempotencia granular e Zero Trust (credenciais so no .env).

    Emite eventos de log estruturados (docs/logging-standard.md): execution.start/end,
    step.start/end, retry.attempt. Exporta HUB_LOG_STRUCTURED/HUB_* para os filhos.
.NOTES
    Version: 3.0.0
    Skill: protocolo-valeg, ai-native-development-standard
    Contract: pure-native-logic, structured-logging, preflight-v1, granular-idempotency
    O agendamento NAO esta aqui: vem do campo "schedule" do
    automation.manifest.json, consumido pelo APScheduler do Orchestrator central.
#>

[CmdletBinding()]
param([string]$ExecId = "")

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$projectRoot = Split-Path -Parent $ScriptDir
$ResultFile  = Join-Path $ScriptDir "result.json"
$LogDir      = Join-Path $ScriptDir "Logs"

$libLogging     = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libLogEvent    = Join-Path $projectRoot "lib\Lib-LogEvent.psm1"
$libEmail       = Join-Path $projectRoot "lib\Lib-Email.psm1"
$libRetry       = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libProcess     = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig      = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libIdempotency = Join-Path $projectRoot "lib\Lib-Idempotency.psm1"

Import-Module $libLogging     -Force
Import-Module $libLogEvent    -Force
Import-Module $libEmail       -Force
Import-Module $libRetry       -Force
Import-Module $libProcess     -Force
Import-Module $libConfig      -Force
Import-Module $libIdempotency -Force
# Lib-Oracle.psm1 so entra se a automacao consulta o Oracle (Invoke-OraclePythonScript).

# O .venv nao e versionado e vive na raiz do repositorio principal: resolver
# so por $projectRoot quebra o pre-flight quando a automacao roda de um worktree.
$pythonExe = Resolve-HubPythonExe -ProjectRoot $projectRoot

$AutomationName = "TEMPLATE_SLUG"

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Register-ExecutionTelemetry -AutomationName $AutomationName
    } elseif (Get-Command New-ExecId -ErrorAction SilentlyContinue) { New-ExecId } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}

$LogFile = Get-AutomacaoLogPath -Slug "TEMPLATE_SLUG" -LogDir $LogDir

# --- CONTEXTO DE LOG ESTRUTURADO (docs/logging-standard.md) ---
$TraceId = Resolve-HubTraceId -Slug "TEMPLATE_SLUG"
Initialize-HubLogContext -Automation $AutomationName -ExecId $ExecId -TraceId $TraceId `
    -LogPath $LogFile -Component "ps_script"

# Processos filhos (Python/Node) herdam o padrao e a correlacao.
$env:HUB_LOG_STRUCTURED = "1"
$env:HUB_AUTOMATION     = $AutomationName
$env:HUB_EXEC_ID        = $ExecId
$env:HUB_TRACE_ID       = $TraceId

$script:RunSw = [System.Diagnostics.Stopwatch]::StartNew()

# O arquivo de contadores so deve existir se ESTA execucao o escreveu.
Remove-Item $ResultFile -Force -ErrorAction SilentlyContinue

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO", [string]$Step = "")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile -Step $Step
}

# Start-HubStep / Complete-HubStep vem de lib/Lib-LogEvent.psm1.

# Codes que NAO representam falha operacional: 2 = idempotencia (nada a fazer).
$NonFailureCodes = @(0, 2)

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    Exit-AutomationWithCode -Code $Code -Msg $Msg -ExecId $ExecId -LogPath $LogFile `
        -NonFailureCodes $NonFailureCodes -EndMessage "FIM - ExitCode=$Code" `
        -RecordCountsPath $ResultFile -DurationMs ([int]$script:RunSw.Elapsed.TotalMilliseconds)
}

Write-HubExecutionStart -Message "INICIO — $AutomationName. ExecId=$ExecId"

# --- PRE-FLIGHT ---
Start-HubStep -Step "preflight" -Message "Python e paths"
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile -CheckPaths @($pythonExe)
Complete-HubStep -Ok $preFlight
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando."
}

try {
    # --- LOCK ---
    Start-HubStep -Step "lock" -Message "Adquirindo lock global"
    Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile | Out-Null
    Complete-HubStep

    try {
        try { Import-HubEnv } catch [System.Exception] { Write-Log "Aviso: falha ao carregar .env: $_" -Lvl "WARN" }

        # --- ETAPA 1: LOGICA DE NEGOCIO AQUI ---
        # Com Oracle: acrescente -CheckOracle ao pre-flight e use
        #   Invoke-OraclePythonScript -PythonExe $pythonExe -ScriptPath $ExtractScript `
        #       -ExecId $ExecId -LogPath $LogFile -OperationName "Extracao" -Step "extract" `
        #       -MaxAttempts 3 -BackoffSeconds @(30, 60, 120)
        # (exit 2 do script Python = idempotente: $result.Idempotent -> Exit-WithCode 2).
        Start-HubStep -Step "extract" -Message "Executando tarefas"
        Write-Log "Executando tarefas..." -Step "extract"
        Complete-HubStep

        # --- ETAPA 2: ENTREGA (exemplo: e-mail com idempotencia granular) ---
        # O modo teste (ORCHESTRATOR_TEST_MODE / AUTOMACAO_TEST_EMAIL) e aplicado
        # pelo proprio Send-OutlookEmail (lib/Lib-Email.psm1); nao reimplemente aqui.
        #
        # $StatePath = Join-Path $ScriptDir "state.json"; $StateTmp = $StatePath + ".tmp"
        # $DeliveryStatePath = Join-Path $ScriptDir "delivery_state.json"
        # $currentHash   = Get-LastContentHash -StateTmpPath $StateTmp -StatePath $StatePath
        # $deliveryState = Read-DeliveryState -Path $DeliveryStatePath -Channels @("email") -OnWarning {
        #     param($mensagem)
        #     Write-Log $mensagem -Lvl "WARN"
        # }
        # if (Update-DeliveryStateHash -State $deliveryState -CurrentHash $currentHash) {
        #     Write-Log "Novo hash ($currentHash). Resetando status de entrega." -Step "dispatch"
        # }
        # if (Test-DeliveryPending -State $deliveryState -Channel "email" -CurrentHash $currentHash) {
        #     $targetTo = if (-not [string]::IsNullOrWhiteSpace($env:NOVA_AUTOMACAO_EMAIL_TO)) { $env:NOVA_AUTOMACAO_EMAIL_TO } else { $env:AUTOMACAO_ALERT_EMAIL }
        #     $sent = Send-OutlookEmail -To $targetTo -Subject $subject -HtmlBody $html -ExecId $ExecId -LogPath $LogFile
        #     if (-not $sent) { Exit-WithCode 4 "Falha no envio do e-mail. State NAO commitado." }
        #     Set-DeliverySuccess -State $deliveryState -Channel "email"
        #     Save-DeliveryState -State $deliveryState -Path $DeliveryStatePath
        # }
        #
        # --- COMMIT DA IDEMPOTENCIA (somente apos a entrega confirmada) ---
        # if (Test-Path $StateTmp) { Move-Item $StateTmp $StatePath -Force }

        Exit-WithCode 0 "Execucao concluida com sucesso."

    } finally {
        # Liberacao do bloqueio global, independente de erro interno
        Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile
    }

} catch [System.Exception] {
    Exit-WithCode 4 "Falha critica na orquestracao: $_"
}
