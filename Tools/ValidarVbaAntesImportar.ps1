[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    [string]$SharedDir = ""
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] [$Level] $Message"
}

function New-CrlfTempCopy {
    param([string]$SourcePath)

    $tempPath = Join-Path $env:TEMP ("{0}_{1}{2}" -f [System.IO.Path]::GetFileNameWithoutExtension($SourcePath), [Guid]::NewGuid().ToString("N"), [System.IO.Path]::GetExtension($SourcePath))
    $bytes = [System.IO.File]::ReadAllBytes($SourcePath)
    $normalized = New-Object System.Collections.Generic.List[byte]

    for ($i = 0; $i -lt $bytes.Length; $i++) {
        $byte = $bytes[$i]
        if ($byte -eq 10) {
            if ($i -eq 0 -or $bytes[$i - 1] -ne 13) {
                $normalized.Add(13)
            }
            $normalized.Add(10)
        }
        else {
            $normalized.Add($byte)
        }
    }

    [System.IO.File]::WriteAllBytes($tempPath, $normalized.ToArray())
    return $tempPath
}

function Get-VbaSourceFile {
    param([string]$FolderPath)

    if ([string]::IsNullOrWhiteSpace($FolderPath)) { return @() }
    if (-not (Test-Path -LiteralPath $FolderPath)) { return @() }

    Get-ChildItem -LiteralPath $FolderPath -File | Where-Object {
        $_.Extension -in ".bas", ".cls" -and
        $_.BaseName -notmatch '^_tmp' -and
        $_.Name -notmatch '^~\$'
    } | Sort-Object Name
}

