# ==============================================================================
# ARQUIVO: run.ps1
# VERSÃO: 1.0
# DESCRIÇÃO: Orchestrador PS-nativo para Receitas Bloqueadas.
#            Abre Excel COM, executa a macro ExecutarProcessoCompleto,
#            monitora log VBA e, em caso de sucesso, dispara Send-WhatsApp.ps1.
#
# ARGS: [ExecId] - passado positionally pelo MonitorAutomacoes.ps1
#
# EXIT CODES (compatíveis com VBS trigger e MonitorAutomacoes):
#   0  — Sucesso
#   1  — Workbook não encontrado
#   2  — Falha ao iniciar Excel
#   3  — Falha ao abrir workbook
#   4  — Falha ao executar macro
#   5  — Timeout aguardando conclusão VBA
#   6  — VBA reportou falha ou erro fatal
#   7  — Workbook bloqueado (somente leitura)
#   8  — Falha de compilacao VBA (preflight)
#  23  — WhatsApp em cooldown (pass-through do bridge)
#  40  — WhatsApp bloqueado por concorrência (pass-through do bridge)
# ==============================================================================

[CmdletBinding()]
param(
    [string]$ExecId = ""  # Argumento posicional passado pelo monitor
)

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$BasePath = $ScriptDir
$ExcelPath = Join-Path $BasePath "Receitas Bloqueadas.xlsm"
$LogDir = Join-Path $BasePath "Logs"
$MacroName = "ExecutarProcessoCompleto"
$MaxTimeoutSec = 300
$PollIntervalMs = 3000

# Tenta carregar biblioteca de logging de forma relativa
$libPath = Join-Path (Split-Path -Parent $BasePath) "lib\Lib-Logging.psm1"
if (Test-Path $libPath) {
    Import-Module $libPath -Force
}

$SendWhatsAppScript = Join-Path (Split-Path -Parent $BasePath) "lib\Send-WhatsApp.ps1"

if (Get-Command Get-AutomacaoLogPath -ErrorAction SilentlyContinue) {
    $LogFile = Get-AutomacaoLogPath -Slug "ReceitasBloqueadas" -LogDir $LogDir
}
else {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    $LogFile = Join-Path $LogDir "ReceitasBloqueadas.log"
}
$vbaLogFile = $LogFile

if ([string]::IsNullOrWhiteSpace($ExecId)) {
    if (Get-Command New-ExecId -ErrorAction SilentlyContinue) {
        $ExecId = New-ExecId
    }
    else {
        $ExecId = (Get-Date -Format 'yyyyMMdd_HHmmss') + "_" + (Get-Random -Minimum 1000 -Maximum 9999)
    }
}

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    if (Get-Command Write-AutomacaoLog -ErrorAction SilentlyContinue) {
        Write-AutomacaoLog -Message $Msg -Level $Lvl -ExecId $ExecId -LogPath $LogFile
    }
    else {
        $ts = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
        $line = "[$ts] [PS] [$Lvl] [ExecId:$ExecId] $Msg"
        Write-Host $line
        try {
            if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
            Add-Content -Path $LogFile -Value $line -Encoding UTF8
        }
        catch {}
    }
}

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")
    if ($Msg) { Write-Log $Msg -Lvl $(if ($Code -eq 0) { "INFO" } else { "ERRO" }) }
    Write-Log "FIM - Finalizado. ExitCode=$Code"
    Write-Log "========================================================================================="
    exit $Code
}

# ==============================================================================
# VALIDACAO DE AMBIENTE (RUNTIME SAFETY)
# ==============================================================================
if (Get-Command Test-AutomationEnvironment -ErrorAction SilentlyContinue) {
    Write-Log "Validando requisitos de ambiente..."
    $envTest = Test-AutomationEnvironment -ConfigPath (Join-Path $BasePath "whatsapp-config.json") -RequiredPaths @($ExcelPath, $SendWhatsAppScript)
    if (-not $envTest.Success) {
        Exit-WithCode 9 "FALHA DE AMBIENTE: $($envTest.Message)"
    }
    Write-Log "Ambiente validado: $($envTest.Message)"
}

