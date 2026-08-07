<#
.SYNOPSIS
    Orquestrador VALEG — OBs Fluxo Sem Tingimento (OFST-06).
.DESCRIPTION
    1. Pre-Flight: Oracle disponivel, Python presente, WhatsApp configurado.
    2. Extracao + validacao: extract_ofst.py grava ofst_result.json (exit 2 = nada a notificar).
    3. Mensagem: format_message.py gera message.txt (exit 2 = nenhuma OB).
    4. WhatsApp: envia o texto ao grupo Expedicao Tinturaria (whatsapp-config.json).
    5. Commit da idempotencia: ofst_state.json.tmp -> ofst_state.json somente apos envio OK.
.NOTES
    Version: 1.0.0
    Skill: protocolo-valeg, ai-native-development-standard
    O agendamento (a cada 60 min) NAO esta aqui: vem do campo "schedule" do
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
$ExtractScript  = Join-Path $ScriptDir "extract_ofst.py"
$FormatScript   = Join-Path $ScriptDir "format_message.py"
$MessageFile    = Join-Path $ScriptDir "message.txt"
$WaConfigPath   = Join-Path $ScriptDir "whatsapp-config.json"
$StateFile      = Join-Path $ScriptDir "ofst_state.json"
$StateTmp       = $StateFile + ".tmp"
$LogDir         = Join-Path $ScriptDir "Logs"

$libLogging = Join-Path $projectRoot "lib\Lib-Logging.psm1"
$libRetry   = Join-Path $projectRoot "lib\Lib-Retry.psm1"
$libProcess = Join-Path $projectRoot "lib\Lib-Process.psm1"
$libConfig  = Join-Path $projectRoot "lib\Lib-Config.psm1"
$libOracle  = Join-Path $projectRoot "lib\Lib-Oracle.psm1"

Import-Module $libLogging -Force
Import-Module $libRetry   -Force
Import-Module $libProcess -Force
Import-Module $libConfig  -Force
Import-Module $libOracle  -Force

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    $ExecId = if (Get-Command Register-ExecutionTelemetry -ErrorAction SilentlyContinue) {
        Register-ExecutionTelemetry -AutomationName "OBs Fluxo Sem Tingimento"
    } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}

$LogFile = Get-AutomacaoLogPath -Slug "Ofst" -LogDir $LogDir

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
}

# Get-ForwardedLogLevel vem de lib/Lib-Logging.psm1 (achado A1).

# Codes que NAO representam falha operacional (mesmo padrao de Receitas
# Bloqueadas/run.ps1 para lock=40/cooldown=23 do motor WhatsApp): canal
# pendente e reavaliado no proximo ciclo, sem abrir incidente. 22 = pendencia
# de canal (WhatsApp lock/cooldown) sinalizada por este script.
$NonFailureCodes = @(0, 2, 22)

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    Exit-AutomationWithCode -Code $Code -Msg $Msg -ExecId $ExecId -LogPath $LogFile -NonFailureCodes $NonFailureCodes -EndMessage "FIM - ExitCode=$Code"
}

