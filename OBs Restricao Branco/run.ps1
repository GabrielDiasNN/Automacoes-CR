<#
.SYNOPSIS
    Orquestrador VALEG — OBs Restrição Branco (ORB-07).
.DESCRIPTION
    1. Pre-Flight: Oracle disponivel, Python presente, WhatsApp configurado.
    2. Extracao + validacao: extract_orb.py grava orb_result.json (exit 2 = nada a notificar).
    3. Mensagem: format_message.py gera message.txt (exit 2 = nenhuma OB).
    4. WhatsApp: envia o texto ao grupo Expedicao Tinturaria (whatsapp-config.json).
    5. Commit da idempotencia: orb_state.json.tmp -> orb_state.json somente apos envio OK.

    Automacao PILOTO do padrao de logging estruturado (docs/logging-standard.md):
    emite eventos JSON (execution.start/end, step.start/end, retry.attempt) em
    stdout e no .jsonl. Exporta HUB_LOG_STRUCTURED/HUB_* para os processos filhos.
.NOTES
    Version: 1.1.0
    Skill: protocolo-valeg, ai-native-development-standard
    O agendamento (a cada 120 min) NAO esta aqui: vem do campo "schedule" do
    automation.manifest.json, consumido pelo APScheduler do Orchestrator central.
#>

[CmdletBinding()]
param([string]$ExecId = "")

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$projectRoot    = Split-Path -Parent $ScriptDir
$pythonExe      = Join-Path $projectRoot ".venv\Scripts\python.exe"
$ExtractScript  = Join-Path $ScriptDir "extract_orb.py"
$FormatScript   = Join-Path $ScriptDir "format_message.py"
$MessageFile    = Join-Path $ScriptDir "message.txt"
$ResultFile     = Join-Path $ScriptDir "orb_result.json"
$WaConfigPath   = Join-Path $ScriptDir "whatsapp-config.json"
$StateFile      = Join-Path $ScriptDir "orb_state.json"
$StateTmp       = $StateFile + ".tmp"
$LogDir         = Join-Path $ScriptDir "Logs"

$libLogging  = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libLogEvent = Join-Path $projectRoot "lib\Lib-LogEvent.psm1"
$libRetry    = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libProcess  = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig   = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libOracle   = Join-Path $projectRoot "lib\Lib-Oracle.psm1"

Import-Module $libLogging  -Force
Import-Module $libLogEvent -Force
Import-Module $libRetry    -Force
Import-Module $libProcess  -Force
Import-Module $libConfig   -Force
Import-Module $libOracle   -Force

$AutomationName = "OBs Restrição Branco"

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Register-ExecutionTelemetry -AutomationName $AutomationName
    } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}

$LogFile = Get-AutomacaoLogPath -Slug "Orb" -LogDir $LogDir

