[CmdletBinding()]
param(
    [string]$RootPath = (Join-Path $PSScriptRoot ".."),
    [string]$AuditPath = ""
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if ([string]::IsNullOrWhiteSpace($AuditPath)) {
    $AuditPath = Join-Path $RootPath "Audit\vba"
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

function Get-FileHashSafe {
    param([string]$FilePath)

    if (-not (Test-Path -LiteralPath $FilePath)) {
        return $null
    }

    try {
        return (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256 -ErrorAction Stop).Hash
    }
    catch [System.Exception] {
        return $null
    }
}

$resolvedRoot = (Resolve-Path -LiteralPath $RootPath).Path
$auditFullPath = [System.IO.Path]::GetFullPath($AuditPath)

if (-not (Test-Path -LiteralPath $auditFullPath)) {
    Write-Log -Level "ERROR" -Message "Audit path not found: $auditFullPath"
    exit 1
}

$manifests = Get-ChildItem -LiteralPath $auditFullPath -Recurse -File -Filter "vba-manifest.json"
if ($manifests.Count -eq 0) {
    Write-Log -Level "WARN" -Message "No vba-manifest.json found under $auditFullPath"
    exit 0
}

$reportItems = @()

foreach ($manifestFile in $manifests) {
    $manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $sourceRel = [string]$manifest.sourcePath
    $sourceDir = [System.IO.Path]::GetDirectoryName($sourceRel)
    $repoFolder = if ([string]::IsNullOrWhiteSpace($sourceDir)) { $resolvedRoot } else { Join-Path $resolvedRoot $sourceDir }
    $auditFolder = Split-Path -Parent $manifestFile.FullName

    $componentMap = @{}
    foreach ($component in $manifest.components) {
        if ($component.type -ne "StdModule" -and $component.type -ne "ClassModule") {
            continue
        }

        $fileName = "{0}{1}" -f $component.name, $component.extension
        $componentMap[$fileName] = $true

        $exportFile = Join-Path $auditFolder $fileName
        $repoFile = Join-Path $repoFolder $fileName

        $exportHash = Get-FileHashSafe -FilePath $exportFile
        $repoHash = Get-FileHashSafe -FilePath $repoFile

        $status = "Match"
        if (-not $repoHash) {
            $status = "MissingInRepo"
        }
        elseif (-not $exportHash) {
            $status = "MissingInAudit"
        }
        elseif ($repoHash -ne $exportHash) {
            $status = "Different"
        }

        $reportItems += [ordered]@{
            workbook   = $sourceRel
            module     = $fileName
            status     = $status
            repoPath   = if ($repoHash) { Get-RelativePath -BasePath $resolvedRoot -TargetPath $repoFile } else { "" }
            exportPath = if ($exportHash) { Get-RelativePath -BasePath $resolvedRoot -TargetPath $exportFile } else { "" }
            repoHash   = $repoHash
            exportHash = $exportHash
        }
    }

    if (Test-Path -LiteralPath $repoFolder) {
        $repoBas = Get-ChildItem -LiteralPath $repoFolder -File -Filter "*.bas"
        $repoCls = Get-ChildItem -LiteralPath $repoFolder -File -Filter "*.cls"
        foreach ($repoFile in @(@($repoBas) + @($repoCls))) {
            if (-not $componentMap.ContainsKey($repoFile.Name)) {
                $reportItems += [ordered]@{
                    workbook   = $sourceRel
                    module     = $repoFile.Name
                    status     = "MissingInXlsm"
                    repoPath   = Get-RelativePath -BasePath $resolvedRoot -TargetPath $repoFile.FullName
                    exportPath = ""
                    repoHash   = Get-FileHashSafe -FilePath $repoFile.FullName
                    exportHash = ""
                }
            }
        }
    }
}

$reportDoc = [ordered]@{
    generatedAt = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    rootPath    = $resolvedRoot
    auditPath   = $auditFullPath
    itemCount   = $reportItems.Count
    items       = $reportItems
}

$reportPath = Join-Path $auditFullPath "compare-report.json"
Write-Utf8File -FilePath $reportPath -Content ($reportDoc | ConvertTo-Json -Depth 8)
Write-Log -Level "INFO" -Message "Comparison report saved: $reportPath"
