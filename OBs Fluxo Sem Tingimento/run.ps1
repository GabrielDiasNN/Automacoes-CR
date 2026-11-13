<#
.SYNOPSIS
    Orquestrador VALEG — OBs Fluxo Sem Tingimento (OFST-06).
.DESCRIPTION
    1. Pre-Flight: Oracle disponivel, Python presente, WhatsApp configurado.
    2. Extracao + validacao: extract_ofst.py grava ofst_result.json (exit 2 = nada a notificar).
    3. Mensagem: format_message.py gera card.png e legenda em message.txt (exit 2 = nenhuma OB).
    4. WhatsApp: envia card.png com legenda ao grupo Expedicao Tinturaria (whatsapp-config.json).
    5. Commit da idempotencia: ofst_state.json.tmp -> ofst_state.json apos envio OK
       ou no ramo idempotente (exit 2), em que nao ha' envio mas o state podado
       precisa ser persistido — OB que saiu da query some do state mesmo em ciclo
       sem OB nova. O unico caminho que NAO commita e' o de falha: extracao com
       linhas rejeitadas aborta sem tocar no state, preservando a idempotencia.

    Emite eventos de log estruturados (docs/logging-standard.md): execution.start/end,
    step.start/end, retry.attempt. Exporta HUB_LOG_STRUCTURED/HUB_* para os filhos.
.NOTES
    Version: 1.2.0
    Skill: protocolo-valeg, ai-native-development-standard
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
$ExtractScript = Join-Path $ScriptDir "extract_ofst.py"
$FormatScript = Join-Path $ScriptDir "format_message.py"
$MessageFile = Join-Path $ScriptDir "message.txt"
$CardFile = Join-Path $ScriptDir "card.png"
$CardsManifestFile = Join-Path $ScriptDir "cards_manifest.json"
$BatchInputFile = Join-Path $ScriptDir "batch_input.json"
$BatchResultFile = Join-Path $ScriptDir "batch_result.json"
$ResultFile = Join-Path $ScriptDir "ofst_result.json"
$WaConfigPath = Join-Path $ScriptDir "whatsapp-config.json"
$StateFile = Join-Path $ScriptDir "ofst_state.json"
$StateTmp = $StateFile + ".tmp"
$LogDir = Join-Path $ScriptDir "Logs"

$libLogging = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libLogEvent = Join-Path $projectRoot "lib\Lib-LogEvent.psm1"
$libRetry = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libProcess = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libOracle = Join-Path $projectRoot "lib\Lib-Oracle.psm1"
$libWaBatch = Join-Path $projectRoot "lib\Lib-WhatsAppBatch.psm1"

Import-Module $libLogging  -Force
Import-Module $libLogEvent -Force
Import-Module $libRetry    -Force
Import-Module $libProcess  -Force
Import-Module $libConfig   -Force
Import-Module $libOracle   -Force
Import-Module $libWaBatch  -Force

# O .venv nao e versionado e vive na raiz do repositorio principal: resolver
# so por $projectRoot quebra o pre-flight quando a automacao roda de um worktree.
$pythonExe = Resolve-HubPythonExe -ProjectRoot $projectRoot

$AutomationName = "OBs Fluxo Sem Tingimento"

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Register-ExecutionTelemetry -AutomationName $AutomationName
    }
    else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}

$LogFile = Get-AutomacaoLogPath -Slug "Ofst" -LogDir $LogDir

# --- CONTEXTO DE LOG ESTRUTURADO ---
$TraceId = Resolve-HubTraceId -Slug "ofst"
Initialize-HubLogContext -Automation $AutomationName -ExecId $ExecId -TraceId $TraceId `
    -LogPath $LogFile -Component "ps_script"

$env:HUB_LOG_STRUCTURED = "1"
$env:HUB_AUTOMATION = $AutomationName
$env:HUB_EXEC_ID = $ExecId
$env:HUB_TRACE_ID = $TraceId

$script:RunSw = [System.Diagnostics.Stopwatch]::StartNew()
$script:ExecutionEnded = $false
$script:HasFreshResult = $false
$waConfirmed = $false

# OBs Fluxo Sem Tingimento usa somente $ResultFile/$StateFile frescos dentro do lock.

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO", [string]$Step = "")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile -Step $Step
}

# Start-HubStep / Complete-HubStep vem de lib/Lib-LogEvent.psm1.

# Codes que nao representam falha operacional: 0 = envio OK, 2 = nada a notificar.
$NonFailureCodes = @(0, 2)

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    $script:ExecutionEnded = $true
    $countsPath = if ($script:HasFreshResult) { $ResultFile } else { "" }
    Exit-AutomationWithCode -Code $Code -Msg $Msg -ExecId $ExecId -LogPath $LogFile `
        -NonFailureCodes $NonFailureCodes -EndMessage "FIM - ExitCode=$Code" `
        -RecordCountsPath $countsPath -DurationMs ([int]$script:RunSw.Elapsed.TotalMilliseconds)
}

Write-HubExecutionStart -Message "INICIO — $AutomationName (OFST-06). ExecId=$ExecId"

try { Import-HubEnv } catch [System.Exception] { Write-Log "Aviso: falha ao carregar .env: $_" -Lvl "WARN" -Step "preflight" }

# --- PRE-FLIGHT ---
Start-HubStep -Step "preflight" -Message "Oracle, Python e WhatsApp configurados"
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile `
    -CheckOracle -CheckPaths @($pythonExe, $ExtractScript, $FormatScript, $WaConfigPath)
