# ==============================================================================
# ARQUIVO: SimularErroAcertoMontagem.ps1
# VERSAO: 1.0
# DESCRICAO: Executa validacao E2E da Montagem com dois cenarios controlados:
#            1) Forca erro de validacao e confirma envio de e-mail de alerta.
#            2) Restaura os dados e confirma envio de e-mail de acerto.
#
# IMPORTANTE:
# - Este script altera 1 celula temporariamente e restaura ao final.
# - Usa o workbook oficial e dispara envios reais via Outlook.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$WorkbookPath = "C:\Automacoes\Montagem de Terceirizados\Validador_Notas_Montagem.xlsm",
    [string]$ReenviarScriptPath = "C:\Automacoes\Montagem de Terceirizados\ReenviarAlertaErros.ps1",
    [string]$LogPath = "",
    [switch]$SkipExecution
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$script:TableName = "VW_EXC_OB_PED_ROM_Faccao"
$script:ColRef = "CD_REF_CLT"
$script:ColObs = "OBS_OB"

$montagemPath = Split-Path -Parent $WorkbookPath
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $montagemPath ("Logs\log_" + (Get-Date -Format "yyyy-MM-dd") + ".log")
}

$legacyLogPath = Join-Path $montagemPath "Logs\Montagem.log"
if (-not (Test-Path -LiteralPath $LogPath) -and (Test-Path -LiteralPath $legacyLogPath)) {
    $LogPath = $legacyLogPath
}

function Write-Stage {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    $ts = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
    Write-Host "[$ts] [SIM] [$Level] $Message"
}

function Get-LogOffset {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return 0L
    }

    return [System.IO.FileInfo]::new($Path).Length
}

function Read-LogDelta {
    param(
        [string]$Path,
        [long]$Offset
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }

    $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        [void]$fs.Seek($Offset, [System.IO.SeekOrigin]::Begin)
        $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8, $true)
        try {
            return $sr.ReadToEnd()
        }
        finally {
            $sr.Close()
            $sr.Dispose()
        }
    }
    finally {
        $fs.Close()
        $fs.Dispose()
    }
}

function Assert-Markers {
    param(
        [string]$Text,
        [string[]]$Markers,
        [string]$Scenario
    )

    foreach ($marker in $Markers) {
        if ($Text -notmatch [Regex]::Escape($marker)) {
            throw "Cenario '$Scenario' falhou: marcador ausente no log: $marker"
        }
    }
}

function Remove-ComObject {
    param([object]$Object)

    if ($null -eq $Object) {
        return
    }

    try {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
    catch {
    }
}

function Find-TargetTable {
    param([object]$Workbook)

    foreach ($ws in $Workbook.Worksheets) {
        foreach ($lo in $ws.ListObjects) {
            if ([string]$lo.Name -eq $script:TableName) {
                return @{
                    Worksheet = $ws
                    Table = $lo
                }
            }
        }
    }

    throw "Tabela '$($script:TableName)' nao encontrada no workbook."
}

function Get-ColumnIndex {
    param(
        [object]$Table,
        [string]$ColumnName
    )

    for ($i = 1; $i -le $Table.ListColumns.Count; $i++) {
        if ([string]$Table.ListColumns.Item($i).Name -eq $ColumnName) {
            return $i
        }
    }

    throw "Coluna '$ColumnName' nao encontrada na tabela '$($Table.Name)'."
}

function Find-DataRow {
    param(
        [object]$DataBodyRange,
        [int]$RefColumn,
        [int]$ObsColumn
    )

    for ($r = 1; $r -le $DataBodyRange.Rows.Count; $r++) {
        $ref = [string]$DataBodyRange.Cells.Item($r, $RefColumn).Value2
        $obs = [string]$DataBodyRange.Cells.Item($r, $ObsColumn).Value2

        if (-not [string]::IsNullOrWhiteSpace($ref) -and $obs -match "NF:\s*\d+") {
            return $r
        }
    }

    throw "Nao foi encontrada linha elegivel para simulacao (ref + OBS_OB com NF)."
}

function Set-ReferenceValue {
    param(
        [string]$Path,
        [int]$RowIndex,
        [string]$NewValue,
        [ref]$OriginalRef,
        [ref]$WorksheetName
    )

    $excel = $null
    $wb = $null

    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $excel.ScreenUpdating = $false
        $excel.EnableEvents = $false
        $excel.AskToUpdateLinks = $false

        $wb = $excel.Workbooks.Open($Path, 0, $false)

        $target = Find-TargetTable -Workbook $wb
        $ws = $target.Worksheet
        $lo = $target.Table

        $refIndex = Get-ColumnIndex -Table $lo -ColumnName $script:ColRef
        $obsIndex = Get-ColumnIndex -Table $lo -ColumnName $script:ColObs

        $data = $lo.DataBodyRange
        if ($null -eq $data) {
            throw "Tabela '$($script:TableName)' sem DataBodyRange."
        }

        $row = if ($RowIndex -gt 0) { $RowIndex } else { Find-DataRow -DataBodyRange $data -RefColumn $refIndex -ObsColumn $obsIndex }

        if ($row -lt 1 -or $row -gt $data.Rows.Count) {
            throw "Indice de linha invalido para simulacao: $row"
        }

        if ([string]::IsNullOrWhiteSpace($OriginalRef.Value)) {
            $OriginalRef.Value = [string]$data.Cells.Item($row, $refIndex).Value2
            if ([string]::IsNullOrWhiteSpace($OriginalRef.Value)) {
                throw "Valor original de CD_REF_CLT vazio na linha selecionada."
            }
        }

        $WorksheetName.Value = [string]$ws.Name
        $data.Cells.Item($row, $refIndex).Value2 = $NewValue

        $wb.Save()
        return $row
    }
    finally {
        if ($wb) {
            try { $wb.Close($false) | Out-Null } catch {}
            Remove-ComObject -Object $wb
        }
        if ($excel) {
            try { $excel.Quit() } catch {}
            Remove-ComObject -Object $excel
        }
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
    }
}

