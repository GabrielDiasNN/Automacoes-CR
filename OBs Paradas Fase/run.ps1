<#
.SYNOPSIS
    Orquestrador VALEG — OBs Paradas na Fase (OBP-04).
.DESCRIPTION
    1. Pre-Flight: Oracle disponivel, Python presente, WhatsApp configurado.
    2. Extracao Oracle: extract_obs.py grava obs_result.json (exit 2 = idempotente).
    3. Geracao de Cards: generate_phase_cards.py gera images/*.png + phase_cards.json.
    4. Idempotencia por fase: compara hash e estado de entrega em delivery_state.json.
    5. WhatsApp: envia um card de imagem por fase ao grupo configurado em whatsapp-config.json.
.NOTES
    Version: 3.0.0
    Skill: protocolo-valeg, ai-native-development-standard
#>

[CmdletBinding()]
param([string]$ExecId = "")

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$projectRoot      = Split-Path -Parent $ScriptDir
$pythonExe        = Join-Path $projectRoot ".venv\Scripts\python.exe"
$ExtractScript    = Join-Path $ScriptDir "extract_obs.py"
$GenScript        = Join-Path $ScriptDir "generate_phase_cards.py"
$PhaseCardsFile   = Join-Path $ScriptDir "phase_cards.json"
$WaConfigPath     = Join-Path $ScriptDir "whatsapp-config.json"
$DeliveryState    = Join-Path $ScriptDir "delivery_state.json"
$ObsStateFile     = Join-Path $ScriptDir "obs_state.json"
$ObsStateTmp      = $ObsStateFile + ".tmp"
$LogDir           = Join-Path $ScriptDir "Logs"

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
        Register-ExecutionTelemetry -AutomationName "OBs Paradas Fase"
    } else { (Get-Date -Format 'yyyyMMdd_HHmmss') }
}

$LogFile = Get-AutomacaoLogPath -Slug "ObsParadasFase" -LogDir $LogDir

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
}

# Get-ForwardedLogLevel vem de lib/Lib-Logging.psm1 (achado A1).

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    Exit-AutomationWithCode -Code $Code -Msg $Msg -ExecId $ExecId -LogPath $LogFile -NonFailureCodes @(0, 2) -EndMessage "FIM - ExitCode=$Code"
}

# --- PRE-FLIGHT ---
$preFlight = Test-AutomationPreFlight -ExecId $ExecId -LogPath $LogFile `
    -CheckOracle -CheckPaths @($pythonExe, $ExtractScript, $GenScript, $WaConfigPath)
if (-not $preFlight) {
    Exit-WithCode 9 "FALHA NO PRE-FLIGHT CHECK. Abortando."
}

Write-Log "INICIO — OBs Paradas Fase (OBP-04). ExecId=$ExecId"

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

        # --- ETAPA 1: EXTRAÇÃO ORACLE ---
        Write-Log "Etapa 1/4: Extracao Oracle..."
        $pyResult = Invoke-OraclePythonScript `
            -PythonExe $pythonExe `
            -ScriptPath $ExtractScript `
            -ExecId $ExecId `
            -LogPath $LogFile `
            -OperationName "Extracao OBs Paradas (extract_obs.py)" `
            -MaxAttempts 3 `
            -BackoffSeconds @(30, 60, 120)

        if ($pyResult.Idempotent) {
            Write-Log "Sem alteracoes nas OBs (idempotencia). Encerrando."
            Exit-WithCode 2 "Idempotencia confirmada — nenhuma mudanca desde o ultimo envio."
        }
        if (-not $pyResult.Success) {
            Exit-WithCode 3 "Falha definitiva na extracao Oracle apos 3 tentativas."
        }

        # --- ETAPA 2: GERAR CARDS POR FASE ---
        Write-Log "Etapa 2/4: Gerando cards de imagem por fase (generate_phase_cards.py)..."
        $genResult = Invoke-NativeProcess -FilePath $pythonExe `
            -Arguments "`"$GenScript`"" `
            -LogAction {
                param($msg, $lvl)
                if (-not [string]::IsNullOrWhiteSpace($msg)) {
                    Write-AutomacaoLog -Message $msg -Level (Get-ForwardedLogLevel -Msg $msg -Fallback $lvl) -ExecId $ExecId -LogPath $LogFile
                }
            }
        if ($genResult.ExitCode -eq 2) {
            Exit-WithCode 2 "Nenhuma OB qualificada — nenhum card gerado."
        }
        if ($genResult.ExitCode -ne 0) {
            Exit-WithCode 4 "Falha em generate_phase_cards.py. ExitCode=$($genResult.ExitCode)"
        }
        if (-not (Test-Path $PhaseCardsFile)) {
            Exit-WithCode 4 "phase_cards.json nao foi gerado."
        }

        [array]$cards = Get-Content $PhaseCardsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $cards -or $cards.Count -eq 0) {
            Exit-WithCode 2 "phase_cards.json vazio — nenhuma fase para enviar."
        }

        # --- IDEMPOTÊNCIA DE ENTREGA (por fase) ---
        $currentHash = ""
        if (Test-Path $ObsStateTmp) {
            try { $currentHash = (Get-Content $ObsStateTmp -Raw | ConvertFrom-Json).last_hash } catch [System.Exception] {}
        }

        $state = @{ last_sent_hash = ""; phases = @() }
        if (Test-Path $DeliveryState) {
            try {
                $saved = Get-Content $DeliveryState -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($saved.last_sent_hash) { $state.last_sent_hash = $saved.last_sent_hash }
                if ($saved.phases) { $state.phases = @($saved.phases) }
            } catch [System.Exception] { Write-Log "Aviso: falha ao ler delivery_state.json. Reiniciando estado." -Lvl "WARN" }
        }

        if ($currentHash -and $currentHash -ne $state.last_sent_hash) {
            Write-Log "Novo hash ($currentHash) — resetando estado de entrega por fase."
            $state.last_sent_hash = $currentHash
            $state.phases = @()
        }

        $allAlreadySent = $cards.Count -gt 0 -and (
            ($state.phases | Where-Object { $_.success }).Count -eq $cards.Count
        )
        if ($allAlreadySent) {
            Write-Log "Todas as fases ja entregues para este lote. Idempotencia confirmada."
            if (Test-Path $ObsStateTmp) { Move-Item $ObsStateTmp $ObsStateFile -Force }
            Exit-WithCode 2 "Entrega ja realizada — nenhum novo envio necessario."
        }

        # --- ETAPA 3: ENVIO EM LOTE (uma sessão Chrome para todas as fases) ---
        # Filtrar fases ainda nao entregues
        $pendentes = @($cards | Where-Object {
            $key = $_.phase_key
            -not ($state.phases | Where-Object { $_.key -eq $key -and $_.success })
        })

        if ($pendentes.Count -eq 0) {
            Write-Log "Todas as fases ja entregues para este lote. Idempotencia confirmada."
            if (Test-Path $ObsStateTmp) { Move-Item $ObsStateTmp $ObsStateFile -Force }
            Exit-WithCode 2 "Entrega ja realizada — nenhum novo envio necessario."
        }

        Write-Log "Etapa 3/4: Enviando $($pendentes.Count) fases em lote (sessao unica)..."

        # Preparar lote: caminhos absolutos para o motor Node.js
        $batchInput = $pendentes | ForEach-Object {
            if (-not $_.image_path) {
                Exit-WithCode 4 "Card '$($_.phase_key)' sem image_path — phase_cards.json corrompido."
            }
            @{
                phase_key  = $_.phase_key
                image_path = (Join-Path $ScriptDir $_.image_path.Replace("/", "\"))
                caption    = $_.caption
            }
        }

        $BatchInputFile  = Join-Path $ScriptDir "batch_input.json"
        $BatchResultFile = Join-Path $ScriptDir "batch_result.json"
        $utf8NoBOM = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($BatchInputFile, ($batchInput | ConvertTo-Json -Depth 5), $utf8NoBOM)

        # Ler chatId: .env (OBP_WHATSAPP_TARGET) tem prioridade; config.json e apenas fallback/placeholder.
        $waCfg = Get-Content $WaConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $chatId = if (-not [string]::IsNullOrWhiteSpace($env:OBP_WHATSAPP_TARGET)) { $env:OBP_WHATSAPP_TARGET } else { $waCfg.target.contactId }
        $clientId = if ($waCfg.auth.clientId) { $waCfg.auth.clientId } else { "hub-global" }

        $SendWhatsAppScript = Join-Path $projectRoot "lib\Send-WhatsApp.ps1"
        $waArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -Mode BATCH -ClientId `"$clientId`" -Phone `"$chatId`" -BatchInputFile `"$BatchInputFile`" -BatchResultFile `"$BatchResultFile`" -LogFile `"$LogFile`""

        $waResult = Invoke-NativeProcess -FilePath "powershell.exe" -Arguments $waArgs `
            -WorkingDirectory $ScriptDir `
            -LogAction {
                param($msg, $lvl)
                if (-not [string]::IsNullOrWhiteSpace($msg)) {
                    Write-AutomacaoLog -Message $msg -Level (Get-ForwardedLogLevel -Msg $msg -Fallback $lvl) -ExecId $ExecId -LogPath $LogFile
                }
            }

        $waExit = $waResult.ExitCode
        Write-Log "Motor WhatsApp Batch ExitCode=$waExit"

        if ($waExit -eq 21) {
            Exit-WithCode 21 "WhatsApp requer reautenticacao."
        }

        # Parsear resultados por fase
        $batchResults = @()
        if (Test-Path $BatchResultFile) {
            try { [array]$batchResults = Get-Content $BatchResultFile -Raw -Encoding UTF8 | ConvertFrom-Json }
            catch [System.Exception] { Write-Log "Aviso: falha ao ler batch_result.json: $_" -Lvl "WARN" }
            Remove-Item $BatchResultFile -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $BatchInputFile -Force -ErrorAction SilentlyContinue

        $anyFailure = $false
        foreach ($card in $pendentes) {
            $phaseKey = $card.phase_key
            $resMatches = @($batchResults | Where-Object { $_.phase_key -eq $phaseKey })
            $res = if ($resMatches.Count -gt 0) { $resMatches[0] } else { $null }
            $phaseSuccess = if ($res) { [bool]$res.success } else { $false }
            if (-not $phaseSuccess) { $anyFailure = $true }

            $entry = $state.phases | Where-Object { $_.key -eq $phaseKey }
            if ($entry) {
                $entry.success = $phaseSuccess
                $entry.sent_at = if ($phaseSuccess) { Get-Date -Format 'dd/MM/yyyy HH:mm:ss' } else { $null }
            } else {
                $state.phases += [PSCustomObject]@{
                    key     = $phaseKey
                    success = $phaseSuccess
                    sent_at = if ($phaseSuccess) { Get-Date -Format 'dd/MM/yyyy HH:mm:ss' } else { $null }
                }
            }
            $phaseDisplay = if ($card.phase_display) { $card.phase_display } else { $phaseKey }
            Write-Log "Fase '$phaseDisplay' — $(if ($phaseSuccess) { 'OK' } else { 'FALHA' })"
        }

        $utf8NoBOMDel = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($DeliveryState, ($state | ConvertTo-Json -Depth 5), $utf8NoBOMDel)

        # Commit Oracle state apenas quando TODAS as fases entregues
        $allSent = -not ($state.phases | Where-Object { -not $_.success })
        if ($allSent -and (Test-Path $ObsStateTmp)) {
            Move-Item $ObsStateTmp $ObsStateFile -Force
        }

        if ($anyFailure) {
            Exit-WithCode 4 "Uma ou mais fases falharam no envio WhatsApp. Verifique os logs."
        }

        Exit-WithCode 0 "Execucao concluida com sucesso."

    } finally {
        if (Test-Path $ObsStateTmp) {
            Remove-Item $ObsStateTmp -Force -ErrorAction SilentlyContinue
            Write-Log "Limpeza finally: $ObsStateTmp removido." -Lvl "DEBUG"
        }
        Exit-AutomationLock -ExecId $ExecId -LogPath $LogFile
    }

} catch [System.Exception] {
    # Sem sinal de controle de fluxo por mensagem (padrao "Processo finalizado" usado em
    # outras automacoes) neste script: toda excecao que chegar aqui - incluindo
    # MethodInvocationException de chamadas .NET como [System.IO.File]::WriteAllText - deve
    # fechar a telemetria e sair com ExitCode padronizado, nunca escapar sem Exit-WithCode.
    Exit-WithCode 4 "Falha critica na orquestracao: $_"
}