if ($preFlight) {
    try {
        $waConfig = Get-Content -LiteralPath $WaConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $null = Resolve-WhatsAppTarget -Target $waConfig.target -ConfigPath $WaConfigPath
    }
    catch [System.Exception] {
        Write-Log "Pre-Flight WhatsApp falhou: $_" -Lvl "ERROR" -Step "preflight"
        $preFlight = $false
    }
}
Complete-HubStep -Ok $preFlight
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando."
}

if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
    Invoke-LogRotation -LogPath $LogFile -KeepDays 15
}

try {
    # --- LOCK ---
    Start-HubStep -Step "lock" -Message "Adquirindo lock global"
    Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile -LockKey "OFST-06" | Out-Null
    Complete-HubStep

    try {
        # Limpa artefatos residuais antes da extracao ja protegido pelo lock.
        Remove-Item $ResultFile, $StateTmp, $MessageFile, $CardFile, $CardsManifestFile, $BatchInputFile, $BatchResultFile -Force -ErrorAction SilentlyContinue
        Get-ChildItem -LiteralPath $ScriptDir -Filter "card_*.png" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

        # --- ETAPA 1: EXTRACAO + VALIDACAO ORACLE ---
        Start-HubStep -Step "extract" -Message "Extracao Oracle + validacao de estoque"
        $pyResult = Invoke-OraclePythonScript `
            -PythonExe $pythonExe `
            -ScriptPath $ExtractScript `
            -ExecId $ExecId `
            -LogPath $LogFile `
            -OperationName "Extracao OBs Fluxo Sem Tingimento (extract_ofst.py)" `
            -Step "extract" `
            -MaxAttempts 3 `
            -BackoffSeconds @(30, 60, 120)
        $extractOk = ($pyResult.Success -or $pyResult.Idempotent)
        if ($extractOk) {
            $script:HasFreshResult = $true
        }
        Complete-HubStep -Ok $extractOk

        if ($pyResult.Idempotent) {
            if (Test-Path $StateTmp) {
                Start-HubStep -Step "commit" -Message "Reconciliando state sem envio"
                Move-Item $StateTmp $StateFile -Force
                Write-Log "State reconciliado sem necessidade de envio." -Step "commit"
                Complete-HubStep
            }
            Exit-WithCode 2 "Nenhuma OB nova com estoque suficiente — nada a notificar."
        }
        if (-not $pyResult.Success) {
            Exit-WithCode 3 "Falha definitiva na extracao Oracle apos 3 tentativas."
        }

        # --- ETAPA 2: MONTAGEM DO(S) CARD(S) E MANIFESTO ---
        Start-HubStep -Step "transform" -Message "Gerando card(s) PNG e cards_manifest.json (format_message.py)"
        $fmtResult = Invoke-NativeProcess -FilePath $pythonExe `
            -Arguments "`"$FormatScript`" `"$ExecId`"" `
            -WorkingDirectory $ScriptDir `
            -LogAction {
            param($msg, $lvl)
            if (-not [string]::IsNullOrWhiteSpace($msg)) {
                Write-HubForwardedLine -Line $msg -FallbackLevel $lvl -Step "transform"
            }
        }
        if ($fmtResult.ExitCode -eq 2) {
            Complete-HubStep -Ok $true
            Exit-WithCode 2 "Nenhuma OB qualificada — mensagem nao gerada."
        }
        if ($fmtResult.ExitCode -ne 0) {
            Complete-HubStep -Ok $false
            Exit-WithCode 4 "Falha em format_message.py. ExitCode=$($fmtResult.ExitCode)"
        }

        $manifestResult = Read-CardsManifest -ManifestPath $CardsManifestFile -BaseDir $ScriptDir -MessageFile $MessageFile -CardFile $CardFile
        Complete-HubStep -Ok $manifestResult.Valid
        if (-not $manifestResult.Valid) {
            Exit-WithCode 4 $manifestResult.Error
        }
        $cards = @($manifestResult.Cards)

        # --- ETAPA 3: ENVIO WHATSAPP ---
        # O destino real vem de OFST_WHATSAPP_TARGET (.env), resolvido dentro de
        # Send-WhatsApp.ps1 via target.contactIdEnv — nunca do config versionado.
        Start-HubStep -Step "dispatch" -Message "Enviando $($cards.Count) card(s) ao grupo Expedicao Tinturaria"

        if (-not (Test-WhatsAppConfigEnabled -Config $waConfig)) {
            Write-Log "Envio WhatsApp desabilitado na configuracao ($WaConfigPath). State NAO commitado." -Lvl "WARN" -Step "dispatch"
            Complete-HubStep -Ok $true
            Exit-WithCode 2 "Envio WhatsApp desabilitado na configuracao — nada enviado e state preservado."
        }

        $SendWhatsAppScript = Join-Path $projectRoot "lib\Send-WhatsApp.ps1"
        if ($cards.Count -eq 1) {
            $waArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -ConfigPath `"$WaConfigPath`" -LogFile `"$LogFile`""
        }
        else {
            Write-WhatsAppBatchInput -Cards $cards -BaseDir $ScriptDir -BatchInputFile $BatchInputFile
            $waArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -Mode BATCH -ConfigPath `"$WaConfigPath`" -BatchInputFile `"$BatchInputFile`" -BatchResultFile `"$BatchResultFile`" -LogFile `"$LogFile`""
        }

        $waResult = Invoke-NativeProcess -FilePath "powershell.exe" -Arguments $waArgs `
            -WorkingDirectory $ScriptDir `
            -LogAction {
            param($msg, $lvl)
            if (-not [string]::IsNullOrWhiteSpace($msg)) {
                Write-HubForwardedLine -Line $msg -FallbackLevel $lvl -Step "dispatch"
            }
        }

        $waExit = $waResult.ExitCode
        Write-Log "Motor WhatsApp ExitCode=$waExit" -Step "dispatch"

        if ($cards.Count -eq 1) {
            Complete-HubStep -Ok ($waExit -eq 0)
            if ($waExit -eq 21) {
                Exit-WithCode 21 "WhatsApp requer reautenticacao."
            }
            if ($waExit -ne 0) {
                Exit-WithCode 4 "Falha no envio WhatsApp (ExitCode=$waExit). State NAO commitado — as OBs serao reavaliadas na proxima execucao."
            }
        }
        else {
            $batchOutcome = Resolve-WhatsAppBatchDelivery -Cards $cards -BatchResultFile $BatchResultFile `
                -StateTmpPath $StateTmp -WaExitCode $waExit `
                -OnWarn { param($warnMsg) Write-Log $warnMsg -Lvl "WARN" -Step "dispatch" }
            Complete-HubStep -Ok ($batchOutcome.Status -eq "AllSent")

            if ($batchOutcome.Status -eq "PartialSent") {
                if (Test-Path $StateTmp) {
                    Start-HubStep -Step "commit" -Message "Commit parcial da idempotencia"
                    Move-Item $StateTmp $StateFile -Force
                    $waConfirmed = $true
                    Write-Log "State parcial commitado: $($batchOutcome.SentCount)/$($batchOutcome.TotalCount) pagina(s) entregue(s); $($batchOutcome.FailedObCount) OB(s) mantida(s) para reenvio." -Lvl "WARN" -Step "commit"
                    Complete-HubStep
                }
                try {
                    Update-WhatsAppResultRecordCounts -ResultPath $ResultFile `
                        -DeliveredObCount $batchOutcome.DeliveredObCount `
                        -SentPages $batchOutcome.SentCount `
                        -TotalPages $batchOutcome.TotalCount
                }
                catch [System.Exception] {
                    Write-Log "Aviso: falha ao ajustar record_counts parcial em ${ResultFile}: $_" -Lvl "WARN" -Step "dispatch"
                }
                if ($waExit -eq 21) {
                    Exit-WithCode 21 "WhatsApp requer reautenticacao apos envio parcial ($($batchOutcome.SentCount)/$($batchOutcome.TotalCount) paginas)."
                }
                Exit-WithCode 4 "Envio WhatsApp parcial ($($batchOutcome.SentCount)/$($batchOutcome.TotalCount) paginas entregues, ExitCode=$waExit). OBs das paginas com falha serao reavaliadas na proxima execucao."
            }

            if ($batchOutcome.Status -eq "NoneSent") {
                if ($waExit -eq 21) {
                    Exit-WithCode 21 "WhatsApp requer reautenticacao."
                }
                Exit-WithCode 4 "Falha no envio WhatsApp em lote (ExitCode=$waExit, 0/$($batchOutcome.TotalCount) paginas entregues). State NAO commitado — as OBs serao reavaliadas na proxima execucao."
            }
        }

        $waConfirmed = $true

        # --- COMMIT DA IDEMPOTENCIA (somente apos envio confirmado) ---
        Start-HubStep -Step "commit" -Message "Commit da idempotencia"
        if (Test-Path $StateTmp) {
            Move-Item $StateTmp $StateFile -Force
            Write-Log "State de OBs notificadas commitado." -Step "commit"
        }
        Complete-HubStep

        Exit-WithCode 0 "Execucao concluida com sucesso ($($cards.Count) card(s))."

    }
    finally {
        if (-not $waConfirmed -and (Test-Path $StateTmp)) {
            Remove-Item $StateTmp -Force -ErrorAction SilentlyContinue
            if (-not $script:ExecutionEnded) {
                Write-Log "Limpeza finally: $StateTmp removido." -Lvl "DEBUG" -Step "cleanup"
            }
        }
        Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile -LockKey "OFST-06"
    }

}
catch [System.Exception] {
    Exit-WithCode 4 "Falha critica na orquestracao: $_"
}
