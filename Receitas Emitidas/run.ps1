# ==============================================================================
# ARQUIVO: run.ps1
# VERSÃO: 1.0
# DESCRIÇÃO: Piloto PS-nativo para Receitas Emitidas.
#            Abre o workbook via Excel COM, executa a macro AtualizarEEnviarOutlook
#            e monitora o log VBA para detectar conclusão ou timeout.
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
# ==============================================================================

[CmdletBinding()]
param(
    [string]$ExecId = ""  # Argumento posicional passado pelo monitor
)

$ErrorActionPreference = "Stop"

$BasePath = "C:\Automacoes\Receitas Emitidas"
$ExcelPath = Join-Path $BasePath "Controle de Receitas Emitidas.xlsm"
$LogDir = Join-Path $BasePath "Logs"
$MacroName = "AtualizarEEnviarOutlook"
$MaxTimeoutSec = 300
$PollIntervalMs = 3000

# Importar Lib-Logging ANTES de derivar o caminho do log
$libPath = "C:\Automacoes\lib\Lib-Logging.psm1"
if (Test-Path $libPath) {
    Import-Module $libPath -Force
}

if (Get-Command Get-AutomacaoLogPath -ErrorAction SilentlyContinue) {
    $LogFile = Get-AutomacaoLogPath -Slug "ReceitasEmitidas" -LogDir $LogDir
}
else {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    $LogFile = Join-Path $LogDir "ReceitasEmitidas.log"
}
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

# ============================================================
if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
    Invoke-LogRotation -LogPath $LogFile -KeepDays 15
}

Write-Log "========================================================================================="
Write-Log "INICIO - run.ps1 Receitas Emitidas. ExecId=$ExecId"

# Validar workbook
if (-not (Test-Path $ExcelPath)) {
    Exit-WithCode 1 "Workbook nao encontrado: $ExcelPath"
}

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

    # Capturar tamanho inicial do log VBA (baseline)
    $initialLogSize = 0
    if (Test-Path $VbaLogFile) {
        $initialLogSize = (Get-Item $VbaLogFile).Length
    }
    Write-Log "Monitoramento VBA ativo. LogVBAInicial=$initialLogSize bytes"

    # Executar macro
    Write-Log "Executando macro: $MacroName [ExecId=$ExecId]"
    try {
        $excel.Run($MacroName, $ExecId) | Out-Null
    }
    catch {
        Write-Log "Falha na execucao da macro (COM): $_" -Lvl "ERRO"
        # A macro pode ter lançado erro mas o VBA pode ter gravado no log — prosseguir com timeout
    }

    # Monitorar VBA log por conclusão
    Write-Log "Aguardando conclusao via log VBA (timeout: ${MaxTimeoutSec}s)..."

    $watchStart = Get-Date
    $previousSize = $initialLogSize
    $foundEnd = $false
    $fatalVba = $false
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
            try {
                $allContent = Get-Content $VbaLogFile -Raw -Encoding UTF8 -ErrorAction Stop
            }
            catch {
                Write-Log "Falha ao ler log VBA durante monitoramento." -Lvl "WARN"
                $previousSize = $currentSize
                continue
            }

            $newContent = if ($allContent.Length -gt $initialLogSize) {
                $allContent.Substring([int]$initialLogSize)
            }
            else { "" }

            if ($newContent -match "ERRO FATAL") {
                $fatalVba = $true
                $foundEnd = $true
            }
            elseif ($newContent -match "FIM DO PROCESSO\.") {
                $successVba = ($newContent -match "Resultado=Sucesso")
                $foundEnd = $true
            }

            $previousSize = $currentSize
        }
    }

    if ($fatalVba -or -not $successVba) {
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
