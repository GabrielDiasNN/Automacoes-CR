# ==============================================================================
# ARQUIVO: ReenviarAlertaErros.ps1
# VERSAO: 2.0
# DESCRICAO: Forca o reenvio do e-mail de alerta de erros NF sem refazer o
#            refresh do Oracle. Apaga o cache de estado anterior (para que o
#            plugin trate os erros atuais como "novos") e chama a macro
#            RevalidarENotificar, que revalida os dados ja carregados e dispara
#            a notificacao.
#
# USO:
#   pwsh -File "C:\Automacoes\Montagem de Terceirizados\ReenviarAlertaErros.ps1"
#   pwsh -File "C:\Automacoes\Montagem de Terceirizados\ReenviarAlertaErros.ps1" -EmailPreviewOnly -EmailToTest "homolog@empresa.com.br" -EmailCcTest "qa@empresa.com.br"
#
# QUANDO USAR:
#   - A automacao rodou mas o e-mail de erro nao foi enviado
#   - Deseja renotificar sem aguardar o proximo ciclo agendado
#   - A execucao mais recente esta refletida no workbook
#
# ARGUMENTOS:
#   -KeepCache  Nao apaga Cache_Estado_Detalhado.txt (usa logica de delta normal)
#               Por padrao, o cache e apagado para tratar erros atuais como novos.
#   -EmailPreviewOnly  Abre o email no Outlook sem enviar (modo teste)
#   -EmailToTest       Sobrescreve destinatario PARA em modo teste
#   -EmailCcTest       Sobrescreve destinatario CC em modo teste
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$KeepCache,
    [switch]$EmailPreviewOnly,
    [string]$EmailToTest = "",
    [string]$EmailCcTest = ""
)

$ErrorActionPreference = "Stop"

$BasePath = "C:\Automacoes\Montagem de Terceirizados"
$ExcelPath = Join-Path $BasePath "Validador_Notas_Montagem.xlsm"
$LogDir = Join-Path $BasePath "Logs"
$LogFile = Join-Path $LogDir "Montagem.log"
$CacheFile = Join-Path $BasePath "Cache_Estado_Detalhado.txt"
$MacroName = "RevalidarENotificar"
$MacroEmailConfig = "modEmailOutlook.ConfigurarModoNotificacaoTeste"

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

if ($EmailPreviewOnly) {
    Write-Log "Modo sem envio ativo: e-mails serao salvos em Rascunhos (headless)." "WARN"
}

Write-Log "Modo Email | PreviewOnly=$EmailPreviewOnly | ToTest=$EmailToTest | CcTest=$EmailCcTest"

# --- 1. Validacoes iniciais ---
if (-not (Test-Path $ExcelPath)) {
    Write-Log "Workbook nao encontrado: $ExcelPath" "ERROR"
    exit 1
}

# --- 2. Apagar cache para forcar deteccao de mudanca ---
if (-not $KeepCache) {
    if (Test-Path $CacheFile) {
        try {
            Remove-Item $CacheFile -Force
            Write-Log "Cache de estado apagado. Erros serao tratados como novos."
        }
        catch {
            Write-Log "Aviso: nao foi possivel apagar o cache: $_" "WARN"
        }
    }
    else {
        Write-Log "Cache nao encontrado (primeira execucao ou ja apagado)."
    }
}
else {
    Write-Log "Cache mantido (-KeepCache). Logica de delta normal sera aplicada."
}

# --- 3. Abrir Excel via COM ---
Write-Log "Iniciando Excel via COM..."
$excel = $null
$wb = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
}
catch {
    Write-Log "Falha ao criar instancia Excel: $_" "ERROR"
    exit 2
}

try {
    $wb = $excel.Workbooks.Open($ExcelPath, 0, $false)
}
catch {
    Write-Log "Falha ao abrir workbook: $_" "ERROR"
    try { $excel.Quit() } catch {}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    exit 3
}

$temOverrideEmail = $EmailPreviewOnly -or -not [string]::IsNullOrWhiteSpace($EmailToTest) -or -not [string]::IsNullOrWhiteSpace($EmailCcTest)
if ($temOverrideEmail) {
    Write-Log "Configurando modo de notificacao TESTE no VBA..."
    try {
        $excel.Run($MacroEmailConfig, [bool]$EmailPreviewOnly, $EmailToTest, $EmailCcTest) | Out-Null
        Write-Log "Modo de notificacao TESTE configurado no VBA."
    }
    catch {
        Write-Log "Falha ao configurar modo de notificacao TESTE no VBA: $_" "ERROR"
        try { $wb.Close($false) } catch {}
        try { $excel.Quit() } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
        exit 4
    }
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
}
catch {
    Write-Log "Falha ao executar macro: $_" "ERROR"
    try { $wb.Close($false) } catch {}
    try { $excel.Quit() } catch {}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    exit 4
}

