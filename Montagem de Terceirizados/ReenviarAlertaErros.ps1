# ==============================================================================
# ARQUIVO: ReenviarAlertaErros.ps1
# VERSÃO: 1.0
# DESCRIÇÃO: Força o reenvio do e-mail de alerta de erros NF sem refazer o
#            refresh do Oracle. Apaga o cache de estado anterior (para que o
#            plugin trate os erros atuais como "novos") e chama a macro
#            RevalidarENotificar, que revalida os dados já carregados e dispara
#            a notificação via FallbackNotificacaoPadrao.
#
# USO:
#   pwsh -File "C:\Automacoes\Montagem de Terceirizados\ReenviarAlertaErros.ps1"
#
# QUANDO USAR:
#   - A automação rodou mas o e-mail de erro não foi enviado
#   - Deseja renotificar sem aguardar o próximo ciclo agendado
#   - A execução mais recente está refletida no workbook
# ==============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$BasePath    = "C:\Automacoes\Montagem de Terceirizados"
$ExcelPath   = Join-Path $BasePath "Validador_Notas_Montagem.xlsm"
$LogDir      = Join-Path $BasePath "Logs"
$LogFile     = Join-Path $LogDir "Montagem.log"
$CacheFile   = Join-Path $BasePath "Cache_Estado_Detalhado.txt"
$MacroName   = "RevalidarENotificar"
$MaxWaitSec  = 120
$PollMs      = 2000

$libPath = "C:\Automacoes\lib\Lib-Logging.psm1"
if (Test-Path $libPath) { Import-Module $libPath -Force }

$ExecId = (Get-Date -Format 'yyyyMMdd_HHmmss') + "_FORCAR"

function Write-Log {
    param([string]$Msg, [string]$Lvl = "INFO")
    $line = "[$(Get-Date -Format 'dd/MM/yyyy HH:mm:ss')] [PS] [$Lvl] [ExecId:$ExecId] $Msg"
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
}

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Log "=== REENVIO FORCADO DE ALERTA ==="
Write-Log "Workbook=$ExcelPath"

# --- 1. Validações iniciais ---
if (-not (Test-Path $ExcelPath)) {
    Write-Log "Workbook nao encontrado: $ExcelPath" "ERROR"
    exit 1
}

# --- 2. Apagar cache para forçar detecção de mudança ---
if (Test-Path $CacheFile) {
    try {
        Remove-Item $CacheFile -Force
        Write-Log "Cache de estado apagado. Erros serão tratados como novos."
    } catch {
        Write-Log "Aviso: nao foi possivel apagar o cache: $_" "WARN"
    }
} else {
    Write-Log "Cache nao encontrado (primeira execucao ou ja apagado)."
}

# --- 3. Abrir Excel via COM ---
Write-Log "Iniciando Excel via COM..."
$excel = $null
$wb    = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible           = $false
    $excel.DisplayAlerts     = $false
    $excel.AskToUpdateLinks  = $false
} catch {
    Write-Log "Falha ao criar instancia Excel: $_" "ERROR"
    exit 2
}

try {
    $wb = $excel.Workbooks.Open($ExcelPath, 0, $false)
} catch {
    Write-Log "Falha ao abrir workbook: $_" "ERROR"
    try { $excel.Quit() } catch {}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    exit 3
}

# --- 4. Capturar offset do log antes da macro ---
$logOffsetBefore = 0
if (Test-Path $LogFile) {
    try { $logOffsetBefore = (Get-Item $LogFile).Length } catch {}
}

# --- 5. Executar macro ---
Write-Log "Executando macro: $MacroName"
try {
    $excel.Run($MacroName)
} catch {
    Write-Log "Falha ao executar macro: $_" "ERROR"
    try { $wb.Close($false) } catch {}
    try { $excel.Quit() } catch {}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    exit 4
}

# --- 6. Aguardar sentinela no log VBA ---
Write-Log "Aguardando conclusao da macro (max ${MaxWaitSec}s)..."
$deadline  = (Get-Date).AddSeconds($MaxWaitSec)
$resultado = $null

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds $PollMs
    if (-not (Test-Path $LogFile)) { continue }

    try {
        $linhasNovas = Get-Content $LogFile -Encoding UTF8 -Raw
        if ($logOffsetBefore -gt 0) {
            $stream = [System.IO.File]::Open($LogFile, 'Open', 'Read', 'ReadWrite')
            $stream.Seek($logOffsetBefore, 'Begin') | Out-Null
            $reader = New-Object System.IO.StreamReader($stream)
            $linhasNovas = $reader.ReadToEnd()
            $reader.Close(); $stream.Close()
        }

        if ($linhasNovas -match "REENVIO FORCADO: Concluido") {
            $resultado = "SUCESSO"
            break
        }
        if ($linhasNovas -match "\[ERROR\]") {
            $resultado = "ERRO_VBA"
            break
        }
    } catch {}
}

if (-not $resultado) {
    Write-Log "Timeout ($MaxWaitSec s) aguardando conclusao da macro." "WARN"
    $resultado = "TIMEOUT"
}

# --- 7. Fechar Excel ---
try { $wb.Close($false) } catch {}
try { $excel.Quit() } catch {}
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null

# --- 8. Resultado ---
switch ($resultado) {
    "SUCESSO" {
        Write-Log "Reenvio concluido com sucesso."
        Write-Log "=== FIM ==="
        exit 0
    }
    "ERRO_VBA" {
        Write-Log "Macro reportou erro. Verifique o log VBA em: $LogFile" "ERROR"
        exit 6
    }
    default {
        Write-Log "Finalizando com status: $resultado" "WARN"
        exit 5
    }
}