function Test-VbaProjectCompiles {
    param(
        [object]$ExcelApp,
        [object]$Workbook
    )

    try {
        $Workbook.Activate() | Out-Null
    }
    catch {
        Write-Log "Preflight VBA: nao foi possivel ativar workbook para compilacao preventiva. Seguindo execucao. Detalhe: $($_.Exception.Message)" -Lvl "WARN"
        return $true
    }

    $vbe = $null
    try {
        $vbe = $ExcelApp.VBE
    }
    catch {
        Write-Log "Preflight VBA: VBE indisponivel (possivel bloqueio de acesso programatico). Seguindo sem compilacao preventiva. Detalhe: $($_.Exception.Message)" -Lvl "WARN"
        return $true
    }

    if ($null -eq $vbe) {
        Write-Log "Preflight VBA: VBE retornou nulo. Seguindo sem compilacao preventiva." -Lvl "INFO"
        return $true
    }

    $commandBars = $null
    try {
        $commandBars = $vbe.CommandBars
    }
    catch {
        Write-Log "Preflight VBA: CommandBars do VBE indisponivel. Seguindo sem compilacao preventiva. Detalhe: $($_.Exception.Message)" -Lvl "WARN"
        return $true
    }

    if ($null -eq $commandBars) {
        Write-Log "Preflight VBA: CommandBars retornou nulo. Seguindo sem compilacao preventiva." -Lvl "WARN"
        return $true
    }

    $compileControl = $null
    try {
        $compileControl = $commandBars.FindControl(1, 578)
    }
    catch {
        Write-Log "Preflight VBA: comando de compilacao inacessivel no ambiente atual. Seguindo sem compilacao preventiva. Detalhe: $($_.Exception.Message)" -Lvl "WARN"
        return $true
    }

    if ($null -eq $compileControl) {
        Write-Log "Preflight VBA: comando de compilacao nao encontrado; seguindo execucao." -Lvl "WARN"
        return $true
    }

    try {
        $compileControl.Execute()
        Write-Log "Preflight VBA: compilacao concluida com sucesso."
        return $true
    }
    catch {
        $compileMessage = $_.Exception.Message
        $isGenericVbeInteropFailure = (
            $compileMessage -match "Unexpected HRESULT" -or
            $compileMessage -match "call to a COM component"
        )

        if ($isGenericVbeInteropFailure) {
            Write-Log "Preflight VBA: VBE retornou HRESULT generico ao compilar. Seguindo sem bloquear a execucao. Detalhe: $compileMessage" -Lvl "WARN"
            return $true
        }

        Write-Log "Preflight VBA: falha de compilacao detectada: $compileMessage" -Lvl "ERRO"
        return $false
    }
}

# ============================================================
if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
    Invoke-LogRotation -LogPath $LogFile -KeepDays 15
}

Write-Log "========================================================================================="
Write-Log "INICIO - run.ps1 Receitas Bloqueadas. ExecId=$ExecId"

# Validar workbook
if (-not (Test-Path $ExcelPath)) {
    Exit-WithCode 1 "Workbook nao encontrado: $ExcelPath"
}

# VBA log unificado (mesmo arquivo que PS)
$vbaLogFile = $LogFile

$excel = $null
$wb = $null
$success = $false

