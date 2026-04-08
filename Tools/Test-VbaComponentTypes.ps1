# ==============================================================================
# ARQUIVO: Test-VbaComponentTypes.ps1
# VERSAO: 1.0
# DESCRICAO: Valida se componentes VBA esperados estao com tipo correto
#            no workbook alvo (StdModule para .bas e ClassModule para .cls).
# ==============================================================================

[CmdletBinding()]
param(
    [string]$WorkbookPath = "C:\Automacoes\Montagem de Terceirizados\Validador_Notas_Montagem.xlsm",
    [string]$SourceFolder = ""
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param(
        [string]$Level,
        [string]$Message
    )

    $ts = Get-Date -Format "dd/MM/yyyy HH:mm:ss"
    Write-Host "[$ts] [$Level] $Message"
}

function Get-TypeName {
    param([int]$Type)

    switch ($Type) {
        1 { return "StdModule" }
        2 { return "ClassModule" }
        3 { return "MSForm" }
        100 { return "Document" }
        default { return "Other" }
    }
}

$resolvedWorkbookPath = [System.IO.Path]::GetFullPath($WorkbookPath)
if (-not (Test-Path -LiteralPath $resolvedWorkbookPath)) {
    Write-Log "ERROR" "Workbook nao encontrado: $resolvedWorkbookPath"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($SourceFolder)) {
    $SourceFolder = Split-Path -Parent $resolvedWorkbookPath
}

$resolvedSourceFolder = [System.IO.Path]::GetFullPath($SourceFolder)
if (-not (Test-Path -LiteralPath $resolvedSourceFolder)) {
    Write-Log "ERROR" "Pasta de fontes nao encontrada: $resolvedSourceFolder"
    exit 1
}

Write-Log "INFO" "Workbook: $resolvedWorkbookPath"
Write-Log "INFO" "Fontes  : $resolvedSourceFolder"

$expectedModules = Get-ChildItem -LiteralPath $resolvedSourceFolder -File -Filter "*.bas" | ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_.Name) }
$expectedClasses = Get-ChildItem -LiteralPath $resolvedSourceFolder -File -Filter "*.cls" | ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_.Name) }

if (($expectedModules.Count + $expectedClasses.Count) -eq 0) {
    Write-Log "WARN" "Nenhum arquivo .bas/.cls encontrado na pasta de fontes."
    exit 0
}

$excel = $null
$wb = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false

    $wb = $excel.Workbooks.Open($resolvedWorkbookPath, 0, $true)

    $componentMap = @{}
    foreach ($component in $wb.VBProject.VBComponents) {
        $componentMap[[string]$component.Name] = [int]$component.Type
    }

    $issues = New-Object System.Collections.Generic.List[string]

    foreach ($name in $expectedModules | Sort-Object -Unique) {
        if (-not $componentMap.ContainsKey($name)) {
            $issues.Add(("Ausente no VBAProject: modulo {0}" -f $name))
            continue
        }

        $actualType = [int]$componentMap[$name]
        if ($actualType -ne 1) {
            $issues.Add(("Tipo incorreto para modulo {0}: atual={1} esperado=StdModule" -f $name, (Get-TypeName -Type $actualType)))
        }
    }

    foreach ($name in $expectedClasses | Sort-Object -Unique) {
        if (-not $componentMap.ContainsKey($name)) {
            $issues.Add(("Ausente no VBAProject: classe {0}" -f $name))
            continue
        }

        $actualType = [int]$componentMap[$name]
        if ($actualType -ne 2) {
            $issues.Add(("Tipo incorreto para classe {0}: atual={1} esperado=ClassModule" -f $name, (Get-TypeName -Type $actualType)))
        }
    }

    if ($issues.Count -gt 0) {
        Write-Log "ERROR" "Foram detectadas inconsistencias de tipagem VBA."
        foreach ($issue in $issues) {
            Write-Log "ERROR" (" - " + $issue)
        }
        exit 2
    }

    Write-Log "INFO" "Tipagem VBA validada com sucesso."
    exit 0
}
catch {
    Write-Log "ERROR" ("Falha ao validar tipagem VBA: {0}" -f $_.Exception.Message)
    exit 3
}
finally {
    if ($null -ne $wb) {
        try { $wb.Close($false) | Out-Null } catch {}
    }
    if ($null -ne $excel) {
        try { $excel.Quit() } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) } catch {}
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