# --- CONTEXTO DE LOG ESTRUTURADO ---
$TraceId = Resolve-HubTraceId -Slug "orb"
Initialize-HubLogContext -Automation $AutomationName -ExecId $ExecId -TraceId $TraceId `
    -LogPath $LogFile -Component "ps_script"

# Processos filhos (Python/Node) herdam o padrao e a correlacao.
$env:HUB_LOG_STRUCTURED = "1"
$env:HUB_AUTOMATION     = $AutomationName
$env:HUB_EXEC_ID        = $ExecId
$env:HUB_TRACE_ID       = $TraceId

$script:RunSw = [System.Diagnostics.Stopwatch]::StartNew()
$script:StepSw = $null

# orb_result.json so deve existir se ESTA execucao o escreveu (contadores frescos
# no execution.end). Remove qualquer residuo do ciclo anterior.
Remove-Item $ResultFile -Force -ErrorAction SilentlyContinue

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO", [string]$Step = "")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile -Step $Step
}

function Start-Step {
    param(
        [ValidateSet("preflight", "lock", "extract", "transform", "dispatch", "commit", "cleanup")]
        [string]$Step,
        [string]$Msg = ""
    )
    $script:StepSw = [System.Diagnostics.Stopwatch]::StartNew()
    $env:HUB_STEP = $Step
    Write-HubStepStart -Step $Step -Message $Msg
}

function Complete-Step {
    param(
        [ValidateSet("preflight", "lock", "extract", "transform", "dispatch", "commit", "cleanup")]
        [string]$Step,
        [bool]$Ok = $true,
        [string]$Msg = ""
    )
    $ms = if ($script:StepSw) { [int]$script:StepSw.Elapsed.TotalMilliseconds } else { 0 }
    Write-HubStepEnd -Step $Step -Ok $Ok -DurationMs $ms -Message $Msg
    $env:HUB_STEP = ""
}

# Codes que NAO representam falha operacional (mesmo padrao de Receitas
# Bloqueadas/run.ps1 para lock=40/cooldown=23 do motor WhatsApp): canal
# pendente e reavaliado no proximo ciclo, sem abrir incidente. 22 = pendencia
# de canal (WhatsApp lock/cooldown) sinalizada por este script.
$NonFailureCodes = @(0, 2, 22)

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")

    $counts = $null
    if (Test-Path $ResultFile) {
        try {
            $rc = (Get-Content $ResultFile -Raw -Encoding UTF8 | ConvertFrom-Json).record_counts
            if ($rc) {
                $counts = @{}
                foreach ($p in $rc.PSObject.Properties) { $counts[$p.Name] = [int]$p.Value }
            }
        } catch [System.Exception] {
            Write-Log "Aviso: falha ao ler record_counts de orb_result.json: $_" -Lvl "WARN"
        }
    }
    $dur = [int]$script:RunSw.Elapsed.TotalMilliseconds

    Exit-AutomationWithCode -Code $Code -Msg $Msg -ExecId $ExecId -LogPath $LogFile `
        -NonFailureCodes $NonFailureCodes -EndMessage "FIM - ExitCode=$Code" `
        -RecordCounts $counts -DurationMs $dur
}

Write-HubExecutionStart -Message "INICIO — $AutomationName (ORB-07). ExecId=$ExecId"

# --- PRE-FLIGHT ---
Start-Step -Step "preflight" -Msg "Oracle, Python e WhatsApp configurados"
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile `
    -CheckOracle -CheckPaths @($pythonExe, $ExtractScript, $FormatScript, $WaConfigPath)
Complete-Step -Step "preflight" -Ok $preFlight
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando."
}