try {
    # Abrir Excel COM
    Write-Log "Abrindo Excel COM..."
    try {
        $excel = New-Object -ComObject Excel.Application
    }
    catch {
        Exit-WithCode 2 "Falha ao iniciar Excel COM: $_"
    }

    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false

    # Abrir workbook
    Write-Log "Abrindo workbook: $ExcelPath"
    try {
        $wb = $excel.Workbooks.Open($ExcelPath)
    }
    catch {
        Exit-WithCode 3 "Falha ao abrir workbook: $_"
    }

    if ($wb.ReadOnly) {
        Exit-WithCode 7 "Workbook aberto em modo somente leitura. Possivel bloqueio: $ExcelPath"
    }

    Write-Log "Preflight VBA: validando compilacao antes de executar macro..."
    if (-not (Test-VbaProjectCompiles -ExcelApp $excel -Workbook $wb)) {
        Exit-WithCode 8 "Compilacao VBA invalida. Corrija os erros no VBE antes de executar."
    }

    # Garantir que o arquivo de log VBA existe antes de capturar o baseline
    if (-not (Test-Path $vbaLogFile)) {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
        New-Item -ItemType File -Path $vbaLogFile -Force | Out-Null
    }
    $initialLogSize = (Get-Item $vbaLogFile).Length
    Write-Log "Monitoramento VBA ativo. LogVBA=$vbaLogFile | Inicial=$initialLogSize bytes"

    # Executar macro com fallback de nome qualificado para reduzir falhas de resolucao no COM
    Write-Log "Executando macro: $MacroName [ExecId=$ExecId]"
    $macroCandidates = @(
        $MacroName,
        "modReceitasBloqueadas.$MacroName",
        "'Receitas Bloqueadas.xlsm'!$MacroName",
        "'Receitas Bloqueadas.xlsm'!modReceitasBloqueadas.$MacroName"
    )

    $macroInvoked = $false
    $macroLastError = ""

    foreach ($macroCandidate in $macroCandidates) {
        try {
            $excel.Run($macroCandidate, $ExecId) | Out-Null
            if ($macroCandidate -ne $MacroName) {
                Write-Log "Macro executada via fallback qualificado: $macroCandidate" -Lvl "WARN"
            }
            $macroInvoked = $true
            break
        }
        catch {
            $macroLastError = $_.ToString()
            Write-Log "Falha na chamada COM da macro '$macroCandidate': $macroLastError" -Lvl "WARN"
        }
    }

    if (-not $macroInvoked) {
        # Verificar se VBA ja registrou conclusao no log antes de abortar
        $jaTemFim = $false
        if (Test-Path $vbaLogFile) {
            try {
                $logSnap = Get-Content $vbaLogFile -Raw -Encoding UTF8 -ErrorAction Stop
                $novoConteudo = if ($logSnap.Length -gt $initialLogSize) { $logSnap.Substring([int]$initialLogSize) } else { "" }
                $jaTemFim = $novoConteudo -match "FIM DO PROCESSO\."
            }
            catch {}
        }

        if (-not $jaTemFim) {
            $isMacroUnavailable = (
                $macroLastError -match "(?i)cannot run the macro|macro.*not available|macros?.*disabled|n.o .poss.vel executar a macro|n.o est. dispon.vel|macros?.*desabilitad"
            )

            if ($isMacroUnavailable) {
                Exit-WithCode 4 "Macro inacessivel no Excel (possivel indisponibilidade/desabilitacao). Detalhe: $macroLastError"
            }

            Exit-WithCode 4 "Falha ao invocar macro em todas as variantes de nome. Detalhe: $macroLastError"
        }

        Write-Log "Falha COM na invocacao da macro, mas VBA ja registrou FIM DO PROCESSO no log. Continuando monitoramento." -Lvl "WARN"
    }

    # Monitorar VBA log por conclusão
    Write-Log "Aguardando conclusao via log VBA (timeout: ${MaxTimeoutSec}s)..."

    $watchStart = Get-Date
    $previousSize = $initialLogSize
    $foundEnd = $false
    $successVba = $false

    while (-not $foundEnd) {
        $elapsed = (New-TimeSpan -Start $watchStart -End (Get-Date)).TotalSeconds
        if ($elapsed -ge $MaxTimeoutSec) {
            Exit-WithCode 5 "TIMEOUT: VBA nao registrou termino em ${MaxTimeoutSec}s"
        }

        Start-Sleep -Milliseconds $PollIntervalMs

        if (-not (Test-Path $vbaLogFile)) { continue }

        $currentSize = (Get-Item $vbaLogFile).Length

        if ($currentSize -lt $previousSize) {
            Write-Log "Log VBA truncado. Reiniciando baseline." -Lvl "WARN"
            $initialLogSize = $currentSize
            $previousSize = $currentSize
            continue
        }

        if ($currentSize -gt $previousSize) {
            try {
                $allContent = Get-Content $vbaLogFile -Raw -Encoding UTF8 -ErrorAction Stop
            }
            catch {
                Write-Log "Falha ao ler log VBA." -Lvl "WARN"
                $previousSize = $currentSize
                continue
            }

            $newContent = if ($allContent.Length -gt $initialLogSize) {
                $allContent.Substring([int]$initialLogSize)
            }
            else { "" }

            if ($newContent -match "ERRO FATAL") {
                $successVba = $false
                $foundEnd = $true
            }
            elseif ($newContent -match "FIM DO PROCESSO\.") {
                $successVba = ($newContent -match "Resultado=Sucesso")
                $foundEnd = $true

                if ($newContent -match "Resultado=Sem envio") {
                    Write-Log "VBA reportou tabela vazia (Sem envio). Nenhum e-mail ou WhatsApp enviado." -Lvl "WARN"
                }
            }

            $previousSize = $currentSize
        }
    }

    if (-not $successVba) {
        Exit-WithCode 6 "VBA reportou falha ou erro fatal nos logs"
    }

    $success = $true
}
finally {
    if ($wb) {
        try { $wb.Close($false) } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wb) | Out-Null } catch {}
    }
    if ($excel) {
        try { $excel.Quit() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch {}
    }
}

if (-not $success) {
    Exit-WithCode 6 "Conclusao anormal."
}

# ============================================================
# PÓS-EXECUÇÃO: Envio WhatsApp
# ============================================================
if (-not (Test-Path $SendWhatsAppScript)) {
    Write-Log "AVISO: Send-WhatsApp.ps1 nao encontrado em: $SendWhatsAppScript. Etapa WhatsApp ignorada." -Lvl "WARN"
    Exit-WithCode 0 "Macro concluida. WhatsApp ignorado (script ausente)."
}

Write-Log "Disparando Send-WhatsApp.ps1. ExecId=$ExecId Mode=AUTO"
try {
    $whatsAppProc = Start-Process "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$SendWhatsAppScript`" -ExecId `"$ExecId`" -Mode AUTO" `
        -WindowStyle Hidden `
        -Wait `
        -PassThru `
        -ErrorAction Stop

    $whatsAppExit = $whatsAppProc.ExitCode
    Write-Log "Send-WhatsApp.ps1 finalizado. ExitCode=$whatsAppExit"

    if ($whatsAppExit -eq 40) {
        Write-Log "WhatsApp ignorado por lock ativo (ExitCode 40)." -Lvl "WARN"
        Exit-WithCode 40 ""
    }
    elseif ($whatsAppExit -eq 23) {
        Write-Log "WhatsApp em cooldown de retry (ExitCode 23)." -Lvl "WARN"
        Exit-WithCode 23 ""
    }
    elseif ($whatsAppExit -ne 0) {
        Write-Log "Send-WhatsApp.ps1 retornou ExitCode $whatsAppExit." -Lvl "WARN"
    }
}
catch {
    Write-Log "Falha ao iniciar Send-WhatsApp.ps1: $_" -Lvl "WARN"
}

Exit-WithCode 0 "Processo concluido com sucesso."
