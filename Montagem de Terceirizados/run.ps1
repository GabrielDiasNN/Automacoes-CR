# ===============================================================================
# ARQUIVO: run.ps1
# VERSAO: 1.0
# DESCRICAO: Piloto PS-nativo para Montagem de Terceirizados.
#            Abre o workbook via Excel COM, executa a macro AtualizarEValidar
#            (modo robo + ExecId) e monitora o log VBA para detectar
#            conclusao ou timeout.
#
# ARGS:
#   [ExecId]             - passado positionally pelo MonitorAutomacoes.ps1
#   [-EmailPreviewOnly]  - abre o email no Outlook sem enviar (modo teste)
#   [-EmailToTest]       - sobrescreve destinatario PARA em modo teste
#   [-EmailCcTest]       - sobrescreve destinatario CC em modo teste
#
# EXIT CODES (compativeis com Trigger_Automation.vbs e MonitorAutomacoes):
#   0  - Sucesso
#   1  - Workbook nao encontrado
#   2  - Falha ao iniciar Excel
#   3  - Falha ao abrir workbook
#   4  - Falha ao executar macro
#   5  - Timeout aguardando conclusao VBA
#   6  - VBA reportou falha ou erro fatal
#   7  - Workbook bloqueado (somente leitura)
#   8  - Falha de compilacao VBA (preflight)
# ===============================================================================

[CmdletBinding()]
param(
    [string]$ExecId = "",
    [switch]$EmailPreviewOnly,
    [string]$EmailToTest = "",
    [string]$EmailCcTest = ""
)

$ErrorActionPreference = "Stop"

$BasePath = "C:\Automacoes\Montagem de Terceirizados"
$ExcelPath = Join-Path $BasePath "Validador_Notas_Montagem.xlsm"
$LogDir = Join-Path $BasePath "Logs"
$MacroName = "AtualizarEValidar"
$MacroEmailConfig = "modEmailOutlook.ConfigurarModoNotificacaoTeste"
$MaxTimeoutSec = 300
$PollIntervalMs = 3000

$libPath = "C:\Automacoes\lib\Lib-Logging.psm1"
if (Test-Path $libPath) {
    Import-Module $libPath -Force
}

if (Get-Command Get-AutomacaoLogPath -ErrorAction SilentlyContinue) {
    $LogFile = Get-AutomacaoLogPath -Slug "Montagem" -LogDir $LogDir
}
else {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    }
    $LogFile = Join-Path $LogDir "Montagem.log"
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
            if (-not (Test-Path $LogDir)) {
                New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
            }
            Add-Content -Path $LogFile -Value $line -Encoding UTF8
        }
        catch {}
    }
}

