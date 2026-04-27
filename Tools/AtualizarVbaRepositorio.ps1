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
    $line = "[$ts] [$Level] $Message"
    Write-Host $line
    Write-Utf8Line -FilePath (Join-Path $RootPath "Audit\vba\sync-repo.log") -Line $line
}

function Write-Utf8Line {
    param(
        [string]$FilePath,
        [string]$Line
    )

    $dir = Split-Path -Parent $FilePath
    if ($dir) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }

    $sw = New-Object System.IO.StreamWriter($FilePath, $true, $Utf8NoBom)
    try {
        $sw.WriteLine($Line)
        $sw.Flush()
    }
    finally {
        $sw.Close()
        $sw.Dispose()
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

foreach ($manifestFile in $manifests) {
    $manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $sourceRel = [string]$manifest.sourcePath
    $sourceDir = [System.IO.Path]::GetDirectoryName($sourceRel)
    $repoFolder = if ([string]::IsNullOrWhiteSpace($sourceDir)) { $resolvedRoot } else { Join-Path $resolvedRoot $sourceDir }
    $auditFolder = Split-Path -Parent $manifestFile.FullName

    Write-Log -Level "INFO" -Message "Atualizando repo para $sourceRel"

    foreach ($component in $manifest.components) {
        if ($component.type -ne "StdModule" -and $component.type -ne "ClassModule") {
            continue
        }

        $fileName = "{0}{1}" -f $component.name, $component.extension
        $exportFile = Join-Path $auditFolder $fileName
        $repoFile = Join-Path $repoFolder $fileName

        if (-not (Test-Path -LiteralPath $exportFile)) {
            Write-Log -Level "ERROR" -Message "Export file not found: $exportFile"
            continue
        }

        $repoDir = Split-Path -Parent $repoFile
        if ($repoDir) {
            New-Item -ItemType Directory -Force -Path $repoDir | Out-Null
        }

        Copy-Item -LiteralPath $exportFile -Destination $repoFile -Force
        Write-Log -Level "INFO" -Message "Atualizado: $repoFile"
    }
}

Write-Log -Level "INFO" -Message "Repositorio atualizado a partir do audit."