function Invoke-Reenviar {
    param(
        [string]$ScriptPath,
        [switch]$KeepCache
    )

    $pwshArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath)
    if ($KeepCache) {
        $pwshArgs += "-KeepCache"
    }

    $childOutput = & pwsh @pwshArgs 2>&1
    if ($null -ne $childOutput) {
        foreach ($line in @($childOutput)) {
            Write-Host $line
        }
    }

    return [int]$LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $WorkbookPath)) {
    throw "Workbook nao encontrado: $WorkbookPath"
}

if (-not (Test-Path -LiteralPath $ReenviarScriptPath)) {
    throw "Script de reenvio nao encontrado: $ReenviarScriptPath"
}

if (-not (Test-Path -LiteralPath (Split-Path -Parent $LogPath))) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
}

$rowIndex = 0
$originalRef = ""
$worksheetName = ""
$needsRestore = $false

Write-Stage "Iniciando simulacao E2E de erro/acerto na Montagem."

try {
    $forcedRef = ""

    Write-Stage "Aplicando erro controlado na coluna $($script:ColRef)."
    $rowIndex = Set-ReferenceValue -Path $WorkbookPath -RowIndex 0 -NewValue "__SIM_PLACEHOLDER__" -OriginalRef ([ref]$originalRef) -WorksheetName ([ref]$worksheetName)

    $forcedRef = "$originalRef`_SIM_ERRO"
    [void](Set-ReferenceValue -Path $WorkbookPath -RowIndex $rowIndex -NewValue $forcedRef -OriginalRef ([ref]$originalRef) -WorksheetName ([ref]$worksheetName))
    $needsRestore = $true

    Write-Stage "Linha de simulacao selecionada: $rowIndex (Aba: $worksheetName). Ref original: '$originalRef'."

    $offsetErro = Get-LogOffset -Path $LogPath

    if (-not $SkipExecution) {
        Write-Stage "Executando cenario A: envio de e-mail de erro (cache limpo)."
        $exitErro = Invoke-Reenviar -ScriptPath $ReenviarScriptPath
        if ($exitErro -ne 0) {
            throw "Cenario de erro retornou exit code $exitErro"
        }
    }

    $deltaErro = Read-LogDelta -Path $LogPath -Offset $offsetErro
    Assert-Markers -Text $deltaErro -Markers @("Email ERRO | tentativa", "E-MAIL: Enviado com sucesso") -Scenario "Erro"
    Write-Stage "Cenario A validado com sucesso."

    Write-Stage "Restaurando valor original para cenario de acerto."
    [void](Set-ReferenceValue -Path $WorkbookPath -RowIndex $rowIndex -NewValue $originalRef -OriginalRef ([ref]$originalRef) -WorksheetName ([ref]$worksheetName))
    $needsRestore = $false

    $offsetOk = Get-LogOffset -Path $LogPath

    if (-not $SkipExecution) {
        Write-Stage "Executando cenario B: envio de e-mail de acerto (cache preservado)."
        $exitOk = Invoke-Reenviar -ScriptPath $ReenviarScriptPath -KeepCache
        if ($exitOk -ne 0) {
            throw "Cenario de acerto retornou exit code $exitOk"
        }
    }

    $deltaOk = Read-LogDelta -Path $LogPath -Offset $offsetOk
    Assert-Markers -Text $deltaOk -Markers @("Email OK | tentativa", "E-MAIL: Enviado com sucesso") -Scenario "Acerto"
    Write-Stage "Cenario B validado com sucesso."

    Write-Stage "Simulacao E2E concluida: erro e acerto confirmados." "INFO"
    exit 0
}
catch {
    Write-Stage "Falha na simulacao: $($_.Exception.Message)" "ERRO"
    exit 1
}
finally {
    if ($needsRestore -and $rowIndex -gt 0 -and -not [string]::IsNullOrWhiteSpace($originalRef)) {
        try {
            [void](Set-ReferenceValue -Path $WorkbookPath -RowIndex $rowIndex -NewValue $originalRef -OriginalRef ([ref]$originalRef) -WorksheetName ([ref]$worksheetName))
            Write-Stage "Valor original restaurado automaticamente no bloco de seguranca." "WARN"
        }
        catch {
            Write-Stage "Falha ao restaurar valor original automaticamente: $($_.Exception.Message)" "ERRO"
        }
    }
}
