param(
    [string]$RootPath = (Join-Path $PSScriptRoot ".."),
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RootPath "Audit\vba"
}

function Write-Log {
    param(
        [string]$Level,
        [string]$Message
    )

    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] [$Level] $Message"
}

function Write-Utf8File {
    param(
        [string]$FilePath,
        [string]$Content
    )

    $dir = Split-Path -Parent $FilePath
    if ($dir) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }

    $sw = New-Object System.IO.StreamWriter($FilePath, $false, $Utf8NoBom)
    try {
        $sw.Write($Content)
        $sw.Flush()
    }
    finally {
        $sw.Close()
        $sw.Dispose()
    }
}

function Get-RelativePath {
    param(
        [string]$BasePath,
        [string]$TargetPath
    )

    $baseFull = [System.IO.Path]::GetFullPath($BasePath)
    $targetFull = [System.IO.Path]::GetFullPath($TargetPath)

    $separator = [string][System.IO.Path]::DirectorySeparatorChar
    if (-not $baseFull.EndsWith($separator)) {
        $baseFull += $separator
    }

    $baseUri = New-Object System.Uri($baseFull)
    $targetUri = New-Object System.Uri($targetFull)
    $relativeUri = $baseUri.MakeRelativeUri($targetUri)

    $relativePath = [System.Uri]::UnescapeDataString($relativeUri.ToString())
    return $relativePath.Replace('/', $separator)
}

function Sanitize-FileName {
    param([string]$Name)

    if ([string]::IsNullOrWhiteSpace($Name)) {
        return "unnamed"
    }

    return ($Name -replace '[\\/:*?"<>|]', '_')
}

function Get-ComponentTypeInfo {
    param([int]$ComponentType)

    switch ($ComponentType) {
        1 { return @{ TypeName = "StdModule"; Extension = ".bas" } }
        2 { return @{ TypeName = "ClassModule"; Extension = ".cls" } }
        3 { return @{ TypeName = "MSForm"; Extension = ".frm" } }
        100 { return @{ TypeName = "Document"; Extension = ".cls" } }
        default { return $null }
    }
}

function Release-ComObject {
    param([object]$Obj)

    if ($null -eq $Obj) {
        return
    }

    try {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Obj)
    }
    catch {}
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Force -Path $outputFullPath | Out-Null

$xlsmFiles = @(
    Get-ChildItem -LiteralPath $resolvedRoot -Recurse -File -Filter "*.xlsm" |
    Sort-Object -Property FullName
)

if ($xlsmFiles.Count -eq 0) {
    Write-Log -Level "WARN" -Message "No .xlsm files found under $resolvedRoot"
    exit 0
}

Write-Log -Level "INFO" -Message "Found $($xlsmFiles.Count) .xlsm files"

$excel = $null
$indexItems = @()

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
}
catch {
    Write-Log -Level "ERROR" -Message "Failed to start Excel.Application: $_"
    exit 1
}

foreach ($xlsm in $xlsmFiles) {
    $relativeSource = Get-RelativePath -BasePath $resolvedRoot -TargetPath $xlsm.FullName
    Write-Log -Level "INFO" -Message "Exporting $relativeSource"

    $relativeDir = [System.IO.Path]::GetDirectoryName($relativeSource)
    if ([string]::IsNullOrWhiteSpace($relativeDir)) {
        $workbookOutputRoot = Join-Path $outputFullPath $xlsm.BaseName
    }
    else {
        $workbookOutputRoot = Join-Path (Join-Path $outputFullPath $relativeDir) $xlsm.BaseName
    }

    New-Item -ItemType Directory -Force -Path $workbookOutputRoot | Out-Null

    $wb = $null
    $componentsInfo = @()
    $errorMessage = $null

    try {
        $wb = $excel.Workbooks.Open($xlsm.FullName, 0, $true)
        $vbProject = $wb.VBProject
        $vbComponents = $vbProject.VBComponents

        foreach ($component in $vbComponents) {
            $typeInfo = Get-ComponentTypeInfo -ComponentType $component.Type
            if ($null -eq $typeInfo) {
                Write-Log -Level "WARN" -Message "Skipping component '$($component.Name)' (Type=$($component.Type))"
                continue
            }

            $safeName = Sanitize-FileName -Name $component.Name
            $exportPath = Join-Path $workbookOutputRoot ($safeName + $typeInfo.Extension)

            if (Test-Path -LiteralPath $exportPath) {
                Remove-Item -LiteralPath $exportPath -Force
            }

            $component.Export($exportPath)

            $exportedFiles = @()
            if (Test-Path -LiteralPath $exportPath) {
                $exportedFiles += Get-RelativePath -BasePath $resolvedRoot -TargetPath $exportPath
            }

            if ($typeInfo.TypeName -eq "MSForm") {
                $frxPath = [System.IO.Path]::ChangeExtension($exportPath, "frx")
                if (Test-Path -LiteralPath $frxPath) {
                    $exportedFiles += Get-RelativePath -BasePath $resolvedRoot -TargetPath $frxPath
                }
            }

            $componentsInfo += [ordered]@{
                name          = [string]$component.Name
                type          = $typeInfo.TypeName
                extension     = $typeInfo.Extension
                exportedFiles = $exportedFiles
            }
        }
    }
    catch {
        $errorMessage = [string]$_
        Write-Log -Level "ERROR" -Message ("Failed to export {0}: {1}" -f $relativeSource, $errorMessage)
    }
    finally {
        if ($wb) {
            try { $wb.Close($false) | Out-Null } catch {}
            Release-ComObject -Obj $wb
        }
    }

    $manifest = [ordered]@{
        sourcePath          = $relativeSource
        sourceFileSizeBytes = $xlsm.Length
        exportedAt          = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
        componentCount      = $componentsInfo.Count
        components          = $componentsInfo
        error               = $errorMessage
    }

    $manifestPath = Join-Path $workbookOutputRoot "vba-manifest.json"
    Write-Utf8File -FilePath $manifestPath -Content ($manifest | ConvertTo-Json -Depth 8)

    $indexItems += [ordered]@{
        sourcePath     = $relativeSource
        outputPath     = Get-RelativePath -BasePath $resolvedRoot -TargetPath $workbookOutputRoot
        manifestPath   = Get-RelativePath -BasePath $resolvedRoot -TargetPath $manifestPath
        componentCount = $componentsInfo.Count
        error          = $errorMessage
    }
}

try {
    if ($excel) {
        $excel.Quit()
    }
}
catch {}
finally {
    Release-ComObject -Obj $excel
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

$indexDoc = [ordered]@{
    generatedAt   = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    rootPath      = $resolvedRoot
    outputPath    = $outputFullPath
    workbookCount = $xlsmFiles.Count
    items         = $indexItems
}

$indexPath = Join-Path $outputFullPath "index.json"
Write-Utf8File -FilePath $indexPath -Content ($indexDoc | ConvertTo-Json -Depth 8)
Write-Log -Level "INFO" -Message "VBA export completed. Index: $indexPath"