# --- 6. Analisar resultado no log ---
# excel.Run() e sincrono: quando retorna, o VBA ja terminou e o log esta completo.
# Lemos apenas as linhas gravadas APOS o inicio desta execucao (via offset de bytes).
Write-Log "Analisando resultado..."

$linhasNovas = @()
if (Test-Path $LogFile) {
    try {
        $stream = [System.IO.File]::Open($LogFile, 'Open', 'Read', 'ReadWrite')
        $stream.Seek($logOffsetBefore, 'Begin') | Out-Null
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        $conteudo = $reader.ReadToEnd()
        $reader.Close()
        $stream.Close()
        $linhasNovas = $conteudo -split "`n" | Where-Object { $_.Trim() -ne "" }
    }
    catch {
        Write-Log "Aviso: nao foi possivel ler novas entradas do log: $_" "WARN"
    }
}

# Exibe as novas linhas geradas pelo VBA nesta execucao
if ($linhasNovas.Count -gt 0) {
    Write-Host ""
    Write-Host "--- Log VBA desta execucao ---" -ForegroundColor Cyan
    $linhasNovas | ForEach-Object { Write-Host "  $_" }
    Write-Host "--- Fim ---" -ForegroundColor Cyan
    Write-Host ""
}

# Categoriza o resultado
$emailMarker = if ($EmailPreviewOnly) { "E-MAIL: rascunho salvo com sucesso" } else { "E-MAIL: Enviado com sucesso" }
$emailEnviado = $linhasNovas | Where-Object { $_ -match [Regex]::Escape($emailMarker) }
$emailFalhou = $linhasNovas | Where-Object { $_ -match "FALHA DEFINITIVA: Email" }
$semMudanca = $linhasNovas | Where-Object { $_ -match "Estado inalterado" }
$idempotencia = $linhasNovas | Where-Object { $_ -match "ignorado por idempotencia" }
$errosVba = $linhasNovas | Where-Object { $_ -match "\[ERROR\]" }
$concluido = $linhasNovas | Where-Object { $_ -match "REENVIO FORCADO: Concluido" }

# --- 7. Fechar Excel ---
try { $wb.Close($false) } catch {}
try { $excel.Quit() } catch {}
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null

# --- 8. Resultado final ---
if ($emailEnviado) {
    if ($EmailPreviewOnly) {
        Write-Log "RASCUNHO DE E-MAIL SALVO COM SUCESSO (NoSend)."
    }
    else {
        Write-Log "E-MAIL ENVIADO COM SUCESSO."
    }
    Write-Log "=== FIM ==="
    exit 0
}

if ($idempotencia) {
    Write-Log "E-mail ignorado por idempotencia (ja enviado nesta sessao do Excel). Feche e reabra o workbook antes de reenviar." "WARN"
    Write-Log "=== FIM ==="
    exit 0
}

if ($semMudanca) {
    Write-Log "Estado inalterado: nenhuma mudanca de erros detectada desde a ultima execucao." "WARN"
    Write-Log "Para forcar envio mesmo sem mudanca: execute sem -KeepCache (padrao)." "WARN"
    Write-Log "=== FIM ==="
    exit 7
}

if ($emailFalhou) {
    Write-Log "FALHA DEFINITIVA no envio do e-mail apos todas as tentativas. Verifique o Outlook e os destinatarios." "ERROR"
    Write-Log "=== FIM ==="
    exit 6
}

if ($errosVba) {
    Write-Log "Macro completou com erros VBA internos. Consulte o log acima." "ERROR"
    Write-Log "=== FIM ==="
    exit 5
}

if ($concluido) {
    Write-Log "Macro concluida sem envio de e-mail detectado. Verifique o log acima." "WARN"
    Write-Log "=== FIM ==="
    exit 8
}

Write-Log "Macro nao gerou as entradas esperadas no log. Verifique manualmente: $LogFile" "WARN"
Write-Log "=== FIM ==="
exit 9

