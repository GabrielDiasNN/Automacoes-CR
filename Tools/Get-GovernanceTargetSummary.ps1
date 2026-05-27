[CmdletBinding()]
param(
    [string]$BasePath = ".",
    [switch]$StagedOnly,
    [string[]]$Paths = @(),
    [switch]$AsJson
)

$ErrorActionPreference = "Stop"

$resolvedRoot = (Resolve-Path -LiteralPath $BasePath).Path

function Get-NormalizedPaths {
    param([string[]]$InputPaths)

    return @(
        $InputPaths |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Trim().Trim('"').Replace('/', '\') } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
    )
}

function Test-MatchAnyPattern {
    param(
        [string]$Path,
        [string[]]$Patterns
    )

    foreach ($pattern in $Patterns) {
        if ($Path -match $pattern) {
            return $true
        }
    }

    return $false
}

if ($StagedOnly -and $Paths.Count -eq 0) {
    $stagedRaw = git diff --cached --name-only --diff-filter=ACM 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao obter arquivos staged via git diff --cached."
    }

    if (-not [string]::IsNullOrWhiteSpace($stagedRaw)) {
        $Paths = @($stagedRaw -split "`r?`n")
    }
}

$normalizedPaths = Get-NormalizedPaths -InputPaths $Paths

$criticalPatterns = @(
    "^lib\\",
    "^Tools\\",
    "^AGENTS\.md$",
    "^GEMINI\.md$",
    "^CONTEXT\.md$",
    "^SECURITY\.md$",
    "^\.gitleaks\.toml$",
    "^\.githooks\\pre-commit$",
    "^\.github\\workflows\\",
    "^\.github\\skills\\"
)

$logTargetPatterns = @(
    "\.(ps1|psm1)$"
)

$excludedLogTargetPatterns = @(
    "^Audit\\",
    "^Tools\\"
)

$criticalPaths = @(
    $normalizedPaths |
        Where-Object { Test-MatchAnyPattern -Path $_ -Patterns $criticalPatterns }
)

$logTargetPaths = @(
    $normalizedPaths |
        Where-Object { Test-MatchAnyPattern -Path $_ -Patterns $logTargetPatterns } |
        Where-Object { -not (Test-MatchAnyPattern -Path $_ -Patterns $excludedLogTargetPatterns) }
)

$fullScanRequired = $criticalPaths.Count -gt 0
$governancePaths = if ($fullScanRequired) { @() } else { $normalizedPaths }

$selectionMode = if ($normalizedPaths.Count -eq 0) {
    "no_paths"
}
elseif ($fullScanRequired) {
    "full_scan"
}
else {
    "targeted_paths"
}

$summary = [PSCustomObject]@{
    BasePath          = $resolvedRoot
    NormalizedPaths   = @($normalizedPaths)
    CriticalPaths     = @($criticalPaths)
    GovernancePaths   = @($governancePaths)
    LogTargetPaths    = @($logTargetPaths)
    HasCriticalPaths  = $fullScanRequired
    HasLogTargets     = $logTargetPaths.Count -gt 0
    SelectionMode     = $selectionMode
    ChangedFileCount  = $normalizedPaths.Count
    CriticalPathCount = $criticalPaths.Count
    LogTargetCount    = $logTargetPaths.Count
}

if ($AsJson) {
    $summary | ConvertTo-Json -Depth 6 -Compress
    exit 0
}

$summary