# --- PRE-FLIGHT ---
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile `
    -CheckOracle -CheckPaths @($pythonExe, $ExtractScript, $FormatScript, $WaConfigPath)
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando."
}

Write-Log "INICIO — OBs Fluxo Sem Tingimento (OFST-06). ExecId=$ExecId"

try {
    # --- LOCK ---
    Enter-AutomationLock -ExecId $ExecId -LogPath $LogFile

    try {
        try { Import-HubEnv } catch [System.Exception] { Write-Log "Aviso: falha ao carregar .env: $_" -Lvl "WARN" }

        # --- CLEANUP CIRURGICO: Chrome zumbis do motor WhatsApp (somente user-data-dir do projeto) ---
        $waAuthDir = (Get-WhatsAppAuthPath).ToLower()
        $chromeZombies = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($waAuthDir) }
        if ($chromeZombies) {
            Write-Log "Limpando $(@($chromeZombies).Count) processo(s) Chrome zumbi do motor WhatsApp..."
            foreach ($proc in $chromeZombies) {
                try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop } catch [System.Exception] {
                    Write-Log "Aviso: nao foi possivel encerrar Chrome PID=$($proc.ProcessId): $_" -Lvl "WARN"
                }
            }
        }

        # --- ETAPA 1: EXTRACAO + VALIDACAO ORACLE ---
        Write-Log "Etapa 1/3: Extracao Oracle + validacao de estoque..."
        $pyResult = Invoke-OraclePythonScript `
            -PythonExe $pythonExe `
            -ScriptPath $ExtractScript `
            -ExecId $ExecId `
            -LogPath $LogFile `
            -OperationName "Extracao OBs Fluxo Sem Tingimento (extract_ofst.py)" `
            -MaxAttempts 3 `
            -BackoffSeconds @(30, 60, 120)

        if ($pyResult.Idempotent) {
            Exit-WithCode 2 "Nenhuma OB nova com estoque suficiente — nada a notificar."
        }
        if (-not $pyResult.Success) {
            Exit-WithCode 3 "Falha definitiva na extracao Oracle apos 3 tentativas."
        }

        # --- ETAPA 2: MONTAGEM DA MENSAGEM ---
        Write-Log "Etapa 2/3: Gerando message.txt (format_message.py)..."
        $fmtResult = Invoke-NativeProcess -FilePath $pythonExe `
            -Arguments "`"$FormatScript`"" `
            -LogAction {
                param($msg, $lvl)
                if (-not [string]::IsNullOrWhiteSpace($msg)) {
                    Write-AutomacaoLog -Message $msg -Level (Get-ForwardedLogLevel -Msg $msg -Fallback $lvl) -ExecId $ExecId -LogPath $LogFile
                }
            }
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
        # O destino real vem de OFST_WHATSAPP_TARGET (.env), resolvido dentro de
        # Send-WhatsApp.ps1 via target.contactIdEnv — nunca do config versionado.
        Write-Log "Etapa 3/3: Enviando ao grupo Expedicao Tinturaria..."

        $SendWhatsAppScript = Join-Path $projectRoot "lib\Send-WhatsApp.ps1"
        $waArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -ConfigPath `"$WaConfigPath`" -LogFile `"$LogFile`""

        $waResult = Invoke-NativeProcess -FilePath "powershell.exe" -Arguments $waArgs `
            -WorkingDirectory $ScriptDir `
            -LogAction {
                param($msg, $lvl)
                if (-not [string]::IsNullOrWhiteSpace($msg)) {
                    Write-AutomacaoLog -Message $msg -Level (Get-ForwardedLogLevel -Msg $msg -Fallback $lvl) -ExecId $ExecId -LogPath $LogFile
                }
            }

        $waExit = $waResult.ExitCode
        Write-Log "Motor WhatsApp ExitCode=$waExit"

        if ($waExit -eq 21) {
            Exit-WithCode 21 "WhatsApp requer reautenticacao."
        }
        if ($waExit -eq 40 -or $waExit -eq 23) {
            # Lock/cooldown do motor WhatsApp: comportamento normal (sessao
            # hub-global compartilhada com OBP-04/RB-01), nao um erro
            # operacional. State NAO commitado — mesma OB e reavaliada no
            # proximo ciclo horario, sem gerar falso incidente.
            $motivo = if ($waExit -eq 40) { "lock ativo" } else { "cooldown" }
            Exit-WithCode 22 "WhatsApp pendente por $motivo (comportamento normal). State NAO commitado — as OBs serao reavaliadas na proxima execucao."
        }
        if ($waExit -ne 0) {
            Exit-WithCode 4 "Falha no envio WhatsApp (ExitCode=$waExit). State NAO commitado — as OBs serao reavaliadas na proxima execucao."
        }

        # --- COMMIT DA IDEMPOTENCIA (somente apos envio confirmado) ---
        if (Test-Path $StateTmp) {
            Move-Item $StateTmp $StateFile -Force
            Write-Log "State de OBs notificadas commitado."
        }

        Exit-WithCode 0 "Execucao concluida com sucesso."

    } finally {
        if (Test-Path $StateTmp) {
            Remove-Item $StateTmp -Force -ErrorAction SilentlyContinue
            Write-Log "Limpeza finally: $StateTmp removido." -Lvl "DEBUG"
        }
        Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile
    }

} catch [System.Exception] {
    Exit-WithCode 4 "Falha critica na orquestracao: $_"
}
