param(
    [string]$RootPath = (Join-Path $PSScriptRoot ".."),
    [string]$OutputPath = "",
    [switch]$IncludeAllXml
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RootPath "Audit\xlsm"
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
    } finally {
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

function Copy-RelativeFileIfExists {
    param(
        [string]$SourceRoot,
        [string]$RelativePath,
        [string]$TargetRoot
    )

    $sourcePath = Join-Path $SourceRoot $RelativePath
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        return $false
    }

    $targetPath = Join-Path $TargetRoot $RelativePath
    $targetDir = Split-Path -Parent $targetPath
    if ($targetDir) {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    }

    Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
    return $true
}

function Copy-RelativeFolderRecursively {
    param(
        [string]$SourceRoot,
        [string]$RelativeFolder,
        [string]$TargetRoot
    )

    $sourceFolder = Join-Path $SourceRoot $RelativeFolder
    if (-not (Test-Path -LiteralPath $sourceFolder)) {
        return @()
    }

    $copied = @()
    $files = Get-ChildItem -LiteralPath $sourceFolder -Recurse -File
    foreach ($file in $files) {
        $relativeFile = Get-RelativePath -BasePath $SourceRoot -TargetPath $file.FullName
        if (Copy-RelativeFileIfExists -SourceRoot $SourceRoot -RelativePath $relativeFile -TargetRoot $TargetRoot) {
            $copied += $relativeFile
        }
    }

    return $copied
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

$indexItems = @()

foreach ($xlsm in $xlsmFiles) {
    $relativeSource = Get-RelativePath -BasePath $resolvedRoot -TargetPath $xlsm.FullName
    Write-Log -Level "INFO" -Message "Extracting $relativeSource"

    $tempRoot = Join-Path $env:TEMP ("automacoes_xlsm_audit_" + [Guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $tempRoot ($xlsm.BaseName + ".zip")
    $extractRoot = Join-Path $tempRoot "extract"

    try {
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
        New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null

        Copy-Item -LiteralPath $xlsm.FullName -Destination $zipPath -Force
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force

        $relativeDir = [System.IO.Path]::GetDirectoryName($relativeSource)
        if ([string]::IsNullOrWhiteSpace($relativeDir)) {
            $workbookOutputRoot = Join-Path $outputFullPath $xlsm.BaseName
        } else {
            $workbookOutputRoot = Join-Path (Join-Path $outputFullPath $relativeDir) $xlsm.BaseName
        }

        New-Item -ItemType Directory -Force -Path $workbookOutputRoot | Out-Null

        $copiedFiles = @()
        $coreFiles = @(
            "[Content_Types].xml",
            "_rels/.rels",
            "docProps/app.xml",
            "docProps/core.xml",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/vbaProject.bin"
        )

        foreach ($relativeFile in $coreFiles) {
            if (Copy-RelativeFileIfExists -SourceRoot $extractRoot -RelativePath $relativeFile -TargetRoot $workbookOutputRoot) {
                $copiedFiles += $relativeFile
            }
        }

        $auditFolders = @(
            "xl/connections",
            "xl/queries",
            "customXml",
            "xl/pivotCache"
        )

        foreach ($folder in $auditFolders) {
            $copiedFiles += Copy-RelativeFolderRecursively -SourceRoot $extractRoot -RelativeFolder $folder -TargetRoot $workbookOutputRoot
        }

        if ($IncludeAllXml) {
            $allXmlFiles = Get-ChildItem -LiteralPath $extractRoot -Recurse -File -Filter "*.xml"
            foreach ($xmlFile in $allXmlFiles) {
                $relativeXml = Get-RelativePath -BasePath $extractRoot -TargetPath $xmlFile.FullName
                if (Copy-RelativeFileIfExists -SourceRoot $extractRoot -RelativePath $relativeXml -TargetRoot $workbookOutputRoot) {
                    $copiedFiles += $relativeXml
                }
            }
        }

        $copiedFiles = $copiedFiles | Sort-Object -Unique

        $manifest = [ordered]@{
            sourcePath = $relativeSource
            sourceFileSizeBytes = $xlsm.Length
            exportedAt = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
            copiedFileCount = $copiedFiles.Count
            copiedFiles = $copiedFiles
        }

        $manifestPath = Join-Path $workbookOutputRoot "manifest.json"
        Write-Utf8File -FilePath $manifestPath -Content ($manifest | ConvertTo-Json -Depth 8)

        $indexItems += [ordered]@{
            sourcePath = $relativeSource
            outputPath = Get-RelativePath -BasePath $resolvedRoot -TargetPath $workbookOutputRoot
            copiedFileCount = $copiedFiles.Count
            manifestPath = Get-RelativePath -BasePath $resolvedRoot -TargetPath $manifestPath
        }
    } catch {
        Write-Log -Level "ERROR" -Message "Failed to extract ${relativeSource}: $_"

        $indexItems += [ordered]@{
            sourcePath = $relativeSource
            outputPath = ""
            copiedFileCount = 0
            error = [string]$_
        }
    } finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$indexDoc = [ordered]@{
    generatedAt = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    rootPath = $resolvedRoot
    outputPath = $outputFullPath
    workbookCount = $xlsmFiles.Count
    items = $indexItems
}

$indexPath = Join-Path $outputFullPath "index.json"
Write-Utf8File -FilePath $indexPath -Content ($indexDoc | ConvertTo-Json -Depth 8)
Write-Log -Level "INFO" -Message "Audit export completed. Index: $indexPath"