function Exit-WithCode {
    param([int]$Code, [string]$Msg = "")

    if ($Msg) {
        Write-Log $Msg -Lvl $(if ($Code -eq 0) { "INFO" } else { "ERRO" })
    }

    Write-Log "FIM - Finalizado. ExitCode=$Code"
    Write-Log "========================================================================================="
    exit $Code
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

if (Get-Command Invoke-LogRotation -ErrorAction SilentlyContinue) {
    Invoke-LogRotation -LogPath $LogFile -KeepDays 15
}

Write-Log "========================================================================================="
Write-Log "INICIO - run.ps1 Montagem de Terceirizados. ExecId=$ExecId"

if ($EmailPreviewOnly) {
    Write-Log "Modo sem envio ativo: e-mails serao salvos em Rascunhos (headless)." -Lvl "WARN"
}

Write-Log "Modo Email | PreviewOnly=$EmailPreviewOnly | ToTest=$EmailToTest | CcTest=$EmailCcTest"

if (-not (Test-Path $ExcelPath)) {
    Exit-WithCode 1 "Workbook nao encontrado: $ExcelPath"
}

$excel = $null
$wb = $null
$success = $false
$saveFailed = $false

try {
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

    $temOverrideEmail = $EmailPreviewOnly -or -not [string]::IsNullOrWhiteSpace($EmailToTest) -or -not [string]::IsNullOrWhiteSpace($EmailCcTest)
    if ($temOverrideEmail) {
        Write-Log "Configurando modo de notificacao TESTE no VBA..."
        try {
            $excel.Run($MacroEmailConfig, [bool]$EmailPreviewOnly, $EmailToTest, $EmailCcTest) | Out-Null
            Write-Log "Modo de notificacao TESTE configurado no VBA."
        }
        catch {
            Exit-WithCode 4 "Falha ao configurar modo de notificacao TESTE no VBA: $_"
        }
    }

    if (-not (Test-Path $VbaLogFile)) {
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
        }
        New-Item -ItemType File -Path $VbaLogFile -Force | Out-Null
    }

    $initialLogSize = (Get-Item $VbaLogFile).Length
    Write-Log "Monitoramento VBA ativo. LogVBA=$VbaLogFile | Inicial=$initialLogSize bytes"

    Write-Log "Executando macro: $MacroName [ModoRobo=True | ExecId=$ExecId]"
    $macroRunInvocationFailed = $false
    $macroCandidates = @(
        $MacroName,
        "modMain.$MacroName",
        "'Validador_Notas_Montagem.xlsm'!$MacroName",
        "'Validador_Notas_Montagem.xlsm'!modMain.$MacroName"
    )

    $macroInvoked = $false
    $macroLastError = ""

    foreach ($macroCandidate in $macroCandidates) {
        try {
            $excel.Run($macroCandidate, $true, $ExecId) | Out-Null
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
        Start-Sleep -Milliseconds 700
        $sizeAfterMacroCall = (Get-Item $VbaLogFile).Length
        if ($sizeAfterMacroCall -le $initialLogSize) {
            $isMacroUnavailable = (
                $macroLastError -match "(?i)cannot run the macro|macro.*not available|macros?.*disabled|n.o .poss.vel executar a macro|n.o est. dispon.vel|macros?.*desabilitad"
            )

            if ($isMacroUnavailable) {
                Exit-WithCode 4 "Macro inacessivel no Excel (possivel indisponibilidade/desabilitacao). Detalhe: $macroLastError"
            }

            Exit-WithCode 8 "Macro nao iniciou no VBA (sem novas linhas de log). Detalhe COM: $macroLastError"
        }

        Write-Log "Falha COM na invocacao da macro, mas VBA ja registrou atividade no log. Continuando monitoramento." -Lvl "WARN"
    }

    if ($macroRunInvocationFailed) {
        Start-Sleep -Milliseconds 700
        $sizeAfterMacroCall = (Get-Item $VbaLogFile).Length
        if ($sizeAfterMacroCall -le $initialLogSize) {
            Exit-WithCode 8 "Macro nao iniciou no VBA (sem novas linhas de log). Provavel erro de compilacao/projeto."
        }
    }

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

        if (-not (Test-Path $VbaLogFile)) {
            continue
        }

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
            else {
                ""
            }

            if ($newContent -match "ERRO FATAL") {
                $fatalVba = $true
                $foundEnd = $true
            }
            elseif ($newContent -match "FIM\s+Do\s+PROCESSO\.") {
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
    if ($wb) {
        if ($success) {
            try {
                $wb.Save()
                Write-Log "Workbook salvo com sucesso antes do fechamento."
            }
            catch {
                $saveFailed = $true
                Write-Log "Falha ao salvar workbook antes do fechamento: $_" -Lvl "ERRO"
            }
        }
        try { $wb.Close($false) } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wb) | Out-Null } catch {}
    }
    if ($excel) {
        try { $excel.Quit() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch {}
    }
}

if ($saveFailed) {
    Exit-WithCode 6 "Falha ao salvar workbook atualizado antes do fechamento."
}

if ($success) {
    Exit-WithCode 0 "Macro concluida com sucesso."
}
else {
    Exit-WithCode 6 "Conclusao anormal."
}
