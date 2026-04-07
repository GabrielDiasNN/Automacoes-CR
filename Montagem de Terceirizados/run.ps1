# ==============================================================================
# ARQUIVO: run.ps1
# VERSÃO: 1.0
# DESCRIÇÃO: Orchestrador PS-nativo para Montagem de Terceirizados.
#            Abre Excel COM, executa a macro AtualizarEValidar (modo robô),
#            monitora log VBA unificado para detectar conclusão ou timeout.
#
# ARGS: [ExecId] - passado positionally pelo MonitorAutomacoes.ps1
#
# CHAMADA DA MACRO: AtualizarEValidar(blnModoRobo=True, strExecId=ExecId)
#   - blnModoRobo=True suprime StatusBar e habilita comportamento headless.
#
# EXIT CODES (compatíveis com Trigger_Automation.vbs e MonitorAutomacoes.ps1):
#   0  — Sucesso
#   1  — Workbook não encontrado
#   2  — Falha ao iniciar Excel
#   3  — Falha ao abrir workbook
#   5  — Timeout aguardando conclusão VBA
#   6  — VBA reportou falha ou erro fatal
#   7  — Workbook bloqueado (somente leitura)
# ==============================================================================

[CmdletBinding()]
param(
    [string]$ExecId = ""  # Argumento posicional passado pelo monitor
)

$ErrorActionPreference = "Stop"

$BasePath = "C:\Automacoes\Montagem de Terceirizados"
$ExcelPath = Join-Path $BasePath "Validador_Notas_Montagem.xlsm"
$LogDir = Join-Path $BasePath "Logs"
$MacroName = "AtualizarEValidar"
$MaxTimeoutSec = 300
$PollIntervalMs = 3000

# Importar Lib-Logging (com fallback inline)
$libPath = "C:\Automacoes\lib\Lib-Logging.psm1"
if (Test-Path $libPath) {
    Import-Module $libPath -Force
}

# Derivar LogFile DEPOIS do import para usar Get-AutomacaoLogPath se disponível
if (Get-Command Get-AutomacaoLogPath -ErrorAction SilentlyContinue) {
    $LogFile = Get-AutomacaoLogPath -Slug "Montagem" -LogDir $LogDir
}
else {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    $LogFile = Join-Path $LogDir "Montagem.log"
}

# Log VBA usa o mesmo arquivo unificado (mesmo comportamento do Trigger_Automation.vbs)
$VbaLogFile = $LogFile

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
        $line = "[$ts] [PS] [$Lvl] [$ExecId] $Msg"
        Write-Host $line
        try {
            # Encoding Default (ANSI/Windows-1252) mantém consistência com o VBA (VUL-02)
            Add-Content -Path $LogFile -Value $line -Encoding Default
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

# ============================================================
# Rotação de log (mantém 30 dias — roda a cada hora seg-sex)
if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
    Invoke-LogRotation -LogPath $LogFile -KeepDays 30
}

Write-Log "========================================================================================="
Write-Log "INICIO - run.ps1 Montagem de Terceirizados. ExecId=$ExecId"

# Validar workbook
if (-not (Test-Path $ExcelPath)) {
    Exit-WithCode 1 "Workbook nao encontrado: $ExcelPath"
}

# Garantir que o log VBA existe antes de capturar o baseline
if (-not (Test-Path $VbaLogFile)) {
    New-Item -ItemType File -Path $VbaLogFile -Force | Out-Null
}
$initialLogSize = (Get-Item $VbaLogFile).Length
Write-Log "Monitoramento VBA ativo. LogVBA=$VbaLogFile | Inicial=$initialLogSize bytes"

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

    # Executar macro com blnModoRobo=$true e ExecId
    Write-Log "Executando macro: $MacroName [blnModoRobo=True, ExecId=$ExecId]"
    try {
        $excel.Run($MacroName, $true, $ExecId) | Out-Null
    }
    catch {
        Write-Log "Falha na chamada COM da macro: $_" -Lvl "WARN"
        # VBA pode ter lançado erro gerenciado — prosseguir com monitoramento do log
    }

    # Monitorar log VBA por conclusão
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

        if (-not (Test-Path $VbaLogFile)) { continue }

        $currentSize = (Get-Item $VbaLogFile).Length

        if ($currentSize -lt $previousSize) {
            Write-Log "Log VBA truncado. Reiniciando baseline." -Lvl "WARN"
            $initialLogSize = $currentSize
            $previousSize = $currentSize
            continue
        }

        if ($currentSize -gt $previousSize) {
            # VUL-01: lê bytes brutos e fatia por offset de byte (correto).
            # Get-Content -Encoding UTF8 retorna chars, cujo índice diverge do offset
            # em bytes se o arquivo contiver chars ANSI multi-byte (Windows-1252).
            try {
                $allBytes = [System.IO.File]::ReadAllBytes($VbaLogFile)
            }
            catch {
                Write-Log "Falha ao ler log VBA durante monitoramento." -Lvl "WARN"
                $previousSize = $currentSize
                continue
            }

            $newBytes = if ($allBytes.Length -gt $initialLogSize) {
                $allBytes[$initialLogSize..($allBytes.Length - 1)]
            }
            else { [byte[]]@() }
            # Decodifica como Windows-1252 (ANSI) — mesmo encoding que o VBA usa ao escrever
            $newContent = [System.Text.Encoding]::GetEncoding(1252).GetString($newBytes)

            if ($newContent -match "ERRO FATAL") {
                $successVba = $false
                $foundEnd = $true
            }
            elseif ($newContent -match "FIM DO PROCESSO\.") {
                $successVba = ($newContent -match "Resultado=Sucesso")
                $foundEnd = $true
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
    # Fechar Excel COM de forma limpa
    if ($wb) {
        try { $wb.Close($false) } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wb) | Out-Null } catch {}
    }
    if ($excel) {
        try { $excel.Quit() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch {}
    }
}

if ($success) {
    Exit-WithCode 0 "Macro concluida com sucesso."
}
else {
    Exit-WithCode 6 "Conclusao anormal."
}