try {
    # --- LOCK ---
    Start-Step -Step "lock" -Msg "Adquirindo lock global"
    Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile
    Complete-Step -Step "lock"

    try {
        try { Import-HubEnv } catch [System.Exception] { Write-Log "Aviso: falha ao carregar .env: $_" -Lvl "WARN" }

        # --- CLEANUP CIRURGICO: Chrome zumbis do motor WhatsApp (somente user-data-dir do projeto) ---
        $waAuthDir = (Get-WhatsAppAuthPath).ToLower()
        $chromeZombies = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($waAuthDir) }
        if ($chromeZombies) {
            Write-Log "Limpando $(@($chromeZombies).Count) processo(s) Chrome zumbi do motor WhatsApp..." -Step "cleanup"
            foreach ($proc in $chromeZombies) {
                try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop } catch [System.Exception] {
                    Write-Log "Aviso: nao foi possivel encerrar Chrome PID=$($proc.ProcessId): $_" -Lvl "WARN" -Step "cleanup"
                }
            }
        }

        # --- ETAPA 1: EXTRACAO + VALIDACAO ORACLE ---
        Start-Step -Step "extract" -Msg "Extracao Oracle + validacao de estoque"
        $pyResult = Invoke-OraclePythonScript `
            -PythonExe $pythonExe `
            -ScriptPath $ExtractScript `
            -ExecId $ExecId `
            -LogPath $LogFile `
            -OperationName "Extracao OBs Restrição Branco (extract_orb.py)" `
            -Step "extract" `
            -MaxAttempts 3 `
            -BackoffSeconds @(30, 60, 120)
        Complete-Step -Step "extract" -Ok ($pyResult.Success -or $pyResult.Idempotent)

        if ($pyResult.Idempotent) {
            if (Test-Path $StateTmp) {
                Move-Item $StateTmp $StateFile -Force
                Write-Log "State reconciliado sem necessidade de envio." -Step "commit"
            }
            Exit-WithCode 2 "Nenhuma OB nova com estoque suficiente — nada a notificar."
        }
        if (-not $pyResult.Success) {
            Exit-WithCode 3 "Falha definitiva na extracao Oracle apos 3 tentativas."
        }

        # --- ETAPA 2: MONTAGEM DA MENSAGEM ---
        Start-Step -Step "transform" -Msg "Gerando message.txt (format_message.py)"
        $fmtResult = Invoke-NativeProcess -FilePath $pythonExe `
            -Arguments "`"$FormatScript`" `"$ExecId`"" `
            -LogAction {
                param($msg, $lvl)
                if (-not [string]::IsNullOrWhiteSpace($msg)) {
                    Write-HubForwardedLine -Line $msg -FallbackLevel $lvl -Step "transform"
                }
            }
        Complete-Step -Step "transform" -Ok ($fmtResult.ExitCode -in @(0, 2))
        if ($fmtResult.ExitCode -eq 2) {
            Exit-WithCode 2 "Nenhuma OB qualificada — mensagem nao gerada."
        }
        if ($fmtResult.ExitCode -ne 0) {
            Exit-WithCode 4 "Falha em format_message.py. ExitCode=$($fmtResult.ExitCode)"
        }
        if (-not (Test-Path $MessageFile)) {
            Exit-WithCode 4 "message.txt nao foi gerado."
        }

        # --- ETAPA 3: ENVIO WHATSAPP ---
        # O destino real vem de OFST_WHATSAPP_TARGET (.env), compartilhado de
        # forma intencional com a OFST-06 por ser o mesmo grupo da Expedicao.
        # Send-WhatsApp.ps1 via target.contactIdEnv — nunca do config versionado.
        Start-Step -Step "dispatch" -Msg "Enviando ao grupo Expedicao Tinturaria"

        $SendWhatsAppScript = Join-Path $projectRoot "lib\Send-WhatsApp.ps1"
        $waArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -ConfigPath `"$WaConfigPath`" -LogFile `"$LogFile`""

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
        Complete-Step -Step "dispatch" -Ok ($waExit -eq 0)

        if ($waExit -eq 21) {
            Exit-WithCode 21 "WhatsApp requer reautenticacao."
        }
        if ($waExit -eq 40 -or $waExit -eq 23) {
            # Lock/cooldown do motor WhatsApp: comportamento normal (sessao
            # hub-global compartilhada com OBP-04/RB-01), nao um erro
            # operacional. State NAO commitado — mesma OB e reavaliada no
            # proximo ciclo agendado, sem gerar falso incidente.
            $motivo = if ($waExit -eq 40) { "lock ativo" } else { "cooldown" }
            Exit-WithCode 22 "WhatsApp pendente por $motivo (comportamento normal). State NAO commitado — as OBs serao reavaliadas na proxima execucao."
        }
        if ($waExit -ne 0) {
            Exit-WithCode 4 "Falha no envio WhatsApp (ExitCode=$waExit). State NAO commitado — as OBs serao reavaliadas na proxima execucao."
        }

        # --- COMMIT DA IDEMPOTENCIA (somente apos envio confirmado) ---
        Start-Step -Step "commit" -Msg "Commit da idempotencia"
        if (Test-Path $StateTmp) {
            Move-Item $StateTmp $StateFile -Force
            Write-Log "State de OBs notificadas commitado." -Step "commit"
        }
        Complete-Step -Step "commit"

        Exit-WithCode 0 "Execucao concluida com sucesso."

    } finally {
        if (Test-Path $StateTmp) {
            Remove-Item $StateTmp -Force -ErrorAction SilentlyContinue
            Write-Log "Limpeza finally: $StateTmp removido." -Lvl "DEBUG" -Step "cleanup"
        }
        Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile
    }

} catch [System.Exception] {
    Exit-WithCode 4 "Falha critica na orquestracao: $_"
}