function Get-VbaComponentNameFromFile {
    param([string]$FilePath)

    $fallback = [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
    $probe = Get-Content -LiteralPath $FilePath -TotalCount 80 -Encoding UTF8 -ErrorAction SilentlyContinue
    foreach ($line in $probe) {
        if ($line -match 'Attribute\s+VB_Name\s*=\s*"([^"]+)"') {
            return $Matches[1]
        }
    }

    return $fallback
}

function New-VbaDescriptor {
    param(
        [System.IO.FileInfo]$File,
        [string]$Origin
    )

    $componentName = Get-VbaComponentNameFromFile -FilePath $File.FullName
    $expectedType = if ($File.Extension -ieq ".cls") { 2 } else { 1 }

    [PSCustomObject]@{
        FileInfo      = $File
        FullName      = $File.FullName
        FileName      = $File.Name
        ComponentName = $componentName
        ExpectedType  = $expectedType
        Origin        = $Origin
    }
}

function Test-DuplicateComponentName {
    param(
        [array]$Descriptors,
        [string]$Context
    )

    $dups = $Descriptors | Group-Object ComponentName | Where-Object { $_.Count -gt 1 }
    if (-not $dups) { return }

    $lines = @()
    foreach ($dup in $dups) {
        $files = ($dup.Group | ForEach-Object { $_.FileName }) -join ", "
        $lines += "- $($dup.Name): $files"
    }

    throw "Nomes de componentes VBA duplicados em ${Context}:`n$($lines -join "`n")"
}

function Import-VbaDescriptor {
    param(
        $VBProject,
        $Descriptor,
        [string]$LogPrefix = ""
    )

    $existing = $null
    foreach ($comp in $VBProject.VBComponents) {
        if ($comp.Name -eq $Descriptor.ComponentName -and ($comp.Type -eq 1 -or $comp.Type -eq 2 -or $comp.Type -eq 3)) {
            $existing = $comp
            break
        }
    }

    if ($null -ne $existing) {
        $VBProject.VBComponents.Remove($existing)
    }

    $tempImportPath = $null
    $importPath = $Descriptor.FullName

    try {
        if ($Descriptor.FileInfo.Extension -ieq ".cls") {
            $tempImportPath = New-CrlfTempCopy -SourcePath $Descriptor.FullName
            $importPath = $tempImportPath
        }

        $importedComponent = $VBProject.VBComponents.Import($importPath)
        if ($null -eq $importedComponent) {
            throw "$LogPrefix import retornou nulo para '$($Descriptor.FileName)'."
        }

        if ([int]$importedComponent.Type -ne $Descriptor.ExpectedType) {
            try { $VBProject.VBComponents.Remove($importedComponent) } catch { } # Ignorado
            throw "$LogPrefix componente '$($Descriptor.FileName)' importado com tipo incorreto ($([int]$importedComponent.Type)). Esperado: $($Descriptor.ExpectedType)."
        }

        if ($importedComponent.Name -ne $Descriptor.ComponentName) {
            try { $VBProject.VBComponents.Remove($importedComponent) } catch { } # Ignorado
            throw "$LogPrefix componente '$($Descriptor.FileName)' importado com nome '$($importedComponent.Name)' em vez de '$($Descriptor.ComponentName)'."
        }

        Write-Log "INFO" "$LogPrefix Importado: $($Descriptor.FileName) -> $($Descriptor.ComponentName)"
    }
    finally {
        if ($null -ne $tempImportPath -and (Test-Path -LiteralPath $tempImportPath)) {
            try { Remove-Item -LiteralPath $tempImportPath -Force } catch { } # Ignorado
        }
    }
}

function Invoke-VbaProjectCompile {
    param(
        $ExcelApp,
        $Workbook
    )

    $Workbook.Activate() | Out-Null
    $compileControl = $ExcelApp.VBE.CommandBars.FindControl(1, 578)

    if ($null -eq $compileControl) {
        throw "Comando de compilacao VBA nao encontrado no VBE (ID 578)."
    }

    $compileControl.Execute()
}

$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)
if (-not (Test-Path -LiteralPath $SourceDir)) {
    throw "Pasta de fontes nao encontrada: $SourceDir"
}

$localFiles = @(Get-VbaSourceFile -FolderPath $SourceDir)
if ($localFiles.Count -eq 0) {
    throw "Nenhum arquivo .bas/.cls valido encontrado em: $SourceDir"
}

$sharedFiles = @()
if (-not [string]::IsNullOrWhiteSpace($SharedDir) -and (Test-Path -LiteralPath $SharedDir)) {
    $SharedDir = [System.IO.Path]::GetFullPath($SharedDir)
    $sharedFiles = @(Get-VbaSourceFile -FolderPath $SharedDir)
}

$localDescriptors = @($localFiles | ForEach-Object { New-VbaDescriptor -File $_ -Origin "Local" })
$sharedDescriptors = @($sharedFiles | ForEach-Object { New-VbaDescriptor -File $_ -Origin "Shared" })

Test-DuplicateComponentName -Descriptors $localDescriptors -Context "SourceDir"
if ($sharedDescriptors.Count -gt 0) {
    Test-DuplicateComponentName -Descriptors $sharedDescriptors -Context "SharedDir"
}

$officeVersion = (Get-ChildItem "HKCU:\Software\Microsoft\Office" -ErrorAction SilentlyContinue |
    Where-Object { $_.PSChildName -match '^\d+\.\d+$' } |
    Sort-Object { [version]$_.PSChildName } -Descending |
    Select-Object -First 1).PSChildName
if ([string]::IsNullOrWhiteSpace($officeVersion)) { $officeVersion = "16.0" }
$regPath = "HKCU:\Software\Microsoft\Office\$officeVersion\Excel\Security"
$prevVal = $null
$excel = $null
$tmpWb = $null

try {
    $prevVal = (Get-ItemProperty -Path $regPath -Name "AccessVBOM" -ErrorAction SilentlyContinue).AccessVBOM
    Set-ItemProperty -Path $regPath -Name "AccessVBOM" -Value 1

    Write-Log "INFO" "Preflight VBA: abrindo Excel COM"
    $excel = New-Object -ComObject "Excel.Application"
    $excel.Visible = $false
    $excel.DisplayAlerts = $false

    Write-Log "INFO" "Preflight VBA: criando workbook temporario"
    $tmpWb = $excel.Workbooks.Add()
    $vbProj = $tmpWb.VBProject

    foreach ($descriptor in $localDescriptors) {
        Import-VbaDescriptor -VBProject $vbProj -Descriptor $descriptor -LogPrefix "[Preflight]"
    }

    foreach ($descriptor in $sharedDescriptors) {
        Import-VbaDescriptor -VBProject $vbProj -Descriptor $descriptor -LogPrefix "[Preflight Shared]"
    }

    Write-Log "INFO" "Preflight VBA: compilando projeto temporario"
    Invoke-VbaProjectCompile -ExcelApp $excel -Workbook $tmpWb
    Write-Log "INFO" "Preflight VBA: compilacao concluida com sucesso"
}
catch {
    Write-Log "ERROR" "Preflight VBA falhou: $($_.Exception.Message)"
    throw
}
finally {
    if ($null -ne $tmpWb) {
        try { $tmpWb.Close($false) } catch { } # Ignorado
    }
    if ($null -ne $excel) {
        try { $excel.Quit() } catch { } # Ignorado
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    }

    if ($null -ne $prevVal) {
        try { Set-ItemProperty -Path $regPath -Name "AccessVBOM" -Value $prevVal } catch { } # Ignorado
    }
}

Write-Log "INFO" "Preflight VBA finalizado sem erros"
