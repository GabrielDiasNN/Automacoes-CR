# ==============================================================================
# ARQUIVO: Test-VbaSharedDependencies.ps1
# VERSAO: 1.0
# DESCRICAO: Valida dependencias VBA compartilhadas (shared) no fonte local e
#            no workbook real, evitando regressao em wrappers e sincronizacoes.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$RootPath = (Join-Path $PSScriptRoot "..")
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

function Get-NormalizedHash {
    param([string]$FilePath)

    if (-not (Test-Path -LiteralPath $FilePath)) {
        return $null
    }

    $raw = [System.IO.File]::ReadAllBytes($FilePath)
    $cleaned = [byte[]]($raw | Where-Object { $_ -ne 13 })
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($cleaned)
        return ([BitConverter]::ToString($hash)) -replace '-', ''
    }
    finally {
        $sha.Dispose()
    }
}

function Get-RequiredSharedClasses {
    param([string]$SourceDir)

    $required = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $classNames = @('ClsOutlookAdapter', 'ClsEmailComposerService')
    $files = Get-ChildItem -LiteralPath $SourceDir -File | Where-Object { $_.Extension -in '.bas', '.cls' }

    foreach ($file in $files) {
        $content = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
        foreach ($className in $classNames) {
            if ($content -match ("(?i)\b(?:As|New)\s+{0}\b" -f [regex]::Escape($className))) {
                [void]$required.Add($className)
            }
        }
    }

    return @($required | Sort-Object)
}

function Test-WorkbookSharedComponents {
    param(
        [string]$WorkbookPath,
        [string[]]$RequiredClasses
    )

    $issues = New-Object System.Collections.Generic.List[string]
    $excel = $null
    $wb = $null

    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false

        $wb = $excel.Workbooks.Open($WorkbookPath, 0, $true)
        $componentMap = @{}
        foreach ($component in $wb.VBProject.VBComponents) {
            $componentMap[[string]$component.Name] = [int]$component.Type
        }

        foreach ($className in $RequiredClasses) {
            if (-not $componentMap.ContainsKey($className)) {
                $issues.Add(("Classe shared ausente no workbook: {0}" -f $className))
                continue
            }

            if ([int]$componentMap[$className] -ne 2) {
                $issues.Add(("Classe shared com tipo incorreto no workbook: {0} (esperado ClassModule)" -f $className))
            }
        }
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

    return $issues
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$sharedDir = Join-Path $resolvedRoot "_Shared\VBA"

if (-not (Test-Path -LiteralPath $sharedDir)) {
    Write-Log "ERROR" "Pasta shared nao encontrada: $sharedDir"
    exit 2
}

$targets = @(
    [pscustomobject]@{
        Name         = "Montagem de Terceirizados"
        SourceDir    = Join-Path $resolvedRoot "Montagem de Terceirizados"
        WorkbookPath = Join-Path $resolvedRoot "Montagem de Terceirizados\Validador_Notas_Montagem.xlsm"
    },
    [pscustomobject]@{
        Name         = "Receitas Bloqueadas"
        SourceDir    = Join-Path $resolvedRoot "Receitas Bloqueadas"
        WorkbookPath = Join-Path $resolvedRoot "Receitas Bloqueadas\Receitas Bloqueadas.xlsm"
    },
    [pscustomobject]@{
        Name         = "Receitas Emitidas"
        SourceDir    = Join-Path $resolvedRoot "Receitas Emitidas"
        WorkbookPath = Join-Path $resolvedRoot "Receitas Emitidas\Controle de Receitas Emitidas.xlsm"
    }
)

$allIssues = New-Object System.Collections.Generic.List[string]

foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target.SourceDir)) {
        $allIssues.Add(("Pasta de fontes ausente: {0}" -f $target.SourceDir))
        continue
    }
    if (-not (Test-Path -LiteralPath $target.WorkbookPath)) {
        $allIssues.Add(("Workbook ausente: {0}" -f $target.WorkbookPath))
        continue
    }

    $requiredClasses = @(Get-RequiredSharedClasses -SourceDir $target.SourceDir)
    if ($requiredClasses.Count -eq 0) {
        Write-Log "INFO" ("{0}: nenhuma dependencia shared detectada nas fontes." -f $target.Name)
        continue
    }

    Write-Log "INFO" ("{0}: dependencias shared detectadas -> {1}" -f $target.Name, ($requiredClasses -join ', '))

    foreach ($className in $requiredClasses) {
        $sharedFile = Join-Path $sharedDir ($className + '.cls')
        $localFile = Join-Path $target.SourceDir ($className + '.cls')

        if (-not (Test-Path -LiteralPath $sharedFile)) {
            $allIssues.Add(("{0}: classe shared ausente em _Shared/VBA: {1}.cls" -f $target.Name, $className))
            continue
        }

        if (Test-Path -LiteralPath $localFile) {
            $localHash = Get-NormalizedHash -FilePath $localFile
            $sharedHash = Get-NormalizedHash -FilePath $sharedFile
            if ($localHash -ne $sharedHash) {
                $allIssues.Add(("{0}: copia local diverge da classe shared canonica: {1}.cls" -f $target.Name, $className))
            }
            else {
                Write-Log "INFO" ("{0}: copia local sincronizada com shared -> {1}.cls" -f $target.Name, $className)
            }
        }
        else {
            Write-Log "INFO" ("{0}: usa classe shared somente via importacao no workbook -> {1}.cls" -f $target.Name, $className)
        }
    }

    $workbookIssues = Test-WorkbookSharedComponents -WorkbookPath $target.WorkbookPath -RequiredClasses $requiredClasses
    foreach ($issue in $workbookIssues) {
        $allIssues.Add(("{0}: {1}" -f $target.Name, $issue))
    }
}

if ($allIssues.Count -gt 0) {
    Write-Log "ERROR" "Falhas detectadas na validacao de dependencias shared VBA."
    foreach ($issue in $allIssues) {
        Write-Log "ERROR" (" - " + $issue)
    }
    exit 1
}

Write-Log "INFO" "Dependencias shared VBA validadas com sucesso."
exit 0
